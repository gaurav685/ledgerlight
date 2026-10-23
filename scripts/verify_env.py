"""Phase 0 environment verification: PASS/FAIL table, non-zero exit on failure.

Usage: uv run python scripts/verify_env.py [--check-docker]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    required: bool = True


def check_python_version() -> CheckResult:
    major, minor = sys.version_info[:2]
    ok = (major, minor) == (3, 12)
    return CheckResult("python version == 3.12", ok, f"running {major}.{minor}")


def check_uv_lock_in_sync() -> CheckResult:
    uv = shutil.which("uv")
    if uv is None:
        return CheckResult("uv.lock in sync", False, "uv not found on PATH")
    proc = subprocess.run(
        [uv, "lock", "--check"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    ok = proc.returncode == 0
    detail = "uv.lock matches pyproject.toml" if ok else (proc.stderr or proc.stdout).strip()
    return CheckResult("uv.lock in sync", ok, detail)


def check_required_tools() -> list[CheckResult]:
    results = []
    for tool in ("git", "uv", "docker"):
        found = shutil.which(tool) is not None
        results.append(CheckResult(f"'{tool}' on PATH", found, "found" if found else "NOT FOUND"))
    for tool in ("node", "tesseract", "pdftoppm"):
        found = shutil.which(tool) is not None
        results.append(
            CheckResult(
                f"'{tool}' on PATH (informational)",
                found,
                "found" if found else "not found (not required for Phase 0)",
                required=False,
            )
        )
    return results


def check_docker_health() -> CheckResult:
    docker = shutil.which("docker")
    if docker is None:
        return CheckResult("docker daemon reachable", False, "docker not on PATH", required=False)
    proc = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=15)
    ok = proc.returncode == 0
    detail = "daemon responding" if ok else (proc.stderr or proc.stdout).strip().splitlines()[0]
    return CheckResult("docker daemon reachable", ok, detail, required=False)


def check_config_loads_from_env_example() -> CheckResult:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from ledgerlight.config.settings import Settings

        example_vars: dict[str, str] = {}
        example_path = REPO_ROOT / ".env.example"
        for line in example_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            example_vars[key.strip()] = value.strip()

        field_kwargs = {
            k[len("LEDGERLIGHT_") :].lower(): v
            for k, v in example_vars.items()
            if k.startswith("LEDGERLIGHT_")
        }
        settings = Settings(_env_file=None, **field_kwargs)  # type: ignore[call-arg,arg-type]
        return CheckResult(
            "config loads from .env.example-derived env",
            True,
            f"contact_email={settings.contact_email!r}",
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult("config loads from .env.example-derived env", False, str(exc))


def check_data_dirs_exist_and_ignored() -> CheckResult:
    missing = []
    for sub in ("raw", "interim", "processed", "manifests"):
        if not (REPO_ROOT / "data" / sub).is_dir():
            missing.append(sub)
    if missing:
        return CheckResult(
            "data/{raw,interim,processed,manifests} exist", False, f"missing: {missing}"
        )

    git = shutil.which("git")
    if git is None:
        return CheckResult("raw data paths gitignored", False, "git not found")
    proc = subprocess.run(
        [git, "check-ignore", "-q", "data/raw/example/2026/file.pdf"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    ok = proc.returncode == 0
    return CheckResult(
        "data/raw is gitignored", ok, "git check-ignore confirms" if ok else "NOT ignored"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-docker", action="store_true", help="Include the Docker daemon health check"
    )
    args = parser.parse_args()

    checks: list[CheckResult] = [
        check_python_version(),
        check_uv_lock_in_sync(),
        *check_required_tools(),
        check_config_loads_from_env_example(),
        check_data_dirs_exist_and_ignored(),
    ]
    if args.check_docker:
        checks.append(check_docker_health())

    name_width = max(len(c.name) for c in checks) + 2
    print(f"{'CHECK'.ljust(name_width)} RESULT   DETAIL")
    overall_ok = True
    for c in checks:
        status = "PASS" if c.ok else ("FAIL" if c.required else "SKIP")
        if not c.ok and c.required:
            overall_ok = False
        print(f"{c.name.ljust(name_width)} {status.ljust(8)} {c.detail}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
