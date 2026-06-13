#!/usr/bin/env python3
"""Run the bug factory on a ticket from the command line.

    python run_demo.py                       # default: ollama gemma3:1b, BUG-101
    python run_demo.py --provider mock       # no model server needed
    python run_demo.py --model gemma3:1b --ticket tickets/BUG-101.json
"""
from __future__ import annotations

import argparse
import json
import os

from bugfactory import run_pipeline
from bugfactory.llm import build_provider

COLORS = {"start": "\033[36m", "info": "\033[37m", "success": "\033[32m", "error": "\033[31m"}
RESET = "\033[0m"


def main():
    ap = argparse.ArgumentParser(description="Bug factory demo")
    ap.add_argument("--provider", default="ollama", choices=["ollama", "mock"])
    ap.add_argument("--model", default="gemma3:1b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--ticket", default="tickets/BUG-101.json")
    ap.add_argument("--repo", default="sample_repo")
    ap.add_argument("--max-candidates", type=int, default=3)
    ap.add_argument("--max-fix-attempts", type=int, default=3)
    ap.add_argument("--baseline-runs", type=int, default=2)
    args = ap.parse_args()

    kwargs = {"model": args.model} if args.provider == "ollama" else {}
    if args.provider == "ollama":
        kwargs["host"] = args.host
    provider = build_provider(args.provider, **kwargs)

    with open(args.ticket) as fh:
        ticket = json.load(fh)

    print(f"\n=== Bug Factory :: provider={provider.name} model={provider.model} ===\n")
    for ev in run_pipeline(args.repo, ticket, provider,
                           max_fix_attempts=args.max_fix_attempts,
                           max_candidates=args.max_candidates,
                           baseline_runs=args.baseline_runs):
        color = COLORS.get(ev.status, "")
        print(f"{color}[{ev.stage:>8}] {ev.status:<7}{RESET} {ev.message}")
        if ev.stage == "mr" and ev.status == "success":
            print(f"\n  -> diff:        {ev.data.get('diff_path')}")
            print(f"  -> description: {ev.data.get('mr_path')}\n")


if __name__ == "__main__":
    main()
