"""The LLM-driven steps. Each agent gives the model a small, bounded job and
falls back to deterministic logic when the (tiny) model returns nothing usable.
That division is what makes gemma3:1b viable: the scaffolding is reliable, the
model only makes narrow choices.

Every system prompt carries a [role:NAME] marker so the deterministic
MockProvider can play each role.
"""
from __future__ import annotations

import json
import re


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _extract_code(text: str) -> str:
    """Pull a code block out of model output, tolerating missing fences."""
    fence = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    body = fence.group(1) if fence else text
    return body.strip("\n")


def intake(provider, ticket: dict) -> dict:
    """Summarize the ticket and extract search keywords."""
    system = (
        "[role:intake] You triage bug tickets. Read the ticket and reply with a "
        'JSON object: {"summary": "<one sentence>", "keywords": ["<identifier-like terms>"]}. '
        "Keywords should be function or symbol names likely to appear in the code."
    )
    prompt = f"Title: {ticket.get('title','')}\nDescription: {ticket.get('description','')}"
    resp = provider.complete(system, prompt)
    parsed = _extract_json(resp.text) or {}

    keywords = [str(k).lower() for k in parsed.get("keywords", []) if isinstance(k, (str, int))]
    if not keywords:
        # Deterministic fallback: identifier-ish tokens straight from the ticket text.
        keywords = list({w.lower() for w in re.findall(r"[A-Za-z_]{3,}", prompt)})
    summary = parsed.get("summary") or ticket.get("title", "")
    return {"summary": summary, "keywords": keywords, "raw": resp.text}


def localize(provider, ticket: dict, keywords: list[str], repo_map: list) -> tuple[object, list]:
    """Score functions by name-overlap with the ticket, then let the model pick
    from the top candidates. Returns (chosen RepoFunction, ranked candidates)."""
    haystack = (ticket.get("title", "") + " " + ticket.get("description", "") + " " + " ".join(keywords)).lower()

    scored = []
    for fn in repo_map:
        score = haystack.count(fn.function.lower())
        if score:
            scored.append((score, fn))
    scored.sort(key=lambda t: t[0], reverse=True)
    candidates = [fn for _, fn in scored] or list(repo_map)
    top = candidates[:5]

    system = (
        "[role:localize] You locate the function responsible for a bug. "
        "Reply with ONLY the name of the single most likely function from the list."
    )
    listing = "\n".join(f"- {fn.function}  ({fn.file})" for fn in top)
    prompt = f"Bug: {ticket.get('title','')}\n{ticket.get('description','')}\n\nCandidate functions:\n{listing}"
    resp = provider.complete(system, prompt)

    pick = resp.text.strip().split()[0].strip("`(),.") if resp.text.strip() else ""
    chosen = next((fn for fn in top if fn.function == pick), top[0])
    return chosen, top


def plan(provider, ticket: dict, target, func_src: str) -> str:
    system = (
        "[role:plan] You write a one or two sentence plan to fix a bug. "
        "Be concrete about what code change is needed."
    )
    prompt = (
        f"Ticket: {ticket.get('description','')}\n\n"
        f"Buggy function `{target.function}` in {target.file}:\n{func_src}"
    )
    resp = provider.complete(system, prompt)
    return resp.text.strip() or f"Fix the {target.function} function per the ticket."


def code_fix(provider, ticket: dict, target, func_src: str, last_error: str | None = None) -> str:
    """Return corrected source for the single target function."""
    system = (
        "[role:code] You fix bugs. Rewrite the given Python function so it is "
        "correct. Reply with ONLY the corrected function in a ```python code block. "
        "Keep the same name and signature. Do not add explanations."
    )
    prompt = (
        f"Ticket: {ticket.get('description','')}\n\n"
        f"Function to fix:\n```python\n{func_src}\n```"
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
