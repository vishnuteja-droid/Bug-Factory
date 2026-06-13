"""Run the target repo's test suite in a subprocess with a timeout.

Returns both the failing tests and the full set of collected tests, so the
pipeline can apply a precise acceptance gate (resolved-without-regression)
rather than a blunt "whole suite green" check.

For the local demo over a trusted dummy repo this is all the isolation we
need. When we scale to untrusted/unknown repos, this is the seam where a
Docker-backed runner drops in behind the same interface.
"""
from __future__ import annotations

import os
import re
import subprocess

_FAILED_RE = re.compile(r"^(?:FAILED\s+(\S+)|(\S+::\S+)\s+FAILED)", re.MULTILINE)


def _env(repo_dir: str) -> dict:
    env = os.environ.copy()
    src = os.path.join(repo_dir, "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _collect(repo_dir: str, timeout: int) -> set:
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "tests", "--collect-only", "-q"],
            cwd=repo_dir, env=_env(repo_dir), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return set()
    return {ln.strip() for ln in proc.stdout.splitlines() if "::" in ln and not ln.startswith(" ")}


def run_tests(repo_dir: str, timeout: int = 120) -> dict:
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "tests", "-q"],
            cwd=repo_dir, env=_env(repo_dir), capture_output=True, text=True, timeout=timeout,
        )
        output, returncode = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return {"passed": False, "returncode": -1, "output": "TIMEOUT", "failing": {"<timeout>"}, "collected": set()}

    failing = {m.group(1) or m.group(2) for m in _FAILED_RE.finditer(output)}
    failing = {f for f in failing if f}
    return {
        "passed": returncode == 0,
        "returncode": returncode,
        "output": output,
        "failing": failing,
        "collected": _collect(repo_dir, timeout),
    }
