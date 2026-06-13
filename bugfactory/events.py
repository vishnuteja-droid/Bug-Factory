"""A pipeline run is a stream of Events. The CLI prints them; the UI streams
them over SSE. One pipeline, two front-ends.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field


@dataclass
class Event:
    stage: str       # intake | localize | plan | code | validate | review | mr | done
    status: str      # start | info | success | error
    message: str
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)
