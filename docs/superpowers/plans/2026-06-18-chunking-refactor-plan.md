# Chunking System Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix chunk content (no more fragments/artifacts) and clean up redundant files in the chunking pipeline.

**Architecture:** Two-file fix: `md_chunker.py` (cross-page merge, short paragraph merge, remove sentence splitting) + `clean_markdown.py` (artifact filters). Then delete 3 redundant files and update callers.

**Tech Stack:** Python, PyMuPDF, aiogram3, FAISS

---

### Task 1: md_chunker.py — cross-page paragraph merge

**Files:**
- Modify: `src/rag/md_chunker.py:75-90`, `:216-258`

- [ ] **Step 1: Add cross_page_merge and merge_short_paragraphs params**

Change `__init__`:

```python
def __init__(
    self,
    min_paragraph_length: int = 10,
    cross_page_merge: bool = True,
    merge_short_paragraphs: bool = True,
    merge_threshold: int = 50,
):
    self.min_paragraph_length = min_paragraph_length
    self.cross_page_merge = cross_page_merge
    self.merge_short_paragraphs = merge_short_paragraphs
    self.merge_threshold = merge_threshold
```

- [ ] **Step 2: Add cross-page merge + short paragraph merge in chunk_md**

Rewrite the page loop in `chunk_md`:

```python
def chunk_md(self, md_path: Path) -> tuple[list[Chunk], ChunkingStats]:
    stats = ChunkingStats()
    chunks = []
    source_name = md_path.stem
    global_paragraph_index = 0
    continued_paragraph = None  # (page, text) for cross-page merge

    logger.info(f"Обработка файла: {md_path.name}")

    try:
        pages_text = self.extract_pages_from_md(md_path)
        stats.total_pages = len(pages_text)

        for page_num, page_text in pages_text:
            if not page_text.strip():
                stats.empty_pages += 1
                continue

            paragraphs = self.split_into_paragraphs(page_text)
            if not paragraphs:
                stats.empty_pages += 1
                continue

            # Cross-page merge: prepend continued paragraph
            if self.cross_page_merge and continued_paragraph is not None:
                paragraphs[0] = continued_paragraph[1] + " " + paragraphs[0]
                continued_paragraph = None
                stats.cross_page_paragraphs += 1

            # Check if last paragraph continues to next page
            if self.cross_page_merge and paragraphs:
                last = paragraphs[-1]
                if not last.rstrip().endswith(('.', '!', '?', ':', ';', '»', '"')):
                    continued_paragraph = (page_num, last)
                    paragraphs = paragraphs[:-1]

            for para in paragraphs:
                chunk = Chunk(
                    content=para,
                    source=source_name,
                    page=page_num,
                    paragraph_index=global_paragraph_index,
                )
                chunks.append(chunk)
                global_paragraph_index += 1
                stats.total_paragraphs += 1

        # Flush remaining continued paragraph
        if continued_paragraph is not None:
            chunk = Chunk(
                content=continued_paragraph[1],
                source=source_name,
                page=continued_paragraph[0],
                paragraph_index=global_paragraph_index,
            )
            chunks.append(chunk)
            global_paragraph_index += 1
            stats.total_paragraphs += 1

        stats.total_chunks = len(chunks)
        stats.files_processed += 1

        logger.info(
            f"  ✓ Обработано: {stats.total_pages} стр., "
            f"{stats.total_paragraphs} абзацев, "
            f"{stats.cross_page_paragraphs} межстраничных"
        )

    except Exception as e:
        stats.errors.append(f"{md_path.name}: {str(e)}")
        logger.error(f"Ошибка обработки {md_path.name}: {e}")
        raise

    return chunks, stats
```

- [ ] **Step 3: Add merge_short_paragraphs in chunk_md**

After building chunks list, merge short ones:

```python
if self.merge_short_paragraphs and chunks:
    merged = []
    for chunk in chunks:
        if len(chunk.content) < self.merge_threshold and merged:
            # Merge with previous chunk
            prev = merged[-1]
            merged[-1] = Chunk(
                content=prev.content + " " + chunk.content,
                source=prev.source,
                page=prev.page,
                chunk_id=prev.chunk_id,
                paragraph_index=prev.paragraph_index,
            )
        else:
            merged.append(chunk)
    chunks = merged
    stats.total_chunks = len(chunks)
```

- [ ] **Step 4: Remove sentence-splitting logic from split_into_paragraphs**

Replace the long-block handling (lines 180-212) with just keeping the block as-is:

```python
def split_into_paragraphs(self, text: str) -> list[str]:
    if not text.strip():
        return []

    text = re.sub(r'<!--\s*Page\s+\d+\s*-->', '', text)
    paragraphs = []
    raw_blocks = re.split(r'\n\n+', text)

    for block in raw_blocks:
        lines = []
        for line in block.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('<!--') and line.endswith('-->'):
                continue
            if re.match(r'^\*\[\d+\s+изображений?\s+на\s+странице\s+\d+\]\*$', line):
                continue
            if re.match(r'^.*\.{3,}\d+$', line):
                continue
            lines.append(line)

        if not lines:
            continue

        block_text = ' '.join(lines)
        if len(block_text) >= self.min_paragraph_length:
            paragraphs.append(block_text)

    return paragraphs
```

- [ ] **Step 5: Run existing tests**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: tests pass (they test a different module, should not be affected)

- [ ] **Step 6: Commit**

```bash
git add src/rag/md_chunker.py
git commit -m "fix(md_chunker): cross-page merge, short paragraph merge, remove sentence splitting"
```

---

### Task 2: clean_markdown.py — artifact filtering

**Files:**
- Modify: `scripts/clean_markdown.py:96-184`

- [ ] **Step 1: Add artifact filters to clean_markdown_content**

Before the line-processing loop, add pre-processing to remove known artifacts:

```python
ARTIFACT_PATTERNS = [
    r'^# Конвертированный документ',
    r'^\*\*Источник:\*\*\s*.+\.pdf',
    r'^\*\*Создано в:\*\*',
    r'^## Страница \d+',
    r'^\*\[Страница пуста или содержит только изображения\]\*',
    r'(?i)^\s*(copyright|©|all rights reserved)',
    r'\bISBN\s+[\d-]{10,}\b',
]
```

Add to `clean_markdown_content`, after reading content and before splitting into lines:

```python
# Remove artifact lines
lines = content.split('\n')
filtered = []
in_colophon = False
for line in lines:
    # Detect colophon start
    if line.strip() in ('***', '---') and in_colophon:
        break
    if line.strip() in ('***', '---'):
        in_colophon = True
        continue
    if in_colophon:
        continue
    # Skip artifact patterns
    stripped = line.strip()
    skip = False
    for pattern in ARTIFACT_PATTERNS:
        if re.match(pattern, stripped):
            skip = True
            break
    if not skip:
        filtered.append(line)
content = '\n'.join(filtered)
```

Then proceed with the existing cleaning logic.

- [ ] **Step 2: Run clean_markdown.py on a test file**

Run: `python scripts/clean_markdown.py --input-dir data/documents/md_docs --dry-run`
Expected: artifacts listed as removed, no actual file changes

- [ ] **Step 3: Commit**

```bash
git add scripts/clean_markdown.py
git commit -m "feat(clean_markdown): filter conversion artifacts, colophon, ISBN, copyright"
```

---

### Task 3: Delete redundant files

**Files:**
- Delete: `src/rag/chunker.py`
- Delete: `src/rag/md_search.py`
- Delete: `scripts/build_faiss_index.py`

- [ ] **Step 1: Delete files**

```bash
git rm src/rag/chunker.py src/rag/md_search.py scripts/build_faiss_index.py
```

- [ ] **Step 2: Verify nothing imports them**

```bash
rg "from src.rag.chunker" src/ tests/ || true
rg "from src.rag.md_search" src/ tests/ || true
rg "import src.rag.md_search" src/ tests/ || true
rg "build_faiss_index" scripts/ src/ tests/ || true
```
Expected: no results (or only in deleted files)

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove unused chunker.py, md_search.py, build_faiss_index.py"
```

---

### Task 4: Update rag_tools.sh and search.py

**Files:**
- Modify: `scripts/rag_tools.sh`
- Modify: `src/rag/search.py:267`
- Modify: `src/rag/__init__.py`
- Modify: `src/rag/md_search.py` (this is being deleted in Task 3, skip)

- [ ] **Step 1: Update rag_tools.sh — replace chunker with md_chunker**

Change line 64: `python -m src.rag.chunker "$@"` → `python -m src.rag.md_chunker "$@"`

Change lines 77-88 (full command): replace `python -m src.rag.chunker` with `python -m src.rag.md_chunker` and add a clean_markdown step:

```bash
# Step 1: Clean markdown
echo -e "${GREEN}[1/4] Очистка Markdown от мусора...${NC}"
python scripts/clean_markdown.py --input-dir data/documents/md_docs

# Step 2: Chunking
echo -e "${GREEN}[2/4] Разбиение документов на чанки...${NC}"
python -m src.rag.md_chunker "$@"

# Step 3: Indexing
echo -e "${GREEN}[3/4] Индексация чанков в векторной базе...${NC}"
python -m src.rag.chunk_loader --clear

# Step 4: Search
echo -e "${GREEN}[4/4] Поиск...${NC}"
```

- [ ] **Step 2: Update search.py error message**

Change line 267 from `"Используйте: python -m src.rag.chunker"` to `"Используйте: python -m src.rag.md_chunker"`

- [ ] **Step 3: Update __init__.py exports**

```python
from .service import ChunkResult, RAGService
from .search import search_query, format_citation

__all__ = [
    "RAGService",
    "ChunkResult",
    "search_query",
    "format_citation",
]
```

- [ ] **Step 4: Commit**

```bash
git add scripts/rag_tools.sh src/rag/search.py src/rag/__init__.py
git commit -m "chore: update callers — chunker→md_chunker, search error msg, __init__ exports"
```

---

### Task 5: Test the full pipeline end-to-end

- [ ] **Step 1: Pick a small PDF and run the pipeline**

```bash
python scripts/pdf_to_markdown.py --input-dir data/documents/pdf_docs --output-dir data/documents/md_docs
python scripts/clean_markdown.py --input-dir data/documents/md_docs
python -m src.rag.md_chunker --input-dir data/documents/md_docs --output-dir data/documents/chunks
python -m src.rag.chunk_loader --clear
```

- [ ] **Step 2: Verify chunks look correct**

```bash
# Check a few chunk files — no fragments, no artifacts
python -c "
import json
from pathlib import Path
for d in sorted(Path('data/documents/chunks').iterdir()):
    if d.is_dir():
        idx = d / 'index.json'
        if idx.exists():
            data = json.loads(idx.read_text())
            print(f'{d.name}: {data[\"total_chunks\"]} chunks')
            for c in data['chunks'][:3]:
                print(f'  page={c[\"page\"]} preview={c[\"preview\"][:80]}')
            print()
"
```

- [ ] **Step 3: Run a test search**

```bash
python -m src.rag.search "тестовый запрос" --verbose
```

- [ ] **Step 4: Run test suite**

```bash
python -m pytest tests/ -v --tb=short
```

- [ ] **Step 5: Commit if any additional fixes were needed**

```bash
git add -A
git commit -m "fix: pipeline adjustments after end-to-end test"
```
