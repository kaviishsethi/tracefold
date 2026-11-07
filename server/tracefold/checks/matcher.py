"""Exact passage matcher: versioned normalization, token shingles, actual-token span confirmation.

Shared shingle hashes only nominate candidates; a match is reported only after the normalized tokens are
compared directly and extended to a maximal contiguous span of at least ``min_tokens`` tokens. Offsets map
back to the original extracted text on both sides.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NORMALIZATION_VERSION = "norm_v1"
MATCHER_VERSION = "exact_v1"


@dataclass(frozen=True)
class MatcherConfig:
    shingle: int = 8
    min_tokens_text: int = 12
    min_tokens_code: int = 24
    boilerplate_ratio: float = 0.5


CONFIG = MatcherConfig()

_TEXT_TOKEN = re.compile(r"\w+", re.UNICODE)
_CODE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[^\sA-Za-z0-9_]", re.UNICODE)


@dataclass
class Token:
    norm: str
    start: int
    end: int


def tokenize(text: str, policy: str) -> list[Token]:
    """text_v1: NFKC + casefold word tokens (punctuation/whitespace ignored).
    code_v1: NFKC, case-preserving identifiers/numbers/punctuation; whitespace-insensitive only."""
    if policy == "code_v1":
        return [Token(unicodedata.normalize("NFKC", m.group()), m.start(), m.end()) for m in _CODE_TOKEN.finditer(text)]
    return [Token(unicodedata.normalize("NFKC", m.group()).casefold(), m.start(), m.end()) for m in _TEXT_TOKEN.finditer(text)]


def policy_for(kind: str) -> str:
    return "code_v1" if kind == "code" else "text_v1"


BOILERPLATE = [
    "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files",
    "THE SOFTWARE IS PROVIDED AS IS, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY",
    "Licensed under the Apache License, Version 2.0 (the License); you may not use this file except in compliance with the License",
    "Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an AS IS BASIS",
    "This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License",
    "Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met",
    "All rights reserved",
]


def _shingles(tokens: list[Token], k: int) -> list[tuple[str, ...]]:
    return [tuple(t.norm for t in tokens[i:i + k]) for i in range(len(tokens) - k + 1)]


_BOILER_CACHE: dict[str, set[tuple[str, ...]]] = {}


def boilerplate_shingles(policy: str) -> set[tuple[str, ...]]:
    if policy not in _BOILER_CACHE:
        s: set[tuple[str, ...]] = set()
        for phrase in BOILERPLATE:
            s.update(_shingles(tokenize(phrase, "text_v1" if policy == "text_v1" else "text_v1"), CONFIG.shingle))
        _BOILER_CACHE[policy] = s
    return _BOILER_CACHE[policy]


@dataclass
class Match:
    local_start: int   # char offsets in local extracted text
    local_end: int
    public_start: int  # char offsets in public extracted text
    public_end: int
    tokens: int
    normalized: str    # normalized matched token sequence (anchor material; private, never sent out)


@dataclass
class MatchResult:
    matches: list[Match]
    boilerplate_skipped: int


def find_matches(local_text: str, public_text: str, policy: str, cfg: MatcherConfig = CONFIG) -> MatchResult:
    k = cfg.shingle
    min_tokens = cfg.min_tokens_code if policy == "code_v1" else cfg.min_tokens_text
    L = tokenize(local_text, policy)
    P = tokenize(public_text, policy)
    if len(L) < min_tokens or len(P) < min_tokens:
        return MatchResult([], 0)
    index: dict[tuple[str, ...], list[int]] = {}
    for j, sh in enumerate(_shingles(P, k)):
        index.setdefault(sh, []).append(j)
    # Boilerplate is compared in text_v1 space regardless of policy.
    boiler = boilerplate_shingles("text_v1")
    matches: list[Match] = []
    skipped = 0
    i = 0
    n_l, n_p = len(L), len(P)
    while i <= n_l - k:
        sh = tuple(t.norm for t in L[i:i + k])
        best_len, best_j = 0, -1
        for j in index.get(sh, ()):
            # Confirm by direct token comparison, then extend forward maximally.
            n = 0
            while i + n < n_l and j + n < n_p and L[i + n].norm == P[j + n].norm:
                n += 1
            if n > best_len:
                best_len, best_j = n, j
        if best_len >= min_tokens:
            span = L[i:i + best_len]
            text_space = tokenize(local_text[span[0].start:span[-1].end], "text_v1")
            shs = _shingles(text_space, k)
            if shs and sum(1 for s in shs if s in boiler) / len(shs) >= cfg.boilerplate_ratio:
                skipped += 1
            else:
                matches.append(Match(
                    local_start=span[0].start, local_end=span[-1].end,
                    public_start=P[best_j].start, public_end=P[best_j + best_len - 1].end,
                    tokens=best_len, normalized=" ".join(t.norm for t in span),
                ))
            i += best_len
        else:
            i += 1
    return MatchResult(matches, skipped)


def segment_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """The enclosing blank-line-delimited block (paragraph) around a span."""
    s = text.rfind("\n\n", 0, start)
    s = 0 if s < 0 else s + 2
    e = text.find("\n\n", end)
    e = len(text) if e < 0 else e
    return s, e


def segment_coverage(text: str, m: Match, policy: str) -> float:
    s, e = segment_bounds(text, m.local_start, m.local_end)
    total = len(tokenize(text[s:e], policy)) or 1
    return round(min(1.0, m.tokens / total), 3)
