"""The LLM-driven steps. Each agent gives the model a small, bounded job and
falls back to deterministic logic when the (tiny) model returns nothing usable.
That division is what makes gemma3:1b viable: the scaffolding is reliable, the
model only makes narrow choices.

Every system prompt carries a [role:NAME] marker so the deterministic
MockProvider can play each role.
"""
from __future__ import annotations

import json
import os
import re

from .codebase import lexical_hits, parse_stack_trace


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _extract_code(text: str) -> str:
    fence = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    body = fence.group(1) if fence else text
    return body.strip("\n")


def intake(provider, ticket: dict) -> dict:
    system = (
        "[role:intake] You triage bug tickets. Read the ticket and reply with a "
        'JSON object: {"summary": "<one sentence>", "keywords": ["<identifier-like terms>"]}. '
        "Keywords should be function, class, or symbol names likely to appear in the code."
    )
    prompt = f"Title: {ticket.get('title','')}\nDescription: {ticket.get('description','')}"
    resp = provider.complete(system, prompt)
    parsed = _extract_json(resp.text) or {}

    keywords = [str(k).lower() for k in parsed.get("keywords", []) if isinstance(k, (str, int))]
    # Always augment with identifier-ish tokens from the ticket (robust for tiny models).
    keywords += [w.lower() for w in re.findall(r"[A-Za-z_]{3,}", prompt)]
    keywords = list(dict.fromkeys(keywords))  # de-dup, keep order
    summary = parsed.get("summary") or ticket.get("title", "")
    return {"summary": summary, "keywords": keywords, "raw": resp.text}


def rank_candidates(ticket: dict, keywords: list[str], repo_map: list, max_candidates: int = 5) -> list:
    """Deterministic, scalable localization: combine stack-trace, symbol-name,
    and lexical signals into a ranked list of source (non-test) functions."""
    text = (ticket.get("title", "") + " " + ticket.get("description", "") + " " + " ".join(keywords)).lower()
    frames = parse_stack_trace(ticket.get("title", "") + "\n" + ticket.get("description", ""))
    source_fns = [fn for fn in repo_map if not fn.is_test]

    scored = []
    for fn in source_fns:
        score = 0.0
        # whole-word match so "add" is not credited for "adding", "total" not for "subtotal"
        name_hits = len(re.findall(r"\b" + re.escape(fn.name.lower()) + r"\b", text))
        score += 10 * name_hits                                  # symbol name in ticket
        score += lexical_hits(fn.source(), keywords)             # ticket terms in body
        for fr in frames:                                        # stack-trace frames (strongest)
            same_file = os.path.basename(fr["file"]) == os.path.basename(fn.file)
            if fr["func"] and fr["func"] == fn.name and same_file:
                score += 100
            elif fr["func"] and fr["func"] == fn.name:
                score += 50
            elif same_file:
                score += 15
        if score > 0:
            scored.append((score, fn))

    scored.sort(key=lambda t: t[0], reverse=True)
    ranked = [fn for _, fn in scored]
    if not ranked:                                               # nothing matched: fall back to all source
        ranked = source_fns
    return ranked[:max_candidates]


def choose_candidate(provider, ticket: dict, candidates: list):
    """Let the model pick the single most likely culprit from the shortlist."""
    if len(candidates) == 1:
        return candidates[0]
    system = (
        "[role:localize] You locate the function responsible for a bug. "
        "Reply with ONLY the qualified name of the single most likely culprit from the list."
    )
    listing = "\n".join(f"- {fn.qualname}  ({fn.file})\n{fn.snippet(8)}" for fn in candidates)
    prompt = f"Bug: {ticket.get('title','')}\n{ticket.get('description','')}\n\nCandidates:\n{listing}"
    resp = provider.complete(system, prompt)
    pick = resp.text.strip().split()[0].strip("`(),.") if resp.text.strip() else ""
    return next((fn for fn in candidates if fn.qualname == pick), candidates[0])


def plan(provider, ticket: dict, target, func_src: str) -> str:
    system = (
        "[role:plan] You write a one or two sentence plan to fix a bug. "
        "Be concrete about what code change is needed."
    )
    prompt = (
        f"Ticket: {ticket.get('description','')}\n\n"
        f"Buggy `{target.qualname}` in {target.file}:\n{func_src}"
    )
    resp = provider.complete(system, prompt)
    return resp.text.strip() or f"Fix {target.qualname} per the ticket."


def code_fix(provider, ticket: dict, target, func_src: str, last_error: str | None = None) -> str:
    system = (
        "[role:code] You fix bugs. Rewrite the given Python function so it is "
        "correct. Reply with ONLY the corrected function in a ```python code block. "
        "Keep the same name and signature. Do not add explanations."
    )
    prompt = (
        f"Ticket: {ticket.get('description','')}\n\n"
        f"Function to fix (`{target.qualname}`):\n```python\n{func_src}\n```"
    )
    if last_error:
        prompt += f"\n\nYour previous attempt still failed tests:\n{last_error}\nTry again."
    resp = provider.complete(system, prompt)
    return _extract_code(resp.text)


def review(provider, ticket: dict, diff: str) -> str:
    system = (
        "[role:review] You review a bug fix. Reply starting with PASS or FAIL, "
        "then a short reason, judging whether the diff addresses the ticket."
    )
    prompt = f"Ticket: {ticket.get('description','')}\n\nProposed diff:\n{diff}"
    resp = provider.complete(system, prompt)
    return resp.text.strip() or "PASS"
