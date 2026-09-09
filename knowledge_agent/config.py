from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    chunk_size: int
    chunk_overlap: int
    top_k: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.getenv("KNOWLEDGE_DATA_DIR", "data/knowledge-agent")),
            host=os.getenv("KNOWLEDGE_HOST", "127.0.0.1"),
            port=int(os.getenv("KNOWLEDGE_PORT", "8090")),
            llm_base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "120")),
            top_k=int(os.getenv("RAG_TOP_K", "5")),
        )
