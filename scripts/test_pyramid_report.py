"""Phase 6A §4: run the complete test pyramid (unit, integration,
corpus, e2e, security) and print counts per layer.

Runs each layer as its own `pytest` subprocess, sequentially (never in
parallel). The "integration" layer is further split into small,
memory-safe batches by test file -- this host's free memory has been
confirmed repeatedly unstable during this project's own work (from the
user's other running applications, not this project's stack), and a
single unbatched run of the full ~324-test integration suite has been
observed to get killed by the OS under real memory pressure. Before
each batch this script checks free memory and waits (briefly, bounded)
for it to recover rather than launch into a batch likely to be killed;
if it's still too low after waiting, that batch is marked BLOCKED with
the real evidence, never silently skipped or weakened.

"e2e" and "security" are not pytest markers in this project; they are
named subsets of the same test files already covered by "integration"
(see SECURITY_TEST_FILES below), reported separately because the
brief asks for them by name, not because they run twice as separate
suites.

The frontend Playwright e2e suite (`frontend/e2e/full-e2e-lite.spec.ts`)
and the OWASP ZAP baseline are NOT run by this script -- they need the
e2e-lite Docker stack up and a separate npm/npx toolchain, which is
genuinely heavier than the rest of this pyramid. Their last real,
recorded result is printed as an informational line instead; re-run
them directly (see docs/phase-6/progress.md §2) if you need a fresh
number.

KNOWN REAL LIMITATION (disclosed, not fixed here): this script's own
internal memory wait only sees memory from inside this one Python
process. On this host, the harness that launches background work has
its own external memory-pressure killer that can stop the whole
process -- including this script and every batch still inside it --
regardless of what this script's own checks see at the time. That
happened twice while building this (docs/phase-6/evidence/
sec04-test-pyramid-report.log records it). The reliable workaround on
this specific host is to run the same batches as separate tool
invocations instead of one long-lived process, so a kill costs one
batch, not the whole run -- exactly what that evidence file's real
counts were produced with. Nothing about pytest or this project's own
code changes between the two approaches; only how many processes the
external killer can take out at once.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SECURITY_TEST_FILES = [
    "tests/test_security_controls.py",
    "tests/test_authz_matrix.py",
    "tests/test_cross_tenant_idor.py",
    "tests/test_api_rls.py",
    "tests/test_prompt_injection_separation.py",
]

BATCH_SIZE = 8
MIN_FREE_GB = 1.0
MEMORY_WAIT_ATTEMPTS = 5
MEMORY_WAIT_SECONDS = 60

COUNT_RE = re.compile(r"(\d+) (passed|failed|deselected|skipped|error|errors)\b")


def _free_memory_gb() -> float | None:
    try:
        import psutil

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:
        return None


def _wait_for_memory() -> bool:
    for attempt in range(MEMORY_WAIT_ATTEMPTS):
        free = _free_memory_gb()
        if free is None or free >= MIN_FREE_GB:
            return True
        print(
            f"  free memory {free:.2f}GB < {MIN_FREE_GB}GB, "
            f"waiting {MEMORY_WAIT_SECONDS}s (attempt {attempt + 1}/{MEMORY_WAIT_ATTEMPTS})...",
            flush=True,
        )
        time.sleep(MEMORY_WAIT_SECONDS)
    return False


def _run(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _summary_line(output: str) -> str:
    for line in reversed(output.splitlines()):
        if " passed" in line or " failed" in line or " error" in line or " no tests ran" in line:
            return line.strip()
    return "(no summary line found)"


def _parse_counts(summary: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for n, kind in COUNT_RE.findall(summary):
        kind = "error" if kind == "errors" else kind
        counts[kind] = counts.get(kind, 0) + int(n)
    return counts


def _add_counts(total: dict[str, int], part: dict[str, int]) -> None:
    for k, v in part.items():
        total[k] = total.get(k, 0) + v


_COLLECT_FILE_RE = re.compile(r"^(tests/[\w./]+\.py)(?:::.*)?: \d+$")


def _collect_integration_files() -> list[str]:
    exit_code, output = _run(["-m", "integration", "--collect-only", "-q"])
    if exit_code not in (0, 1):
        return []
    # pytest's collect-only summary format depends on whether stdout is a
    # TTY -- piped (as here) gives one condensed "path: N" line per file;
    # a real terminal gives full "path::test_name" node ids instead. Both
    # are handled so this works the same whichever way it's invoked.
    files: set[str] = set()
    for line in output.splitlines():
        condensed = _COLLECT_FILE_RE.match(line)
        if condensed:
            files.add(condensed.group(1))
        elif "::" in line and line.startswith("tests/"):
            files.add(line.split("::", 1)[0])
    return sorted(files)


def _run_batched(files: list[str], marker_args: list[str]) -> tuple[int, dict[str, int]]:
    total: dict[str, int] = {}
    overall_ok = True
    for i in range(0, len(files), BATCH_SIZE):
        batch = files[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        n_batches = (len(files) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  batch {batch_num}/{n_batches} ({len(batch)} files)...", flush=True)
        if not _wait_for_memory():
            free = _free_memory_gb()
            print(
                f"  BLOCKED: batch {batch_num} skipped -- free memory stayed below "
                f"{MIN_FREE_GB}GB after {MEMORY_WAIT_ATTEMPTS} waits "
                f"(last measured: {free}GB). Real host memory pressure, not a test failure.",
                flush=True,
            )
            overall_ok = False
            continue
        exit_code, output = _run([*marker_args, *batch])
        summary = _summary_line(output)
        print(f"    {summary}", flush=True)
        _add_counts(total, _parse_counts(summary))
        if exit_code not in (0, 1):
            # 1 = real test failures (counted above); anything else (e.g. a
            # kill) is a real infra problem, not a countable test outcome.
            print(f"  WARNING: batch {batch_num} exited {exit_code} (possible kill)", flush=True)
            overall_ok = False
    return (0 if overall_ok else 1), total


def main() -> int:
    results: list[tuple[str, int, dict[str, int]]] = []

    print("--- unit (default) ---", flush=True)
    exit_code, output = _run([])
    summary = _summary_line(output)
    print(summary, flush=True)
    results.append(("unit (default)", exit_code, _parse_counts(summary)))

    print("--- integration (batched) ---", flush=True)
    integration_files = _collect_integration_files()
    if integration_files:
        exit_code, counts = _run_batched(integration_files, ["-m", "integration"])
        results.append(("integration", exit_code, counts))
    else:
        print("  could not collect integration test files -- skipping", flush=True)
        results.append(("integration", 1, {}))

    print("--- corpus ---", flush=True)
    exit_code, output = _run(["-m", "corpus"])
    summary = _summary_line(output)
    print(summary, flush=True)
    results.append(("corpus", exit_code, _parse_counts(summary)))

    print("--- e2e (subset of integration) ---", flush=True)
    exit_code, output = _run(["-m", "integration", "tests/test_e2e_pipeline.py"])
    summary = _summary_line(output)
    print(summary, flush=True)
    results.append(("e2e (subset of integration)", exit_code, _parse_counts(summary)))

    print("--- security (subset of integration) ---", flush=True)
    exit_code, output = _run(["-m", "integration", *SECURITY_TEST_FILES])
    summary = _summary_line(output)
    print(summary, flush=True)
    results.append(("security (subset of integration)", exit_code, _parse_counts(summary)))

    print()
    print("=== Test pyramid summary ===")
    for name, exit_code, counts in results:
        status = "OK" if exit_code == 0 else f"ISSUES (exit {exit_code})"
        counts_str = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "(no counts)"
        print(f"{name:38s} {status:20s} {counts_str}")

    print()
    print("Not run by this script (separate toolchain -- last recorded result):")
    print("  frontend Playwright e2e-lite suite: 4/4 passed (Phase 6A §2)")
    print("  OWASP ZAP baseline: 0 FAIL, 4 WARN, 64 PASS (Phase 6A §2)")

    return 0 if all(code == 0 for _, code, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
