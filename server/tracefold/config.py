"""Engine settings. Values are proposed pilot limits from docs/SHARED_ENGINE_PLAN.md §10."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Limits:
    max_queued_scans: int = 4
    max_files_per_capture: int = 10
    max_file_bytes: int = 5 * 1024 * 1024
    max_request_bytes: int = 20 * 1024 * 1024
    max_extracted_text_per_capture: int = 10 * 1024 * 1024
    max_captures: int = 2
    max_captured_raw_bytes: int = 40 * 1024 * 1024
    capture_ttl_seconds: int = 15 * 60
    scan_deadline_seconds: int = 5 * 60
    max_public_pages: int = 20
    max_public_text_per_page: int = 200 * 1024
    max_public_raw_bytes_per_page: int = 2 * 1024 * 1024
    max_provider_requests: int = 40
    max_public_cache_bytes: int = 50 * 1024 * 1024
    public_http_concurrency: int = 2
    max_model_candidates: int = 10
    max_model_requests: int = 25
    max_model_input_tokens: int = 40_000
    max_model_output_tokens: int = 2_000
    model_context_tokens: int = 8_192
    docx_max_entries: int = 200
    docx_max_uncompressed_bytes: int = 20 * 1024 * 1024
    docx_max_ratio: int = 100
    page_size_default: int = 50
    page_size_max: int = 100
    retained_scans: int = 100
    retained_days: int = 30


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("TRACEFOLD_DATA", "data")).resolve())
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")
    allowed_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    ollama_url: str = field(default_factory=lambda: os.environ.get("TRACEFOLD_OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("TRACEFOLD_OLLAMA_MODEL", "qwen2.5:7b-instruct"))
    model_timeout_seconds: float = 120.0
    start_runner: bool = True
    runner_poll_seconds: float = 0.2
    retrieval_in_process: bool = False  # tests may run the worker in-process with a mock transport
    fixture_root: Path | None = field(default_factory=lambda: Path(os.environ["TRACEFOLD_FIXTURES"]).resolve()
                                      if os.environ.get("TRACEFOLD_FIXTURES") else None)
    limits: Limits = field(default_factory=Limits)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tracefold.db"

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "public_blobs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
