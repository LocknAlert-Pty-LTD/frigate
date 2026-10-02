"""The stale-shm cleanup must clear Kestrel's segments and nothing else.

/dev/shm is commonly shared with the host (`ipc: host`), where it also holds
other containers' segments. PostgreSQL keeps its shared buffers there, so a
blanket sweep would corrupt an unrelated live database. The camera list from
this instance's own config is the whitelist, and these tests pin that.

Loads the script by path: it ships to /usr/local/bin without a .py extension
and is deliberately importable without the frigate package, so it runs under
root before the service starts.
"""

import contextlib
import importlib.util
import io
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "docker/main/rootfs/usr/local/bin/clear-stale-shm"


def load_script():
    spec = importlib.util.spec_from_loader(
        "clear_stale_shm",
        importlib.machinery.SourceFileLoader("clear_stale_shm", str(SCRIPT)),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClearStaleShmTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_script()

        self.shm = tempfile.mkdtemp()
        self.config_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.shm, True)
        self.addCleanup(shutil.rmtree, self.config_dir, True)

        # The script reads its target from a module constant, so pointing it at
        # a temporary directory is a plain assignment.
        #
        # An earlier version patched self.module.os.unlink instead. That is the
        # *same* module object every other import of os shares, so the patch
        # escaped the script entirely and shutil.rmtree -- which passes dir_fd
        # -- blew up in this class's own teardown. It only showed up on Linux;
        # rmtree takes a different path on Windows and passed there.
        self.module.SHM_DIR = self.shm

    def write_config(self, body: str) -> None:
        Path(self.config_dir, "config.yml").write_text(body, encoding="utf-8")
        os.environ["CONFIG_FILE"] = str(Path(self.config_dir, "config.yml"))
        self.addCleanup(os.environ.pop, "CONFIG_FILE", None)

    def touch(self, *names: str) -> None:
        for name in names:
            Path(self.shm, name).write_bytes(b"x")

    def present(self) -> set:
        return set(os.listdir(self.shm))


class TestRemovesOwnSegments(ClearStaleShmTestCase):
    def test_removes_camera_out_and_frame_segments(self) -> None:
        self.write_config("cameras:\n  hek: {}\n  driveway: {}\n")
        self.touch(
            "hek", "out-hek", "hek_frame0", "hek_frame17",
            "driveway", "out-driveway", "driveway_frame3",
        )

        self.module.main()

        self.assertEqual(set(), self.present())

    def test_is_idempotent(self) -> None:
        self.write_config("cameras:\n  hek: {}\n")
        self.touch("hek")

        self.module.main()
        self.module.main()  # must not raise on the second pass

        self.assertEqual(set(), self.present())


class TestLeavesOtherContainersAlone(ClearStaleShmTestCase):
    def test_postgresql_segments_survive(self) -> None:
        """The one that would corrupt a live database."""
        self.write_config("cameras:\n  hek: {}\n")
        self.touch("hek", "PostgreSQL.1208056366", "PostgreSQL.667366728")

        self.module.main()

        self.assertEqual(
            {"PostgreSQL.1208056366", "PostgreSQL.667366728"}, self.present()
        )

    def test_unrelated_segments_survive(self) -> None:
        self.write_config("cameras:\n  hek: {}\n")
        self.touch("hek", "go2rtc.yaml", "sem.mp-0005nsit", "some-other-app")

        self.module.main()

        self.assertEqual(
            {"go2rtc.yaml", "sem.mp-0005nsit", "some-other-app"}, self.present()
        )

    def test_a_camera_named_like_another_app_does_not_widen_the_sweep(self) -> None:
        """Only exact names and the frame prefix, never a substring match."""
        self.write_config("cameras:\n  gate: {}\n")
        self.touch("gate", "gateway_db", "my-gate", "gate_frame1")

        self.module.main()

        self.assertEqual({"gateway_db", "my-gate"}, self.present())


class TestDegradesSafely(ClearStaleShmTestCase):
    def test_missing_config_removes_nothing(self) -> None:
        os.environ["CONFIG_FILE"] = str(Path(self.config_dir, "absent.yml"))
        self.addCleanup(os.environ.pop, "CONFIG_FILE", None)
        self.touch("hek", "PostgreSQL.1")

        self.assertEqual(0, self.module.main())
        self.assertEqual({"hek", "PostgreSQL.1"}, self.present())

    def test_unparseable_config_removes_nothing(self) -> None:
        self.write_config("cameras: [this is not a mapping\n")
        self.touch("hek")

        self.assertEqual(0, self.module.main())
        self.assertEqual({"hek"}, self.present())

    def test_config_without_cameras_removes_nothing(self) -> None:
        self.write_config("mqtt:\n  host: broker\n")
        self.touch("hek")

        self.assertEqual(0, self.module.main())
        self.assertEqual({"hek"}, self.present())

    def test_path_traversal_in_a_camera_name_is_refused(self) -> None:
        self.write_config('cameras:\n  "../escape": {}\n  hek: {}\n')
        self.touch("hek")

        self.module.main()

        self.assertEqual(set(), self.present())


class TestYamlBackend(ClearStaleShmTestCase):
    """The image ships ruamel.yaml, not PyYAML.

    An `import yaml` here fails in the container and, before this was caught,
    made the whole cleanup a silent no-op: startup then died on the first stale
    segment with no clue why.
    """

    def hide(self, *names: str):
        """Make the given modules unimportable for the duration of a test."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            root = name.split(".")[0]
            if root in names:
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        saved = {n: sys.modules.pop(n, None) for n in names}
        for mod in list(sys.modules):
            if mod.split(".")[0] in names:
                saved.setdefault(mod, sys.modules.pop(mod))

        builtins.__import__ = fake_import
        self.addCleanup(setattr, builtins, "__import__", real_import)
        self.addCleanup(
            lambda: sys.modules.update({k: v for k, v in saved.items() if v is not None})
        )

    def test_works_with_only_ruamel_available(self) -> None:
        """The container case: PyYAML absent."""
        self.hide("yaml")
        self.write_config("cameras:\n  hek: {}\n")
        self.touch("hek", "out-hek", "PostgreSQL.1")

        self.module.main()

        self.assertEqual({"PostgreSQL.1"}, self.present())

    def test_works_with_only_pyyaml_available(self) -> None:
        self.hide("ruamel")
        self.write_config("cameras:\n  hek: {}\n")
        self.touch("hek")

        self.module.main()

        self.assertEqual(set(), self.present())

    def test_warns_loudly_when_no_yaml_library_exists(self) -> None:
        """Must never fail silently -- that is what made this hard to find."""
        self.hide("yaml", "ruamel")
        self.write_config("cameras:\n  hek: {}\n")
        self.touch("hek")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(0, self.module.main())

        self.assertIn("no YAML library available", stderr.getvalue())
        self.assertEqual({"hek"}, self.present(), "nothing removed without a parser")


if __name__ == "__main__":
    unittest.main()
