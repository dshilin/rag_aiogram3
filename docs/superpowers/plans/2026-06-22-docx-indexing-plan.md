# Docx Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace PDF→MD→clean→chunk pipeline with direct .docx parser preserving book hierarchy, rich metadata, and definition expansion.

**Architecture:** `DocxParser` in `src/rag/docx_parser.py` reads .docx via `python-docx`, detects heading hierarchy and step definitions, splits/merges paragraphs into chunks with full metadata (`citation_label`, `definition_ref_id`, `na_concepts`). `RAGService.query_with_metadata()` gains `metadata_filter` and `expand_definitions`. CLI: `python -m src.rag.docx_parser`.

**Tech Stack:** python-docx, FAISS (unchanged), pytest

**Spec:** `docs/superpowers/specs/2026-06-22-docx-indexing-design.md`

---

### Task 1: Add python-docx dependency

**Files:**
- Modify: `requirements.txt`
- Create: `tests/test_docx_parser.py`

- [ ] **Step 1: Add python-docx to requirements.txt**

Append to `requirements.txt`:
```
python-docx>=1.1.0
```

- [ ] **Step 2: Create test file with shared fixtures**

```python
from pathlib import Path
from docx import Document as DocxDocument

import pytest

from src.rag.docx_parser import DocxParser

FIXTURE_DOCX_DIR = Path(__file__).parent / "fixtures"


def _make_docx(paragraphs: list[tuple], tmp_path: Path) -> Path:
    """Create a .docx for testing. Each tuple: (text, style) where style is 'h1'..'h4' or None for body."""
    doc = DocxDocument()
    for text, style in paragraphs:
        if style and style.startswith("h"):
            doc.add_heading(text, level=int(style[1]))
        else:
            p = doc.add_paragraph(text)
    path = tmp_path / "test.docx"
    doc.save(str(path))
    return path


@pytest.fixture
def parser():
    return DocxParser()
```

- [ ] **Step 3: Install and verify**

```bash
pip install python-docx
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt tests/test_docx_parser.py
git commit -m "chore: add python-docx, test scaffold for DocxParser"
```

---

### Task 2: Heading hierarchy detection

**Files:**
- Modify: `tests/test_docx_parser.py`
- Create: `src/rag/docx_parser.py`

- [ ] **Step 1: Write failing test — H1 → book_title**

```python
class TestHierarchy:
    def test_h1_detected_as_book_title(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст АН", "h1"),
            ("Текст абзаца.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert len(chunks) == 1
        assert chunks[0].metadata["book_title"] == "Базовый текст АН"
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_docx_parser.py::TestHierarchy -v
# FAIL — DocxParser not defined
```

- [ ] **Step 3: Write minimal DocxParser**

```python
import hashlib
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
        hierarchy = {"book_title": "", "part": None, "chapter": None, "section": None}
        definition_id = None
        definition_text = None
        chunks = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name if para.style else "Normal"
            detected = self._detect_heading(text, style_name, hierarchy)

            if detected:
                level, value = detected
                if level == "book_title":
                    hierarchy = {"book_title": value, "part": None, "chapter": None, "section": None}
                elif level == "part":
                    hierarchy["part"] = value
                    hierarchy["chapter"] = None
                    hierarchy["section"] = None
                elif level == "chapter":
                    hierarchy["chapter"] = value
                    hierarchy["section"] = None
                    definition_id = None
                    definition_text = None
                elif level == "section":
                    hierarchy["section"] = value
                continue

            if self._is_definition(text, hierarchy):
                definition_id = hashlib.md5((text[:100]).encode("utf-8")).hexdigest()[:16]
                definition_text = text
                chunk = self._make_chunk(text, hierarchy, "definition", definition_id, definition_id)
                chunks.append(chunk)
                continue

            chunk = self._make_chunk(text, hierarchy, "body", definition_id, None)
            chunks.append(chunk)

        return self._post_process(chunks)

    def _detect_heading(self, text: str, style_name: str, hierarchy: dict) -> Optional[tuple]:
        style_lower = style_name.lower()
        if "heading 1" in style_lower or "heading1" in style_lower:
            return ("book_title", text)
        if "heading 2" in style_lower or "heading2" in style_lower:
            return ("part", text)
        if "heading 3" in style_lower or "heading3" in style_lower:
            return ("chapter", text)
        if "heading 4" in style_lower or "heading4" in style_lower:
            return ("section", text)
        return None

    def _is_definition(self, text: str, hierarchy: dict) -> bool:
        return text.startswith("«") and text.endswith("»")

    def _make_chunk(self, text, hierarchy, role, definition_id, chunk_id):
        element_type, element_number = self._classify_chapter(hierarchy.get("chapter"))
        parts = [f"«{hierarchy.get('book_title', '')}»"]
        if hierarchy.get("chapter"):
            parts.append(f"Глава «{hierarchy['chapter']}»")
        if hierarchy.get("section"):
            parts.append(f"Раздел «{hierarchy['section']}»")
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

    def _classify_chapter(self, chapter: str) -> tuple:
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
        if "введен" in chapter_lower:
            return ("main_text", None)
        return ("main_text", None)

    def _post_process(self, chunks: list[DocxChunk]) -> list[DocxChunk]:
        # ponytail: merge short, split long. For MVP skip — paragraphs are the unit.
        return chunks

    def _estimate_tokens(self, text: str) -> int:
        # ponytail: rough estimate for chunk sizing
        return int(len(text.split()) * 1.3)
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/test_docx_parser.py::TestHierarchy -v
# PASS
```

- [ ] **Step 5: Add test for deep nesting**

- [ ] **Step 6: Implement heuristic heading detection**

Add to `_detect_heading`:
```python
# Heuristic: isolated short line without punctuation, preceded by blank
words = text.split()
if 1 <= len(words) <= 5 and not text.rstrip().endswith((".", "!", "?", ":", ";", "»")):
    if any(kw in text.lower() for kw in ["шаг", "традици", "книга", "часть"]):
        return ("chapter", text)
```

- [ ] **Step 7: Run all hierarchy tests, commit**

```bash
git add src/rag/docx_parser.py tests/test_docx_parser.py
git commit -m "feat: DocxParser heading hierarchy detection"
```

---

### Task 3: Step definition + definition_ref_id + citation_label

**Files:**
- Modify: `src/rag/docx_parser.py`
- Modify: `tests/test_docx_parser.py`

- [ ] **Step 1: Write failing tests**

```python
class TestStepDefinition:
    def test_first_paragraph_in_quotes_is_definition(self, parser, tmp_path):
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Текст главы.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert chunks[0].metadata["chunk_role"] == "definition"
        assert chunks[1].metadata["chunk_role"] == "body"

    def test_definition_ref_id_propagated(self, parser, tmp_path):
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Текст главы.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        def_chunk = [c for c in chunks if c.metadata["chunk_role"] == "definition"][0]
        body_chunk = [c for c in chunks if c.metadata["chunk_role"] == "body"][0]
        assert body_chunk.metadata["definition_ref_id"] == def_chunk.chunk_id

    def test_citation_label_format(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст АН", "h1"),
            ("Шаг Первый", "h3"),
            ("Бессилие и неуправляемость", "h4"),
            ("Текст раздела.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert chunks[0].metadata["citation_label"] == (
            "«Базовый текст АН», Глава «Шаг Первый», Раздел «Бессилие и неуправляемость»"
        )
```

- [ ] **Step 2: Run to confirm fail**

- [ ] **Step 3: Implement (already done in Task 2 — verify passes)**

- [ ] **Step 4: Run tests, commit**

```bash
git add src/rag/docx_parser.py tests/test_docx_parser.py
git commit -m "feat: step definition, definition_ref_id, citation_label"
```

---

### Task 4: Chunk merging/splitting + cross-reference + na_concepts

**Files:**
- Modify: `src/rag/docx_parser.py`
- Modify: `tests/test_docx_parser.py`

- [ ] **Step 1: Write failing tests**

```python
class TestChunking:
    def test_short_paragraphs_merged(self, parser, tmp_path):
        # Each paragraph < 250 tokens → merged into one chunk
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Короткий текст.", None),
            ("Еще короткий.", None),
            ("Третий короткий.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        body_chunks = [c for c in chunks if c.metadata["chunk_role"] == "body"]
        assert len(body_chunks) < 3  # merged

    def test_long_paragraph_split(self, parser, tmp_path):
        long_text = "Предложение. " * 1000  # ~2000 tokens
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали.»", None),
            (long_text, None),
        ], tmp_path)
        chunks = parser.parse(path)
        body_chunks = [c for c in chunks if c.metadata["chunk_role"] == "body"]
        assert len(body_chunks) > 1

    def test_na_concepts_detected(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст АН", "h1"),
            ("Капитуляция и смирение — ключ к выздоровлению.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert "капитуляция" in chunks[0].metadata["na_concepts"]
        assert "смирение" in chunks[0].metadata["na_concepts"]
        assert "выздоровление" in chunks[0].metadata["na_concepts"]
```

- [ ] **Step 2: Run to confirm fail**

- [ ] **Step 3: Implement `_post_process`**

Replace the stub `_post_process` in `docx_parser.py`:

```python
    def _post_process(self, chunks: list[DocxChunk]) -> list[DocxChunk]:
        if not chunks:
            return chunks

        merged = [chunks[0]]
        for chunk in chunks[1:]:
            if (self._estimate_tokens(merged[-1].content) < self.min_chunk_tokens
                    and merged[-1].metadata.get("chunk_role") != "definition"
                    and chunk.metadata.get("chunk_role") != "definition"):
                merged[-1].content += " " + chunk.content
                continue

            if (self._estimate_tokens(chunk.content) > self.max_chunk_tokens
                    and chunk.metadata.get("chunk_role") != "definition"):
                split = self._split_chunk(chunk)
                merged.extend(split)
                continue

            merged.append(chunk)

        return merged

    def _split_chunk(self, chunk: DocxChunk) -> list[DocxChunk]:
        sentences = [s.strip() for s in chunk.content.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        parts = []
        current = []
        current_tokens = 0
        overlap_tokens = int(self.max_chunk_tokens * self.overlap_ratio)

        for sent in sentences:
            tokens = self._estimate_tokens(sent)
            if current_tokens + tokens > self.max_chunk_tokens and current:
                text = ". ".join(current) + "."
                new_chunk = DocxChunk(content=text, metadata=dict(chunk.metadata))
                new_chunk.metadata["chunk_id"] = hashlib.md5(
                    (text[:100]).encode("utf-8")
                ).hexdigest()[:16]
                parts.append(new_chunk)

                # overlap: keep last N sentences
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
            current_tokens += tokens

        if current:
            text = ". ".join(current) + "."
            new_chunk = DocxChunk(content=text, metadata=dict(chunk.metadata))
            new_chunk.metadata["chunk_id"] = hashlib.md5(
                (text[:100]).encode("utf-8")
            ).hexdigest()[:16]
            parts.append(new_chunk)

        return parts
```

- [ ] **Step 4: Run tests to verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/rag/docx_parser.py tests/test_docx_parser.py
git commit -m "feat: chunk merge/split, na_concepts detection"
```

---

### Task 5: RAGService — metadata_filter + definition expansion

**Files:**
- Modify: `src/rag/service.py`
- Modify: `tests/test_rag.py`

- [ ] **Step 1: Write failing integration tests**

Add to `tests/test_rag.py`:

```python
class TestMetadataFilter:
    def test_filter_by_book_title(self, rag_service):
        rag_service.add_documents(
            ["Текст про первый шаг.", "Текст про второй шаг."],
            [{"book_title": "Базовый текст АН"}, {"book_title": "Это работает"}],
        )
        results = rag_service.query_with_metadata(
            "первый шаг", top_k=5, metadata_filter={"book_title": "Базовый текст АН"}
        )
        assert all(r.metadata.get("book_title") == "Базовый текст АН" for r in results)

    def test_filter_excludes_non_matching(self, rag_service):
        rag_service.add_documents(
            ["Текст про капитуляцию.", "Текст про смирение."],
            [{"book_title": "Базовый текст АН"}, {"book_title": "Это работает"}],
        )
        results = rag_service.query_with_metadata(
            "капитуляция", top_k=5, metadata_filter={"book_title": "Несуществующая книга"}
        )
        assert len(results) == 0


class TestDefinitionExpansion:
    def test_definition_prepended_to_body(self, rag_service):
        def_id = "def_001"
        rag_service.add_documents(
            ["Текст главы."],
            [{"definition_ref_id": def_id, "chunk_role": "body", "book_title": "Тест"}],
        )
        rag_service.add_documents(
            ["«Определение шага.»"],
            [{"chunk_id": def_id, "chunk_role": "definition", "book_title": "Тест"}],
        )
        results = rag_service.query_with_metadata(
            "текст главы", top_k=5, expand_definitions=True
        )
        assert any("[Определение]" in r.content for r in results)
```

- [ ] **Step 2: Update ChunkResult and query_with_metadata**

```python
@dataclass
class ChunkResult:
    content: str
    source: str
    page: int
    chunk_id: str
    score: float = 0.0
    metadata: dict = None  # NEW
```

Replace `query_with_metadata` in `src/rag/service.py`:

```python
    @trace
    def query_with_metadata(
        self,
        question: str,
        top_k: Optional[int] = None,
        score_threshold: float = 0.0,
        metadata_filter: Optional[dict] = None,
        expand_definitions: bool = True,
    ) -> list[ChunkResult]:
        log_call_flow(f"RAG query: '{question[:50]}...' top_k={top_k or settings.top_k}")

        if self.vectorstore is None:
            log_call_flow("Vector store is None, returning empty results")
            return []

        k = top_k or settings.top_k
        results = self.vectorstore.similarity_search_with_score(question, k=k * 2)

        chunk_results = []
        for doc, score in results:
            meta = doc.metadata or {}
            if metadata_filter:
                if not all(meta.get(k) == v for k, v in metadata_filter.items()):
                    continue
            if score < score_threshold:
                continue
            chunk_results.append(
                ChunkResult(
                    content=doc.page_content,
                    source=meta.get("source", meta.get("book_title", "unknown")),
                    page=meta.get("page", 0),
                    chunk_id=meta.get("chunk_id", "unknown"),
                    score=score,
                    metadata=meta,
                )
            )

        chunk_results.sort(key=lambda x: x.score, reverse=True)

        # dedup by (source, page)
        seen = set()
        deduped = []
        for r in chunk_results:
            key = (r.source, r.page)
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        # expand definitions
        if expand_definitions and self.vectorstore:
            for r in deduped:
                def_ref_id = (r.metadata or {}).get("definition_ref_id")
                if def_ref_id:
                    for idx, doc_id in self.vectorstore.index_to_docstore_id.items():
                        if doc_id == def_ref_id:
                            doc = self.vectorstore.docstore.search(doc_id)
                            if doc:
                                def_content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
                                r.content = f"[Определение]\n{def_content}\n\n{r.content}"
                            break

        log_call_flow(f"RAG query returned {len(deduped)} results (deduped from {len(chunk_results)})")
        return deduped[:k]
```

- [ ] **Step 3: Run tests to verify pass**

```bash
pytest tests/test_rag.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/rag/service.py tests/test_rag.py
git commit -m "feat: metadata_filter + definition expansion in RAGService"
```

---

### Task 6: CLI + integration test

**Files:**
- Modify: `src/rag/docx_parser.py`
- Create: `tests/test_docx_parser.py` (add to end)

- [ ] **Step 1: Add CLI `main()` to docx_parser.py**

```python
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
    sys.exit(main())
```

- [ ] **Step 2: Add rag_service fixture + integration tests**

Add to `tests/test_docx_parser.py`:

```python
import shutil
import pytest
from src.rag.service import RAGService


@pytest.fixture
def rag_service(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.rag.service.settings.embeddings_db_path",
        str(tmp_path),
    )
    service = RAGService()
    yield service
    service.clear()


class TestIntegration:
    def test_parse_then_index_then_search(self, rag_service, tmp_path):
        path = _make_docx([
            ("Базовый текст", "h1"),
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Капитуляция — это ключ к выздоровлению.", None),
        ], tmp_path)
        parser = DocxParser()
        chunks = parser.parse(path)
        texts = [c.content for c in chunks]
        metadatas = [c.metadata for c in chunks]
        rag_service.add_documents(texts, metadatas)

        results = rag_service.query_with_metadata(
            "капитуляция", top_k=5, metadata_filter={"book_title": "Базовый текст"}
        )
        assert len(results) > 0
        assert results[0].metadata.get("book_title") == "Базовый текст"

    def test_definition_expansion_pipeline(self, rag_service, tmp_path):
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Текст с капитуляцией.", None),
        ], tmp_path)
        parser = DocxParser()
        chunks = parser.parse(path)
        texts = [c.content for c in chunks]
        metadatas = [c.metadata for c in chunks]
        rag_service.add_documents(texts, metadatas)

        results = rag_service.query_with_metadata(
            "капитуляция", top_k=5, expand_definitions=True
        )
        body_results = [r for r in results if "[Определение]" in r.content]
        assert len(body_results) > 0
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/test_docx_parser.py tests/test_rag.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/rag/docx_parser.py tests/test_docx_parser.py
git commit -m "feat: CLI main() + integration tests for DocxParser"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```

- [ ] **Step 2: Lint/type-check (if available)**

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: finalize docx indexing implementation"
```
