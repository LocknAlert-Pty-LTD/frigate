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


def git_commit_hash() -> str:
    """Short commit hash, with git's own error surfaced if it refuses.

    Never swallow git's stderr here. The common failure is WSL reading a
    checkout on the Windows filesystem, where git's ownership check trips and
    exits 128; hiding that message turns a one-line fix into a mystery.
    """
    proc = subprocess.run(
        ["git", "log", "-1", "--pretty=format:%h"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()

    stderr = (proc.stderr or "").strip()

    if "dubious ownership" in stderr or "safe.directory" in stderr:
        sys.exit(
            f"git refused to read this repository:\n\n  {stderr.splitlines()[0]}\n\n"
            "This is git's ownership check. It trips under WSL when the checkout\n"
            "lives on the Windows filesystem (/mnt/c/...), because the directory's\n"
            "owner does not match your WSL user. Mark it trusted, then re-run:\n\n"
            f"  git config --global --add safe.directory {REPO_ROOT.as_posix()}\n"
        )

    sys.exit(
        f"git log failed (exit {proc.returncode}):\n\n"
        f"  {stderr or proc.stdout.strip() or '<no output>'}\n"
    )


def write_version_files() -> str:
    """The Makefile's `version` target, without needing make.

    Written with an explicit encoding and newline: PowerShell's Set-Content /
    Out-File default to UTF-8-with-BOM here, and a BOM in web/.env breaks the
    Vite build.
    """
    commit = git_commit_hash()

    (REPO_ROOT / "frigate" / "version.py").write_text(
        f'VERSION = "{VERSION}-{commit}"\n', encoding="utf-8", newline="\n"
    )
    (REPO_ROOT / "web" / ".env").write_text(
        f"VITE_GIT_COMMIT_HASH={commit}\n", encoding="utf-8", newline="\n"
    )
    return commit


def check_docker_access(docker: str) -> None:
    """Fail early, and usefully, when the daemon is unreachable.

    Reaching for `sudo` is the natural reaction to the permission error, but it
    makes things worse: a builder created under sudo lives in root's buildx
    state and is invisible when you later build as yourself, and `docker login`
    credentials are per-user too. Point at the group fix instead.
    """
    proc = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return

    err = (proc.stderr or proc.stdout or "").strip()
    first = err.splitlines()[0] if err else "<no output>"

    if "permission denied" in err.lower():
        sys.exit(
            f"Cannot reach the Docker daemon as this user:\n\n  {first}\n\n"
            "Add yourself to the docker group rather than using sudo -- a builder\n"
            "created with sudo lives in root's buildx state and will not be found\n"
            "when you build as yourself:\n\n"
            "  sudo usermod -aG docker $USER\n\n"
            "Then apply the new group. In WSL the reliable way is to close the\n"
            "shell and run `wsl --shutdown` from Windows; `newgrp docker` works\n"
            "for a single shell. Afterwards recreate the builder as your user:\n\n"
            "  docker buildx rm frigate-builder 2>/dev/null || true\n"
            "  docker buildx create --name frigate-builder "
            "--driver docker-container --use --bootstrap\n"
        )

    sys.exit(f"docker is installed but not usable:\n\n  {first}\n")


def check_registry_login(repo: str) -> None:
    """Fail before the build when the push has no chance of succeeding.

    A missing `docker login` only shows up at the very end, after everything is
    compiled, which is a miserable way to lose an hour. This reads the same
    config file the push will use -- including the root-owned one when running
    under sudo, which is a different file from the one `docker login` wrote if
    that was run as a normal user.

    Best effort by design: a credential helper can store the secret outside the
    config, so an entry here is evidence of a login, not proof of a valid one.
    Hence exit only when there is clearly nothing at all.
    """
    import json

    config_dir = os.environ.get("DOCKER_CONFIG")
    config_path = (
        pathlib.Path(config_dir) / "config.json"
        if config_dir
        else pathlib.Path.home() / ".docker" / "config.json"
    )

    registry = "docker.io" if repo.count("/") <= 1 else repo.split("/")[0]
    hint = (
        f"  docker login{'' if registry == 'docker.io' else ' ' + registry}\n\n"
        f"Checked {config_path}"
    )

    if not config_path.is_file():
        sys.exit(
            f"No Docker credentials found, so --push would fail after the build.\n\n"
            f"Log in first:\n\n{hint} (does not exist).\n"
        )

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"\nWarning: could not read {config_path} ({exc}); skipping login check.")
        return

    auths = config.get("auths") or {}
    logged_in = any(registry in key for key in auths) or bool(
        config.get("credsStore") or config.get("credHelpers")
    )

    if not logged_in:
        sys.exit(
            f"No credentials for {registry} found, so --push would fail after the\n"
            f"build finishes. Log in first:\n\n{hint}\n"
        )


def warn_if_running_as_root() -> None:
    """sudo works, but it quietly splits your Docker state in two."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return

    print(
        "\nWarning: running as root (sudo).\n"
        "The builder, the build cache and the registry credentials all live in\n"
        "root's Docker state, separate from your user's. In particular a\n"
        "`docker login` you ran as yourself does NOT apply here, so --push can\n"
        "fail at the end. Preferably fix the group instead and re-run without\n"
        "sudo:\n\n"
        "  sudo usermod -aG docker $USER\n"
        "  # then, from Windows: wsl --shutdown, and reopen the shell\n"
    )


def warn_if_slow_filesystem() -> None:
    """A build context on /mnt/c from WSL goes over the 9p bridge, which is
    slow enough to dominate the build. Worth saying once, up front."""
    if sys.platform != "linux":
        return
    if not str(REPO_ROOT).startswith("/mnt/"):
        return

    print(
        "\nWarning: this checkout is on the Windows filesystem "
        f"({REPO_ROOT}).\n"
        "Docker build contexts there cross WSL's 9p bridge and are far slower\n"
        "than a checkout inside the WSL filesystem. For a build this large,\n"
        "cloning to e.g. ~/frigate and building there is usually much faster.\n"
    )


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

    # Check the things that make a build fail immediately before doing any work,
    # so the error arrives in one second rather than after the context upload.
    if not args.dry_run:
        check_docker_access(docker)
        if args.push:
            check_registry_login(args.repo)

    warn_if_running_as_root()
    warn_if_slow_filesystem()

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
