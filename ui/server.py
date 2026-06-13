#!/usr/bin/env python3
"""Tiny web UI to watch the bug factory work.

    uvicorn ui.server:app --reload      # then open http://localhost:8000

Provider/model come from env vars so the page can drive Ollama by default:
    PROVIDER=ollama  OLLAMA_MODEL=gemma3:1b  OLLAMA_HOST=http://localhost:11434
Set PROVIDER=mock to demo without a model server.
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from bugfactory import run_pipeline
from bugfactory.llm import build_provider

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

app = FastAPI(title="Bug Factory")


def _provider():
    name = os.environ.get("PROVIDER", "ollama")
    if name == "ollama":
        return build_provider(
            "ollama",
            model=os.environ.get("OLLAMA_MODEL", "gemma3:1b"),
            host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        )
    return build_provider(name)


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/stream")
def stream(ticket: str = "BUG-101"):
    ticket_path = os.path.join(ROOT, "tickets", f"{ticket}.json")
    with open(ticket_path) as fh:
        ticket_data = json.load(fh)
    provider = _provider()
    repo = os.path.join(ROOT, "sample_repo")
    output_dir = os.path.join(ROOT, "output")

    def gen():
        meta = {"provider": provider.name, "model": provider.model}
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"
        try:
            for ev in run_pipeline(repo, ticket_data, provider, output_dir=output_dir):
                yield f"data: {json.dumps(ev.to_dict())}\n\n"
        except Exception as exc:  # surface provider/connection errors to the page
            err = {"stage": "done", "status": "error", "message": str(exc), "data": {}}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
