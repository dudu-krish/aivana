"""Text chunking for knowledge base documents — flat and hierarchical (parent-child)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def chunk_text(text: str, *, max_chars: int = 900) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("## ") or line.startswith("# "):
            if current:
                sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    if not sections and (text or "").strip():
        sections = [text.strip()]

    chunks: list[str] = []
    for sec in sections:
        if len(sec) <= max_chars:
            chunks.append(sec)
            continue
        for para in re.split(r"\n\s*\n", sec):
            para = para.strip()
            if not para:
                continue
            if len(para) <= max_chars:
                chunks.append(para)
            else:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i : i + max_chars])
    return [c for c in chunks if c.strip()]


def _split_child_chunks(text: str, *, max_chars: int, overlap: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    children: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            children.append(current)
        if len(sentence) <= max_chars:
            current = sentence
            continue
        step = max(max_chars - overlap, 1)
        for i in range(0, len(sentence), step):
            children.append(sentence[i : i + max_chars])
        current = ""

    if current:
        children.append(current)

    if not children:
        step = max(max_chars - overlap, 1)
        for i in range(0, len(text), step):
            children.append(text[i : i + max_chars])
    return [c for c in children if c.strip()]


@dataclass
class ChildChunk:
    child_index: int
    text: str


@dataclass
class ParentChunk:
    parent_index: int
    text: str
    children: list[ChildChunk] = field(default_factory=list)


def hierarchical_chunk(
    text: str,
    *,
    parent_max_chars: int = 1800,
    child_max_chars: int = 280,
    child_overlap: int = 40,
) -> list[ParentChunk]:
    """Split into parent sections (context) and child chunks (semantic search)."""
    parent_texts = chunk_text(text, max_chars=parent_max_chars)
    blocks: list[ParentChunk] = []
    for pi, parent_text in enumerate(parent_texts):
        child_texts = _split_child_chunks(
            parent_text,
            max_chars=child_max_chars,
            overlap=child_overlap,
        )
        blocks.append(
            ParentChunk(
                parent_index=pi,
                text=parent_text,
                children=[
                    ChildChunk(child_index=ci, text=child_text)
                    for ci, child_text in enumerate(child_texts)
                ],
            )
        )
    return blocks


def hierarchical_to_records(
    blocks: list[ParentChunk],
    *,
    document_id: str,
) -> list[dict[str, Any]]:
    """Flatten hierarchical blocks into parent/child records for storage."""
    records: list[dict[str, Any]] = []
    for block in blocks:
        parent_id = f"{document_id}__p{block.parent_index}"
        records.append(
            {
                "parent_id": parent_id,
                "document_id": document_id,
                "parent_text": block.text,
                "children": [
                    {
                        "child_id": f"{parent_id}__c{child.child_index}",
                        "parent_id": parent_id,
                        "document_id": document_id,
                        "child_text": child.text,
                        "child_index": child.child_index,
                    }
                    for child in block.children
                ],
            }
        )
    return records
