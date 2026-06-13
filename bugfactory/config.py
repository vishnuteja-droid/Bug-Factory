"""Central run configuration. Threaded into the pipeline and read by the CLI/UI
from env vars, so behavior is tunable without code changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    provider: str = "ollama"
    model: str = "gemma3:1b"
    host: str = "http://localhost:11434"
    repo_path: str = "sample_repo"
    max_fix_attempts: int = 3
    max_candidates: int = 3
    baseline_runs: int = 2
    output_dir: str = "output"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            provider=os.environ.get("PROVIDER", cls.provider),
            model=os.environ.get("OLLAMA_MODEL", cls.model),
            host=os.environ.get("OLLAMA_HOST", cls.host),
            repo_path=os.environ.get("REPO_PATH", cls.repo_path),
            max_fix_attempts=int(os.environ.get("MAX_FIX_ATTEMPTS", cls.max_fix_attempts)),
            max_candidates=int(os.environ.get("MAX_CANDIDATES", cls.max_candidates)),
            baseline_runs=int(os.environ.get("BASELINE_RUNS", cls.baseline_runs)),
            output_dir=os.environ.get("OUTPUT_DIR", cls.output_dir),
        )
