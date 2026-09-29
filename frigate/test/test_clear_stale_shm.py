"""The stale-shm cleanup must clear Kestrel's segments and nothing else.

/dev/shm is commonly shared with the host (`ipc: host`), where it also holds
other containers' segments. PostgreSQL keeps its shared buffers there, so a
blanket sweep would corrupt an unrelated live database. The camera list from
this instance's own config is the whitelist, and these tests pin that.

Loads the script by path: it ships to /usr/local/bin without a .py extension
and is deliberately importable without the frigate package, so it runs under
root before the service starts.
"""

import importlib.util
import os
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

        # the script targets /dev/shm by literal path; redirect it
        self._patch_shm_path()

    def _patch_shm_path(self) -> None:
        shm = self.shm
        real_listdir, real_unlink, real_join = os.listdir, os.unlink, os.path.join

        def listdir(path):
            return real_listdir(shm if path == "/dev/shm" else path)

        def unlink(path):
            if path.startswith("/dev/shm/"):
                path = real_join(shm, path[len("/dev/shm/") :])
            return real_unlink(path)

        def join(a, *rest):
            return real_join(shm if a == "/dev/shm" else a, *rest)

        self.module.os.listdir = listdir
        self.module.os.unlink = unlink
        self.module.os.path.join = join

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


if __name__ == "__main__":
    unittest.main()
