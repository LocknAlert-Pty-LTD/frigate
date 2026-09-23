#!/usr/bin/env python3
"""Build (and optionally push) the Frigate images this fork publishes.

Why this exists instead of `make push-trt`:

* There is no `make` on Windows, and every documented build path goes through
  the Makefile.
* Each TensorRT variant needs a *different* set of environment variables
  (ARCH/BASE_IMAGE/SLIM_BASE/TRT_BASE). In PowerShell, `$env:BASE_IMAGE = ...`
  persists for the rest of the session, so running the Jetson build and then the
  amd64 build in one shell silently produces an amd64 image built on a Jetson
  base. Each build below gets its own environment dict, so that cannot happen.

Targets:

  tensorrt   amd64 dGPU (RTX 3060 etc.)      -> <repo>:<tag>-tensorrt
  jp5        Jetson, JetPack 5               -> <repo>:<tag>-tensorrt-jp5
  jp6        Jetson, JetPack 6               -> <repo>:<tag>-tensorrt-jp6
  default    standard image                  -> <repo>:<tag>

`default` is the image to use for Hailo. There is no separate Hailo image: the
HailoRT runtime is not baked in, it is downloaded on first start by
frigate/util/runtime_deps.py once a Hailo detector is configured.

Examples:

  python scripts/build_images.py --repo rainelocknalert/locknalert-frigate \\
      --tag 0.19.0 tensorrt --push

  python scripts/build_images.py --repo rainelocknalert/locknalert-frigate \\
      --tag 0.19.0 tensorrt jp5 jp6 default --push --dry-run
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def read_version() -> str:
    """Take VERSION from the Makefile rather than duplicating it here.

    A second copy would drift, and the only symptom would be images tagged with
    the wrong version -- silent and easy to miss.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^VERSION\s*=\s*(\S+)", makefile, re.MULTILINE)
    if not match:
        sys.exit("Could not read VERSION from the Makefile.")
    return match.group(1)


VERSION = read_version()

JETPACK5_BASE = "nvcr.io/nvidia/l4t-tensorrt:r8.5.2-runtime"
JETPACK6_BASE = "nvcr.io/nvidia/tensorrt:23.12-py3-igpu"

# name -> (tag suffix, bake env, needs_qemu)
TRT_TARGETS: dict[str, tuple[str, dict[str, str], bool]] = {
    "tensorrt": (
        "-tensorrt",
        {"ARCH": "amd64", "COMPUTE_LEVEL": "50 60 70 80 90"},
        False,
    ),
    "jp5": (
        "-tensorrt-jp5",
        {
            "ARCH": "arm64",
            "BASE_IMAGE": JETPACK5_BASE,
            "SLIM_BASE": JETPACK5_BASE,
            "TRT_BASE": JETPACK5_BASE,
        },
        True,
    ),
    "jp6": (
        "-tensorrt-jp6",
        {
            "ARCH": "arm64",
            "BASE_IMAGE": JETPACK6_BASE,
            "SLIM_BASE": JETPACK6_BASE,
            "TRT_BASE": JETPACK6_BASE,
        },
        True,
    ),
}

ALL_TARGETS = [*TRT_TARGETS, "default"]


def docker_binary() -> str:
    """Find docker even when it is not on PATH.

    A PowerShell window opened before Docker Desktop was installed or updated
    keeps the old PATH for its whole life, so `docker` is missing there even
    though the install is fine. Rather than making that the user's problem,
    fall back to the two standard Docker Desktop locations.
    """
    found = shutil.which("docker")
    if found:
        return found

    fallbacks = [
        pathlib.Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "DockerDesktop"
        / "resources"
        / "bin"
        / "docker.exe",
        pathlib.Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"),
    ]
    for candidate in fallbacks:
        if candidate.is_file():
            print(f"Note: docker is not on PATH; using {candidate}")
            return str(candidate)

    sys.exit(
        "docker not found. Start Docker Desktop, then open a NEW terminal so it "
        "picks up the updated PATH."
    )


def write_version_files() -> str:
    """The Makefile's `version` target, without needing make.

    Written with an explicit encoding and newline: PowerShell's Set-Content /
    Out-File default to UTF-8-with-BOM here, and a BOM in web/.env breaks the
    Vite build.
    """
    commit = subprocess.run(
        ["git", "log", "-1", "--pretty=format:%h"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.strip()

    (REPO_ROOT / "frigate" / "version.py").write_text(
        f'VERSION = "{VERSION}-{commit}"\n', encoding="utf-8", newline="\n"
    )
    (REPO_ROOT / "web" / ".env").write_text(
        f"VITE_GIT_COMMIT_HASH={commit}\n", encoding="utf-8", newline="\n"
    )
    return commit


def run(cmd: list[str], env: dict[str, str] | None, dry_run: bool) -> None:
    # quote anything with spaces so the echoed line is safe to copy and paste
    shown = " ".join(shlex.quote(part) for part in cmd)
    prefix = " ".join(
        f"{k}={shlex.quote(v)}" for k, v in sorted((env or {}).items())
    )
    print(f"\n$ {prefix + ' ' if prefix else ''}{shown}\n", flush=True)

    if dry_run:
        return

    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=full_env)
    if result.returncode != 0:
        sys.exit(f"Build failed for: {shown}")


def build_trt(
    docker: str, target: str, repo: str, tag: str, push: bool, dry_run: bool
) -> None:
    suffix, bake_env, _ = TRT_TARGETS[target]
    cmd = [
        docker,
        "buildx",
        "bake",
        "--file=docker/tensorrt/trt.hcl",
        "tensorrt",
        f"--set=tensorrt.tags={repo}:{tag}{suffix}",
        "--push" if push else "--load",
    ]
    run(cmd, bake_env, dry_run)


def build_default(
    docker: str, repo: str, tag: str, platforms: str, push: bool, dry_run: bool
) -> None:
    cmd = [
        docker,
        "buildx",
        "build",
        "--target=frigate",
        "--file=docker/main/Dockerfile",
        ".",
        f"--tag={repo}:{tag}",
        f"--platform={platforms}",
        "--push" if push else "--load",
    ]
    run(cmd, None, dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "targets",
        nargs="+",
        choices=[*ALL_TARGETS, "all"],
        help="which images to build ('all' = every target)",
    )
    parser.add_argument("--repo", required=True, help="e.g. user/repository")
    parser.add_argument("--tag", default=VERSION, help=f"tag prefix (default {VERSION})")
    parser.add_argument(
        "--push", action="store_true", help="push to the registry instead of --load"
    )
    parser.add_argument(
        "--platforms",
        default="linux/amd64",
        help="platforms for the 'default' target (default linux/amd64). "
        "Add linux/arm64 for Raspberry Pi / arm64 Hailo hosts.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the commands without running them"
    )
    args = parser.parse_args()

    targets = ALL_TARGETS if "all" in args.targets else list(dict.fromkeys(args.targets))
    docker = docker_binary()

    commit = write_version_files()
    print(f"Version files written: {VERSION}-{commit}")

    if any(TRT_TARGETS.get(t, ("", {}, False))[2] for t in targets):
        print(
            "\nNote: jp5/jp6 are arm64. On an x86 host they build under QEMU "
            "emulation, which is very slow (hours). If they fail to start, run:\n"
            "  docker run --privileged --rm tonistiigi/binfmt --install all"
        )

    if args.push:
        print(
            "\nNote: --push needs a docker-container builder and a logged-in "
            "registry. If it errors, run:\n"
            "  docker login\n"
            "  docker buildx create --name frigate-builder "
            "--driver docker-container --use --bootstrap"
        )

    for target in targets:
        if target == "default":
            build_default(
                docker, args.repo, args.tag, args.platforms, args.push, args.dry_run
            )
        else:
            build_trt(docker, target, args.repo, args.tag, args.push, args.dry_run)

    print("\nDone." if not args.dry_run else "\nDry run complete; nothing was built.")


if __name__ == "__main__":
    main()
