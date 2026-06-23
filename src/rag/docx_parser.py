import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docx import Document as DocxDocument


@dataclass
class DocxChunk:
    content: str
    chunk_id: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = hashlib.md5(
                (self.content[:100]).encode("utf-8")
            ).hexdigest()[:16]


class DocxParser:
    def __init__(self, min_chunk_tokens=250, max_chunk_tokens=1200, overlap_ratio=0.15):
        self.min_chunk_tokens = min_chunk_tokens
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_ratio = overlap_ratio
        self.na_concepts_map = {
            "капитуляция", "смирение", "Высшая Сила", "групповое сознание",
            "духовное пробуждение", "спонсорство", "только сегодня", "бессилие",
            "неуправляемость", "честность", "открытость", "готовность",
            "единство", "служение", "терапевтическая ценность", "выздоровление",
            "духовность", "принципы", "традиции", "шаги",
        }

    def parse(self, path: Path) -> list[DocxChunk]:
        doc = DocxDocument(str(path))
        hierarchy = {"book_title": path.stem, "part": None, "chapter": None, "section": None}
        definition_id = None
        chunks = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name if para.style else "Normal"
            detected = self._detect_heading(text, style_name, hierarchy)

            if detected:
                level, value = detected
                if level == "part":
                    hierarchy["part"] = value
                    hierarchy["chapter"] = None
                    hierarchy["section"] = None
                elif level == "chapter":
                    hierarchy["chapter"] = value
                    hierarchy["section"] = None
                    definition_id = None
                elif level == "section":
                    hierarchy["section"] = value
                continue

            if self._is_definition(text):
                definition_id = hashlib.md5((text[:100]).encode("utf-8")).hexdigest()[:16]
                chunk = self._make_chunk(text, hierarchy, "definition", definition_id, definition_id)
                chunks.append(chunk)
                continue

            chunk = self._make_chunk(text, hierarchy, "body", definition_id, None)
            chunks.append(chunk)

        return self._post_process(chunks)

    def _detect_heading(self, text: str, style_name: str, hierarchy: dict) -> Optional[tuple[str, str]]:
        style_lower = style_name.lower()
        if text.strip().upper().startswith("КНИГА"):
            return ("part", text)
        if "heading 1" in style_lower or "heading1" in style_lower:
            return ("chapter", text)
        if "heading 2" in style_lower or "heading2" in style_lower:
            return ("section", text)
        if "heading 3" in style_lower or "heading3" in style_lower:
            return ("section", text)
        if "heading 4" in style_lower or "heading4" in style_lower:
            return ("section", text)
        words = text.split()
        if 1 <= len(words) <= 5 and not text.rstrip().endswith((".", "!", "?", ":", ";", "»")):
            if any(kw in text.lower() for kw in ["шаг", "традици", "книга", "часть"]):
                return ("section", text)
        return None

    def _is_definition(self, text: str) -> bool:
        stripped = text.rstrip(".!?,")
        return text.startswith("«") and stripped.endswith("»")

    def _make_chunk(self, text, hierarchy, role, definition_id, chunk_id):
        element_type, element_number = self._classify_chapter(hierarchy.get("chapter"))
        parts = [f"«{hierarchy.get('book_title', '')}»"]
        if hierarchy.get("part"):
            parts.append(hierarchy["part"])
        if hierarchy.get("chapter"):
            parts.append(f"Глава «{hierarchy['chapter']}»")
        if hierarchy.get("section"):
            sec = hierarchy["section"]
            if any(sec.lower().startswith(p) for p in ["шаг", "глава", "традици", "книга"]):
                parts.append(sec)
            else:
                parts.append(f"Раздел «{sec}»")
        citation_label = ", ".join(parts)

        metadata = {
            "chunk_id": chunk_id or hashlib.md5((text[:100]).encode()).hexdigest()[:16],
            "book_title": hierarchy.get("book_title", ""),
            "part": hierarchy.get("part"),
            "chapter": hierarchy.get("chapter", ""),
            "section": hierarchy.get("section"),
            "page": None,
            "element_type": element_type,
            "element_number": element_number,
            "chunk_role": role,
            "citation_label": citation_label,
            "definition_ref_id": definition_id,
            "na_concepts": [c for c in self.na_concepts_map if c.lower() in text.lower()],
            "keywords": [],
            "source": hierarchy.get("book_title", ""),
        }
        return DocxChunk(content=text, chunk_id=metadata["chunk_id"], metadata=metadata)

    def _classify_chapter(self, chapter: Optional[str]) -> tuple:
        if not chapter:
            return ("main_text", None)
        chapter_lower = chapter.lower()
        if "шаг" in chapter_lower:
            for w in chapter_lower.split():
                if w.isdigit():
                    return ("step", int(w))
            return ("step", None)
        if "традици" in chapter_lower:
            for w in chapter_lower.split():
                if w.isdigit():
                    return ("tradition", int(w))
            return ("tradition", None)
        return ("main_text", None)

    def _post_process(self, chunks: list[DocxChunk]) -> list[DocxChunk]:
        if not chunks:
            return chunks

        merged = [chunks[0]]
        for chunk in chunks[1:]:
            prev_is_def = merged[-1].metadata.get("chunk_role") == "definition"
            curr_is_def = chunk.metadata.get("chunk_role") == "definition"

            if not prev_is_def and not curr_is_def and self._estimate_tokens(merged[-1].content) < self.min_chunk_tokens:
                merged[-1].content += " " + chunk.content
                continue

            if not curr_is_def and self._estimate_tokens(chunk.content) > self.max_chunk_tokens:
                split = self._split_chunk(chunk)
                merged.extend(split)
                continue

            merged.append(chunk)

        return merged

    def _split_chunk(self, chunk: DocxChunk) -> list[DocxChunk]:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', chunk.content) if s.strip()]
        if len(sentences) < 2:
            return [chunk]

        parts = []
        current = []
        current_tokens = 0
        overlap_tokens = int(self.max_chunk_tokens * self.overlap_ratio)

        for sent in sentences:
            sent_tokens = self._estimate_tokens(sent)
            if current_tokens + sent_tokens > self.max_chunk_tokens and current:
                text = " ".join(current)
                new_chunk = DocxChunk(
                    content=text,
                    metadata=dict(chunk.metadata),
                )
                new_chunk.metadata["chunk_id"] = hashlib.md5((text[:100]).encode()).hexdigest()[:16]
                parts.append(new_chunk)

                overlap = []
                overlap_tok = 0
                for s in reversed(current):
                    t = self._estimate_tokens(s)
                    if overlap_tok + t > overlap_tokens:
                        break
                    overlap.insert(0, s)
                    overlap_tok += t
                current = overlap
                current_tokens = overlap_tok

            current.append(sent)
            current_tokens += sent_tokens

        if current:
            text = " ".join(current)
            new_chunk = DocxChunk(
                content=text,
                metadata=dict(chunk.metadata),
            )
            new_chunk.metadata["chunk_id"] = hashlib.md5((text[:100]).encode()).hexdigest()[:16]
            parts.append(new_chunk)

        return parts

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * 1.3)


def main():
    import argparse
    import sys
    from loguru import logger

    logger.remove()
    logger.add(sys.stdout, format="{time} | {level} | {message}", level="INFO")

    parser = argparse.ArgumentParser(description="Parse .docx and index into FAISS")
    parser.add_argument("path", type=Path, help="Path to .docx file or directory")
    parser.add_argument("--clear", action="store_true", help="Clear existing index")

    args = parser.parse_args()
    path = args.path

    if not path.exists():
        logger.error(f"Path not found: {path}")
        return 1

    if path.is_dir():
        files = sorted(path.glob("*.docx"))
    else:
        files = [path]

    if not files:
        logger.error("No .docx files found")
        return 1

    from src.rag.service import RAGService
    rag = RAGService()

    if args.clear:
        rag.clear()

    docx_parser = DocxParser()
    for f in files:
        logger.info(f"Parsing: {f}")
        chunks = docx_parser.parse(f)
        texts = [c.content for c in chunks]
        metadatas = [c.metadata for c in chunks]
        rag.add_documents(texts, metadatas)
        logger.info(f"  Indexed {len(chunks)} chunks from {f.name}")

    logger.success(f"Done. Total chunks: {rag.get_document_count()}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
