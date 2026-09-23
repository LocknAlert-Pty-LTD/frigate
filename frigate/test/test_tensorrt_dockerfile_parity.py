"""The amd64 TensorRT stages exist in two Dockerfiles; keep them identical.

`docker/tensorrt/Dockerfile.amd64` is what `docker buildx bake` builds (it takes
wheels/deps/rootfs in as named build contexts). `docker/main/Dockerfile` repeats
the same two stages so the image is also reachable from a plain `docker build
--target frigate-tensorrt`, and therefore from `docker compose build`, which
cannot supply bake's `target:` contexts.

Two copies means they can drift, and a drift would silently produce a different
image depending on which path built it. This test is the guard.

Deliberately dependency-free (no frigate imports, no cv2/onnxruntime) so it runs
on a bare host as well as in the container.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_DOCKERFILE = REPO_ROOT / "docker" / "main" / "Dockerfile"
TRT_DOCKERFILE = REPO_ROOT / "docker" / "tensorrt" / "Dockerfile.amd64"

SHARED_STAGES = ("trt-wheels", "frigate-tensorrt")

_FROM = re.compile(r"^FROM\s+.*?\s+AS\s+(?P<name>[\w.-]+)\s*$", re.IGNORECASE)


def parse_stages(path: Path) -> dict[str, list[str]]:
    """Map stage name -> its instruction lines, comments and blanks stripped.

    Comments are dropped on purpose: the main Dockerfile carries an extra
    explanatory block above its copy, and that should not count as drift.
    """
    stages: dict[str, list[str]] = {}
    current: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        match = _FROM.match(line.strip())

        if match:
            current = match.group("name")
            stages[current] = [line.strip()]
            continue

        if current is None:
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        stages[current].append(line)

    return stages


class TestTensorrtDockerfileParity(unittest.TestCase):
    def setUp(self) -> None:
        self.main = parse_stages(MAIN_DOCKERFILE)
        self.trt = parse_stages(TRT_DOCKERFILE)

    def test_both_dockerfiles_define_the_shared_stages(self) -> None:
        for stage in SHARED_STAGES:
            self.assertIn(
                stage, self.main, f"{MAIN_DOCKERFILE.name} lost stage '{stage}'"
            )
            self.assertIn(
                stage, self.trt, f"{TRT_DOCKERFILE.name} lost stage '{stage}'"
            )

    def test_shared_stages_are_identical(self) -> None:
        for stage in SHARED_STAGES:
            self.assertEqual(
                self.main[stage],
                self.trt[stage],
                f"Stage '{stage}' has drifted between docker/main/Dockerfile and "
                f"docker/tensorrt/Dockerfile.amd64. They must stay identical so "
                f"`docker build --target frigate-tensorrt` and `docker buildx "
                f"bake ... tensorrt` produce the same image.",
            )

    def test_frigate_tensorrt_still_builds_on_local_stages_in_main(self) -> None:
        """The point of the copy: in main/Dockerfile these resolve to real
        stages, so no named build contexts are needed."""
        for required in ("wheels", "deps", "rootfs"):
            self.assertIn(
                required,
                self.main,
                f"docker/main/Dockerfile must define a '{required}' stage for "
                f"frigate-tensorrt to build without buildx bake",
            )

    def test_main_dockerfile_default_target_is_unaffected(self) -> None:
        """Adding the TRT stages must not disturb the plain image."""
        self.assertIn("frigate", self.main)
        body = "\n".join(self.main["frigate"])
        self.assertNotIn("trt-wheels", body)
        self.assertNotIn("tensorrt", body.lower())


if __name__ == "__main__":
    unittest.main()
