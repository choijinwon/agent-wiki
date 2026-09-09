from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def chunk_text(value: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Split text near paragraph/sentence boundaries with a small context overlap."""
    if size < 100:
        raise ValueError("chunk size must be at least 100 characters")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk overlap must be between 0 and size")

    text = normalize_text(value)
    if not text:
        return []

    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        hard_end = min(cursor + size, len(text))
        end = hard_end
        if hard_end < len(text):
            floor = cursor + int(size * 0.55)
            candidates = [
                text.rfind("\n\n", floor, hard_end),
                text.rfind(". ", floor, hard_end),
                text.rfind("다. ", floor, hard_end),
                text.rfind("요. ", floor, hard_end),
            ]
            boundary = max(candidates)
            if boundary >= floor:
                end = boundary + (2 if text[boundary : boundary + 2] == "\n\n" else 1)

        chunk = text[cursor:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        next_cursor = max(end - overlap, cursor + 1)
        while next_cursor < end and not text[next_cursor].isspace():
            next_cursor += 1
        cursor = min(next_cursor, end)
    return chunks
