"""File-type classification. Only declared types are accepted; everything else is reported as rejected."""
from __future__ import annotations

from pathlib import PurePosixPath

TEXT_EXT = {".txt": "text", ".md": "text", ".markdown": "text", ".rst": "text"}
CODE_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".go": "go", ".rb": "ruby", ".java": "java", ".rs": "rust", ".sh": "shell", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".toml": "toml", ".ini": "ini", ".cfg": "ini", ".env.example": "dotenv", ".sql": "sql",
}
DOCX_EXT = {".docx"}


def classify(path: str) -> tuple[str | None, str | None]:
    """Return (kind, language) or (None, None) for unsupported."""
    name = PurePosixPath(path).name.lower()
    if name.endswith(".env.example"):
        return "code", "dotenv"
    suffix = PurePosixPath(name).suffix
    if suffix in TEXT_EXT:
        return "text", None
    if suffix in CODE_EXT:
        return "code", CODE_EXT[suffix]
    if suffix in DOCX_EXT:
        return "docx", None
    return None, None


def check_text(data: bytes) -> str | None:
    """Return a rejection reason if bytes are not acceptable UTF-8 text."""
    if b"\x00" in data:
        return "binary_content"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "not_utf8"
    return None
