"""Minimal in-memory multipart/form-data parser.

Starlette's UploadFile spools parts larger than 1 MB to a temporary file on disk; the ephemeral
privacy mode forbids that, so uploads are read as one bounded byte string and split here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..errors import ApiError

_BOUNDARY = re.compile(r'boundary="?([^";]{1,200})"?', re.I)
_DISPO_NAME = re.compile(r'\bname="([^"]*)"', re.I)
_DISPO_FILE = re.compile(r'\bfilename="([^"]*)"', re.I)


@dataclass
class Part:
    name: str
    filename: str | None
    data: bytes


def sanitize_name(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in unicodedata.normalize("NFC", name) if ch.isprintable())
    name = name.strip().lstrip(".") or "upload"
    return name[:200]


def parse(content_type: str | None, body: bytes, max_parts: int) -> list[Part]:
    if not content_type or not content_type.lower().startswith("multipart/form-data"):
        raise ApiError(422, "invalid_content_type", "Use multipart/form-data with one or more 'file' parts.")
    m = _BOUNDARY.search(content_type)
    if not m:
        raise ApiError(422, "invalid_multipart", "Missing multipart boundary.")
    delim = b"--" + m.group(1).encode("latin-1")
    chunks = body.split(delim)
    if len(chunks) < 3 or not chunks[-1].startswith(b"--"):
        raise ApiError(422, "invalid_multipart", "Malformed multipart body.")
    parts: list[Part] = []
    for chunk in chunks[1:-1]:
        if not chunk.startswith(b"\r\n"):
            raise ApiError(422, "invalid_multipart", "Malformed multipart body.")
        chunk = chunk[2:]
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep or not data.endswith(b"\r\n"):
            raise ApiError(422, "invalid_multipart", "Malformed multipart part.")
        data = data[:-2]
        headers = {}
        for line in head.decode("utf-8", "replace").split("\r\n"):
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        dispo = headers.get("content-disposition", "")
        nm = _DISPO_NAME.search(dispo)
        fn = _DISPO_FILE.search(dispo)
        parts.append(Part(name=nm.group(1) if nm else "", filename=sanitize_name(fn.group(1)) if fn else None, data=data))
        if len(parts) > max_parts:
            raise ApiError(413, "too_many_files", f"At most {max_parts} files per capture.")
    return parts
