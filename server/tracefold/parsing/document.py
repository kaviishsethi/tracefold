"""Parsed documents with stable source locations.

Offsets are zero-based Unicode code points, end exclusive. Code/text also expose 1-based line numbers.
DOCX exposes paragraph IDs plus offsets inside the extracted paragraph text (no fabricated page numbers).
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from ..inputs.registry import CapturedFile


@dataclass
class Paragraph:
    pid: str
    start: int
    end: int


@dataclass
class ParsedDoc:
    file: CapturedFile
    text: str
    kind: str
    language: str | None
    line_starts: list[int] = field(default_factory=list)
    paragraphs: list[Paragraph] | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.line_starts:
            self.line_starts = [0] + [i + 1 for i, ch in enumerate(self.text) if ch == "\n"]

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.line_starts, offset)

    def line_span(self, line: int) -> tuple[int, int]:
        start = self.line_starts[line - 1]
        end = self.line_starts[line] - 1 if line < len(self.line_starts) else len(self.text)
        return start, end

    @property
    def line_count(self) -> int:
        return len(self.line_starts)

    def paragraph_at(self, offset: int) -> Paragraph | None:
        if not self.paragraphs:
            return None
        starts = [p.start for p in self.paragraphs]
        i = bisect.bisect_right(starts, offset) - 1
        return self.paragraphs[i] if i >= 0 else None

    def location(self, start: int, end: int) -> dict:
        if not (0 <= start < end <= len(self.text)):
            raise ValueError("location out of bounds")
        loc = {"file_id": self.file.file_id, "path": self.file.path, "start": start, "end": end,
               "line_start": None, "line_end": None, "paragraph_id": None}
        if self.kind == "docx":
            p = self.paragraph_at(start)
            if p is not None:
                loc["paragraph_id"] = p.pid
                loc["para_start"] = start - p.start
                loc["para_end"] = min(end, p.end) - p.start
        else:
            loc["line_start"] = self.line_of(start)
            loc["line_end"] = self.line_of(max(start, end - 1))
        return loc


def parse_text(f: CapturedFile) -> ParsedDoc:
    assert f.data is not None
    text = f.data.decode("utf-8")
    if text.startswith("﻿"):
        text = text[1:]
    # Normalize line endings while keeping a 1:1 meaning for line numbers.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return ParsedDoc(file=f, text=text, kind=f.kind or "text", language=f.language)
