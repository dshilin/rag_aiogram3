# md_chunker Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for syntax tracking.

**Goal:** Bring `md_chunker.py` metadata richness up to parity with `docx_parser.py` (hierarchy, definitions, NA concepts, keywords, token-based merge/split).

**Architecture:** Extract shared components (`NA_CONCEPTS`, `_extract_keywords`) to separate modules so both parsers share them. Rewrite `Chunk` dataclass with full metadata. Add heading detection, definition detection, hierarchy tracking, and token-based merge/split to `MarkdownChunker`.

**Tech Stack:** Python 3.11, pytest, natasha, no new dependencies.

**Files created:**
- `src/rag/concepts.py`
- `src/utils/text.py`

**Files modified:**
- `src/rag/docx_parser.py`
- `src/rag/md_chunker.py`
- `tests/test_md_chunker.py`
- `src/utils/__init__.py`

---

### Task 1: Create `src/rag/concepts.py`

**Files:**
- Create: `src/rag/concepts.py`

- [ ] **Step 1: Write the file**

```python
NA_CONCEPTS = {
    "капитуляция", "смирение", "Высшая Сила", "групповое сознание",
    "духовное пробуждение", "спонсорство", "только сегодня", "бессилие",
    "неуправляемость", "честность", "открытость", "готовность",
    "единство", "служение", "терапевтическая ценность", "выздоровление",
    "духовность", "принципы", "традиции", "шаги",
}
```

- [ ] **Step 2: Commit**

```bash
git add src/rag/concepts.py
git commit -m "feat: extract NA_CONCEPTS to shared module"
```

---

### Task 2: Create `src/utils/text.py` with `_extract_keywords`

**Files:**
- Create: `src/utils/text.py`
- Modify: `src/utils/__init__.py`

- [ ] **Step 1: Create `src/utils/text.py`**

Move the `_RUSSIAN_STOPWORDS` set and `_extract_keywords` function from `docx_parser.py`:

```python
from collections import Counter

_RUSSIAN_STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "из", "им", "от", "о", "для", "или", "еще", "до", "это", "об",
    "ни", "их", "чем", "при", "был", "когда", "кто", "меня", "нет", "вот",
    "теперь", "если", "уже", "будет", "даже", "потом", "чтобы", "себя", "них",
    "него", "нее", "там", "тому", "ли", "ну", "всё", "все", "очень",
    "разве", "ведь", "опять", "другой", "пока", "над", "под", "без",
}


# ponytail: natasha model loads ~100MB, ~5s cold start.
# Replace with lightweight keyword extraction if index rebuild speed matters.
def _extract_keywords(text: str, top_n: int = 5) -> list[str]:
    from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, Segmenter

    emb = NewsEmbedding()
    pipeline = {
        "segmenter": Segmenter(),
        "morph_tagger": NewsMorphTagger(emb),
        "morph_vocab": MorphVocab(),
    }

    doc = Doc(text.lower())
    doc.segment(pipeline["segmenter"])
    doc.tag_morph(pipeline["morph_tagger"])

    lemmas = []
    for token in doc.tokens:
        if token.pos not in ("NOUN", "PROPN"):
            continue
        token.lemmatize(pipeline["morph_vocab"])
        lemma = token.lemma
        if len(lemma) <= 2 or lemma in _RUSSIAN_STOPWORDS or lemma.isdigit():
            continue
        lemmas.append(lemma)

    top = Counter(lemmas).most_common(top_n)
    return [w for w, _ in top]
```

- [ ] **Step 2: Update `src/utils/__init__.py`**

```python
from .logging import setup_logging
from .text import _extract_keywords

__all__ = ["setup_logging", "_extract_keywords"]
```

- [ ] **Step 3: Commit**

```bash
git add src/utils/text.py src/utils/__init__.py
git commit -m "feat: extract _extract_keywords to src/utils/text.py"
```

---

### Task 3: Refactor `docx_parser.py` — use shared modules

**Files:**
- Modify: `src/rag/docx_parser.py`

- [ ] **Step 1: Replace imports**

At the top of `docx_parser.py`, replace the local `_RUSSIAN_STOPWORDS` and `_extract_keywords` via imports:

Remove:
```python
_RUSSIAN_STOPWORDS = { ... }
```

```python
# ponytail: natasha model loads ~100MB, ~5s cold start.
# Replace with lightweight keyword extraction if index rebuild speed matters.
def _get_morph_pipeline():
    ...
```

```python
def _extract_keywords(text: str, top_n: int = 5) -> list[str]:
    ...
```

Add:
```python
from src.utils.text import _extract_keywords
from src.rag.concepts import NA_CONCEPTS
```

- [ ] **Step 2: Replace `na_concepts_map` reference**

In `DocxParser.__init__`, replace:
```python
self.na_concepts_map = { ... }
```
with:
```python
self.na_concepts_map = NA_CONCEPTS
```

- [ ] **Step 3: Run existing docx_parser tests to confirm nothing broke**

Run:
```bash
pytest tests/test_docx_parser.py -v
```
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/rag/docx_parser.py
git commit -m "refactor: docx_parser uses shared NA_CONCEPTS and _extract_keywords"
```

---

### Task 4: Rewrite `Chunk` dataclass in `md_chunker.py`

**Files:**
- Modify: `src/rag/md_chunker.py`

- [ ] **Step 1: Replace the `Chunk` dataclass**

Current:
```python
@dataclass
class Chunk:
    content: str
    source: str
    page: int
    chunk_id: str = ""
    paragraph_index: int = 0
```

New:
```python
@dataclass
class Chunk:
    content: str
    source: str
    chunk_id: str = ""
    book_title: str = ""
    part: str | None = None
    chapter: str | None = None
    section: str | None = None
    element_type: str = "main_text"  # "main_text" | "step" | "tradition"
    element_number: int | None = None
    chunk_role: str = "body"  # "body" | "definition"
    definition_ref_id: str | None = None
    citation_label: str = "TBD"
    na_concepts: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    paragraph_index: int = 0
    page: int = 0  # kept for backward compat, always 0 after page removal
```

- [ ] **Step 2: Update `_generate_id`**

Keep same logic (md5 of source + content[:50]).

- [ ] **Step 3: Update `to_dict`**

```python
def to_dict(self) -> dict:
    return {
        "content": self.content,
        "metadata": {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "book_title": self.book_title,
            "part": self.part,
            "chapter": self.chapter,
            "section": self.section,
            "element_type": self.element_type,
            "element_number": self.element_number,
            "chunk_role": self.chunk_role,
            "definition_ref_id": self.definition_ref_id,
            "citation_label": self.citation_label,
            "na_concepts": self.na_concepts,
            "keywords": self.keywords,
            "paragraph_index": self.paragraph_index,
        }
    }
```

- [ ] **Step 4: Commit**

```bash
git add src/rag/md_chunker.py
git commit -m "refactor: update Chunk dataclass with full metadata fields"
```

---

### Task 5: Add heading detection + hierarchy tracking

**Files:**
- Modify: `src/rag/md_chunker.py`

- [ ] **Step 1: Add imports**

```python
import re
from src.rag.concepts import NA_CONCEPTS
from src.utils.text import _extract_keywords
```

- [ ] **Step 2: Add `_detect_heading` method**

```python
@staticmethod
def _detect_heading(text: str) -> tuple[str, str] | None:
    """Detect markdown heading and return (level, value) or None."""
    stripped = text.strip()
    for prefix, level in [("# ", "chapter"), ("## ", "section")]:
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            return (level, value)
    return None
```

- [ ] **Step 3: Add `_classify_heading` method**

```python
@staticmethod
def _classify_heading(chapter: str | None) -> tuple[str, int | None]:
    if not chapter:
        return ("main_text", None)
    chapter_lower = chapter.lower()
    m = re.search(r"шаг\s*(\d+)", chapter_lower)
    if m:
        return ("step", int(m.group(1)))
    m = re.search(r"традици[яюи]\s*(\d+)", chapter_lower)
    if m:
        return ("tradition", int(m.group(1)))
    return ("main_text", None)
```

- [ ] **Step 4: Update `__init__` — remove old params**

```python
def __init__(
    self,
    min_chunk_tokens: int = 250,
    max_chunk_tokens: int = 1200,
    overlap_ratio: float = 0.15,
):
    self.min_chunk_tokens = min_chunk_tokens
    self.max_chunk_tokens = max_chunk_tokens
    self.overlap_ratio = overlap_ratio
```

Remove `min_paragraph_length`, `cross_page_merge`, `merge_short_paragraphs`, `merge_threshold`.

- [ ] **Step 5: Commit**

```bash
git add src/rag/md_chunker.py
git commit -m "feat: heading detection, hierarchy tracking, new constructor params"
```

---

### Task 6: Add definition detection

**Files:**
- Modify: `src/rag/md_chunker.py`

- [ ] **Step 1: Add `_is_definition` static method**

```python
@staticmethod
def _is_definition(text: str) -> bool:
    stripped = text.rstrip(".!?,")
    return text.startswith("«") and stripped.endswith("»")
```

- [ ] **Step 2: Add `_detect_na_concepts` static method**

```python
@staticmethod
def _detect_na_concepts(text: str) -> list[str]:
    return [c for c in NA_CONCEPTS if c.lower() in text.lower()]
```

- [ ] **Step 3: Commit**

```bash
git add src/rag/md_chunker.py
git commit -m "feat: definition and na_concepts detection"
```

---

### Task 7: Rewrite `chunk_md` with hierarchy + definitions + metadata

**Files:**
- Modify: `src/rag/md_chunker.py`

- [ ] **Step 1: Rewrite `chunk_md` method**

```python
def chunk_md(self, md_path: Path) -> tuple[list[Chunk], ChunkingStats]:
    stats = ChunkingStats()
    chunks = []
    source_name = md_path.stem
    global_paragraph_index = 0

    hierarchy = {
        "book_title": source_name,
        "part": None,
        "chapter": None,
        "section": None,
        "element_type": "main_text",
        "element_number": None,
    }

    logger.info(f"Обработка файла: {md_path.name}")

    try:
        text = md_path.read_text(encoding="utf-8")
        paragraphs = self.split_into_paragraphs(text)
        stats.total_pages = 1

        current_definition_id: str | None = None

        for para in paragraphs:
            heading = self._detect_heading(para)
            if heading:
                level, value = heading
                if level == "chapter":
                    hierarchy["chapter"] = value
                    hierarchy["section"] = None
                    hierarchy["element_type"], hierarchy["element_number"] = \
                        self._classify_heading(value)
                    current_definition_id = None
                elif level == "section":
                    hierarchy["section"] = value
                continue

            if self._is_definition(para):
                chunk_id = hashlib.md5(
                    (para[:100]).encode("utf-8")
                ).hexdigest()[:16]
                current_definition_id = chunk_id
                chunk = Chunk(
                    content=para,
                    source=source_name,
                    book_title=hierarchy["book_title"],
                    part=hierarchy["part"],
                    chapter=hierarchy["chapter"],
                    section=hierarchy["section"],
                    element_type=hierarchy["element_type"],
                    element_number=hierarchy["element_number"],
                    chunk_role="definition",
                    definition_ref_id=chunk_id,
                    na_concepts=self._detect_na_concepts(para),
                    keywords=_extract_keywords(para),
                    paragraph_index=global_paragraph_index,
                )
                chunks.append(chunk)
                global_paragraph_index += 1
                continue

            chunk = Chunk(
                content=para,
                source=source_name,
                book_title=hierarchy["book_title"],
                part=hierarchy["part"],
                chapter=hierarchy["chapter"],
                section=hierarchy["section"],
                element_type=hierarchy["element_type"],
                element_number=hierarchy["element_number"],
                chunk_role="body",
                definition_ref_id=current_definition_id,
                na_concepts=self._detect_na_concepts(para),
                keywords=_extract_keywords(para),
                paragraph_index=global_paragraph_index,
            )
            chunks.append(chunk)
            global_paragraph_index += 1

        stats.total_paragraphs = len(chunks)
        chunks = self._post_process(chunks)
        stats.total_chunks = len(chunks)
        stats.files_processed += 1

        logger.info(f"  ✓ Обработано: {stats.total_chunks} чанков")

    except Exception as e:
        stats.errors.append(f"{md_path.name}: {str(e)}")
        logger.error(f"Ошибка обработки {md_path.name}: {e}")
        raise

    return chunks, stats
```

- [ ] **Step 2: Add `_post_process`, `_split_chunk`, `_estimate_tokens` methods**

```python
def _post_process(self, chunks: list[Chunk]) -> list[Chunk]:
    if not chunks:
        return chunks

    merged = [chunks[0]]
    for chunk in chunks[1:]:
        prev_is_def = merged[-1].chunk_role == "definition"
        curr_is_def = chunk.chunk_role == "definition"

        if not prev_is_def and not curr_is_def and \
           self._estimate_tokens(merged[-1].content) < self.min_chunk_tokens:
            merged[-1].content += " " + chunk.content
            continue

        if not curr_is_def and \
           self._estimate_tokens(chunk.content) > self.max_chunk_tokens:
            split = self._split_chunk(chunk)
            merged.extend(split)
            continue

        merged.append(chunk)

    return merged

def _split_chunk(self, chunk: Chunk) -> list[Chunk]:
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
            new_chunk = Chunk(
                content=text,
                source=chunk.source,
                book_title=chunk.book_title,
                part=chunk.part,
                chapter=chunk.chapter,
                section=chunk.section,
                element_type=chunk.element_type,
                element_number=chunk.element_number,
                chunk_role=chunk.chunk_role,
                definition_ref_id=chunk.definition_ref_id,
                na_concepts=chunk.na_concepts,
                keywords=chunk.keywords,
                paragraph_index=chunk.paragraph_index,
            )
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
        new_chunk = Chunk(
            content=text,
            source=chunk.source,
            book_title=chunk.book_title,
            part=chunk.part,
            chapter=chunk.chapter,
            section=chunk.section,
            element_type=chunk.element_type,
            element_number=chunk.element_number,
            chunk_role=chunk.chunk_role,
            definition_ref_id=chunk.definition_ref_id,
            na_concepts=chunk.na_concepts,
            keywords=chunk.keywords,
            paragraph_index=chunk.paragraph_index,
        )
        parts.append(new_chunk)

    return parts

@staticmethod
def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)
```

- [ ] **Step 3: Rewrite `split_into_paragraphs` — remove page/HTML cleanup, keep core logic**

```python
def split_into_paragraphs(self, text: str) -> list[str]:
    if not text.strip():
        return []

    paragraphs = []
    raw_blocks = re.split(r'\n\n+', text)

    for block in raw_blocks:
        lines = []
        for line in block.split('\n'):
            line = line.strip()
            if not line:
                continue
            lines.append(line)

        if not lines:
            continue

        block_text = ' '.join(lines)
        if block_text.strip():
            paragraphs.append(block_text)

    return paragraphs
```

- [ ] **Step 4: Commit**

```bash
git add src/rag/md_chunker.py
git commit -m "feat: rewrite chunk_md with hierarchy, definitions, token-based merge/split"
```

---

### Task 8: Clean up old methods

**Files:**
- Modify: `src/rag/md_chunker.py`

- [ ] **Step 1: Remove unused methods**

Remove `extract_pages_from_md` method entirely.

- [ ] **Step 2: Remove unused ChunkingStats fields** (optional — can keep for compat)

- [ ] **Step 3: Commit**

```bash
git add src/rag/md_chunker.py
git commit -m "refactor: remove extract_pages_from_md, simplify ChunkingStats"
```

---

### Task 9: Update tests

**Files:**
- Modify: `tests/test_md_chunker.py`

- [ ] **Step 1: Rewrite test class for new behavior**

```python
"""Tests for MarkdownChunker after metadata upgrade"""

import pytest
from src.rag.md_chunker import MarkdownChunker


class TestHeadingDetection:
    def test_detect_h1_as_chapter(self):
        chunker = MarkdownChunker()
        result = chunker._detect_heading("# Шаг Первый")
        assert result == ("chapter", "Шаг Первый")

    def test_detect_h2_as_section(self):
        chunker = MarkdownChunker()
        result = chunker._detect_heading("## Бессилие")
        assert result == ("section", "Бессилие")

    def test_plain_text_not_heading(self):
        chunker = MarkdownChunker()
        assert chunker._detect_heading("Обычный текст") is None

    def test_classify_step(self):
        chunker = MarkdownChunker()
        assert chunker._classify_heading("Шаг Первый") == ("step", None)
        assert chunker._classify_heading("Шаг 1") == ("step", 1)

    def test_classify_tradition(self):
        chunker = MarkdownChunker()
        assert chunker._classify_heading("Традиция 12") == ("tradition", 12)
        assert chunker._classify_heading("Традиции") == ("main_text", None)


class TestDefinitionDetection:
    def test_definition_in_quotes(self):
        chunker = MarkdownChunker()
        assert chunker._is_definition("«Мы признали, что бессильны.»")

    def test_plain_text_not_definition(self):
        chunker = MarkdownChunker()
        assert not chunker._is_definition("Обычный текст.")

    def test_quotes_but_not_definition_without_end_quote(self):
        chunker = MarkdownChunker()
        assert not chunker._is_definition("«Мы признали, что бессильны.")


class TestNAConcepts:
    def test_detect_single_concept(self):
        chunker = MarkdownChunker()
        result = chunker._detect_na_concepts("Капитуляция — ключ к выздоровлению.")
        assert "капитуляция" in result
        assert "выздоровление" in result

    def test_no_concepts_in_plain_text(self):
        chunker = MarkdownChunker()
        assert chunker._detect_na_concepts("Обычный текст без концепций.") == []


class TestSplitIntoParagraphs:
    def test_simple_paragraphs(self):
        chunker = MarkdownChunker()
        text = "Первый параграф.\n\nВторой параграф."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 2

    def test_heading_not_removed(self):
        chunker = MarkdownChunker()
        text = "# Шаг Первый\n\nТекст шага."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 2
        assert result[0] == "# Шаг Первый"

    def test_empty_text(self):
        chunker = MarkdownChunker()
        assert chunker.split_into_paragraphs("") == []


class TestChunkMd:
    def test_simple_document(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "«Мы признали, что бессильны.»\n\n"
            "Капитуляция — это ключ к выздоровлению.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) >= 2
        assert chunks[0].chunk_role == "definition"
        assert chunks[1].chunk_role == "body"

    def test_hierarchy_propagated(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "## Бессилие\n\n"
            "Текст раздела.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        assert chunks[0].chapter == "Шаг Первый"
        assert chunks[0].section == "Бессилие"
        assert chunks[0].element_type == "step"

    def test_definition_ref_id_propagated(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "«Мы признали.»\n\n"
            "Текст главы.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        def_chunk = [c for c in chunks if c.chunk_role == "definition"][0]
        body_chunk = [c for c in chunks if c.chunk_role == "body"][0]
        assert body_chunk.definition_ref_id == def_chunk.chunk_id

    def test_short_body_chunks_merged(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг\n\n"
            "«Мы признали.»\n\n"
            "Короткий текст.\n\n"
            "Еще короткий.\n\n"
            "Третий короткий.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        body_chunks = [c for c in chunks if c.chunk_role == "body"]
        assert len(body_chunks) < 3  # merged

    def test_long_body_chunk_split(self, tmp_path):
        long_text = "Предложение. " * 500
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг\n\n"
            "«Мы признали.»\n\n" + long_text,
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        body_chunks = [c for c in chunks if c.chunk_role == "body"]
        assert len(body_chunks) > 1  # split

    def test_na_concepts_detected_in_chunk(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг\n\n"
            "Капитуляция смирение выздоровление.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        assert "капитуляция" in chunks[0].na_concepts
        assert "смирение" in chunks[0].na_concepts
        assert "выздоровление" in chunks[0].na_concepts

    def test_to_dict_includes_all_metadata(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "Текст.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        d = chunks[0].to_dict()
        assert "chunk_id" in d["metadata"]
        assert "book_title" in d["metadata"]
        assert "chapter" in d["metadata"]
        assert "element_type" in d["metadata"]
        assert "chunk_role" in d["metadata"]
        assert "na_concepts" in d["metadata"]
        assert "keywords" in d["metadata"]


class TestSaveChunks:
    def test_save_and_load(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "«Мы признали.»\n\n"
            "Текст.",
            encoding="utf-8",
        )
        out_dir = tmp_path / "chunks"
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        chunker.save_chunks(chunks, out_dir)

        assert (out_dir / "index.json").exists()
        assert (out_dir / "chunk_0000.json").exists()

        import json
        chunk0 = json.loads((out_dir / "chunk_0000.json").read_text(encoding="utf-8"))
        assert chunk0["metadata"]["source"] == "test"
        assert chunk0["metadata"]["chunk_role"] == "definition"
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_md_chunker.py -v
```
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```
Expected: ALL PASS (docx_parser tests also pass)

- [ ] **Step 4: Commit**

```bash
git add tests/test_md_chunker.py
git commit -m "test: update md_chunker tests for new metadata features"
```

---

### Self-Review Checklist

**1. Spec coverage:**
- Heading detection (H1/H2) → Task 5 ✓
- Hierarchy tracking (book_title → chapter → section) → Task 7 ✓
- Definition detection («») → Task 6, Task 7 ✓
- NA concepts → Task 6 (detection), Task 7 (integration) ✓
- Keywords → Task 2 (extract), Task 7 (integration) ✓
- Token-based merge/split → Task 7 (_post_process) ✓
- Updated to_dict → Task 4 ✓
- Removed page logic → Task 8 ✓
- citation_label = TBD → in Chunk dataclass ✓
- DocxParser refactored to use shared modules → Task 3 ✓
- concepts.py created → Task 1 ✓
- utils/text.py created → Task 2 ✓

**2. Placeholder scan:** No placeholders. Every step contains actual code.

**3. Type consistency:** All Chunk field names match between __init__, to_dict, and chunk_md usage.

**4. No gaps between tasks:** Each task produces working, committable state.
