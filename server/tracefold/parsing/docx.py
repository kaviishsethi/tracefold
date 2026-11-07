"""DOCX extraction as data only.

Bounded: entry count, total uncompressed size and per-entry compression ratio are checked from the zip
directory before any allocation, and the document part is read with a hard cap. DOCTYPE declarations are
refused (no entity expansion). Macros, embedded objects and external relationships are never executed or
fetched; their presence is noted. Locations are paragraph IDs plus offsets inside extracted paragraph text.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

from ..config import Limits
from ..inputs.registry import CapturedFile
from .document import Paragraph, ParsedDoc

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14_PARAID = "{http://schemas.microsoft.com/office/word/2010/wordml}paraId"
PARA_SEP = "\n\n"


class DocxError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _bounded_read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> bytes:
    with zf.open(info) as fh:
        data = fh.read(cap + 1)
    if len(data) > cap:
        raise DocxError("docx_part_too_large")
    return data


def parse_docx(f: CapturedFile, limits: Limits) -> ParsedDoc:
    assert f.data is not None
    try:
        zf = zipfile.ZipFile(io.BytesIO(f.data))
    except zipfile.BadZipFile:
        raise DocxError("not_a_docx")
    infos = zf.infolist()
    if len(infos) > limits.docx_max_entries:
        raise DocxError("docx_too_many_entries")
    total = 0
    for i in infos:
        total += i.file_size
        if i.file_size > 1024 * 1024 and i.file_size / max(i.compress_size, 1) > limits.docx_max_ratio:
            raise DocxError("docx_compression_ratio")
    if total > limits.docx_max_uncompressed_bytes:
        raise DocxError("docx_too_large_uncompressed")
    names = {i.filename: i for i in infos}
    if "word/document.xml" not in names:
        raise DocxError("not_a_docx")
    notes: list[str] = []
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        notes.append("macros_present_ignored")
    if any(n.startswith("word/embeddings/") for n in names):
        notes.append("embedded_objects_ignored")
    rels = names.get("word/_rels/document.xml.rels")
    if rels is not None:
        rel_xml = _bounded_read(zf, rels, 1024 * 1024)
        if re.search(rb'TargetMode\s*=\s*"External"', rel_xml):
            notes.append("external_relationships_not_fetched")
    xml = _bounded_read(zf, names["word/document.xml"], min(limits.docx_max_uncompressed_bytes, limits.max_extracted_text_per_capture * 4))
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise DocxError("docx_doctype_refused")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise DocxError("docx_xml_invalid")

    parent: dict[ET.Element, ET.Element] = {c: p for p in root.iter() for c in p}

    def owner_paragraph(el: ET.Element) -> ET.Element | None:
        cur = parent.get(el)
        while cur is not None and cur.tag != W + "p":
            cur = parent.get(cur)
        return cur

    paras = list(root.iter(W + "p"))
    texts: dict[ET.Element, list[str]] = {p: [] for p in paras}
    for el in root.iter():
        if el.tag in (W + "t", W + "delText"):
            if el.tag == W + "delText":
                continue  # deleted tracked-change text is not current content
            p = owner_paragraph(el)
            if p is not None:
                texts[p].append(el.text or "")
        elif el.tag == W + "tab":
            p = owner_paragraph(el)
            if p is not None:
                texts[p].append("\t")
        elif el.tag in (W + "br", W + "cr"):
            p = owner_paragraph(el)
            if p is not None:
                texts[p].append("\n")

    out_parts: list[str] = []
    paragraphs: list[Paragraph] = []
    pos = 0
    seen_ids: set[str] = set()
    for idx, p in enumerate(paras):
        t = "".join(texts[p])
        if not t.strip():
            continue
        pid = p.get(W14_PARAID) or f"p{idx}"
        if pid in seen_ids:
            pid = f"{pid}-{idx}"
        seen_ids.add(pid)
        if out_parts:
            out_parts.append(PARA_SEP)
            pos += len(PARA_SEP)
        paragraphs.append(Paragraph(pid=pid, start=pos, end=pos + len(t)))
        out_parts.append(t)
        pos += len(t)
    text = "".join(out_parts)
    if len(text) > limits.max_extracted_text_per_capture:
        raise DocxError("docx_text_too_large")
    return ParsedDoc(file=f, text=text, kind="docx", language=None, paragraphs=paragraphs, notes=notes)
