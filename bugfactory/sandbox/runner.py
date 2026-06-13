"""Run the target repo's test suite in a subprocess with a timeout.

For the local demo over a trusted dummy repo this is all the isolation we
need. When we scale to untrusted/unknown repos, this is the seam where a
Docker-backed runner drops in behind the same interface.
"""
from __future__ import annotations

import os
import re
import subprocess

_FAILED_RE = re.compile(r"^(FAILED\s+\S+|\S+::\S+\s+FAILED)", re.MULTILINE)


def run_tests(repo_dir: str, timeout: int = 120) -> dict:
    env = os.environ.copy()
    src = os.path.join(repo_dir, "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "tests", "-q"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout + proc.stderr
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        return {"passed": False, "returncode": -1, "output": "TIMEOUT", "failing": ["<timeout>"]}

    failing = sorted({m.group(0).replace("FAILED", "").strip() for m in _FAILED_RE.finditer(output)})
    failing = [f for f in failing if f]
    return {"passed": returncode == 0, "returncode": returncode, "output": output, "failing": failing}
