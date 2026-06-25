# md_chunker Upgrade: Bringing Metadata Depth to Markdown Chunking

## Motivation

`md_chunker.py` produces flat chunks (source, page, paragraph_index), while
`docx_parser.py` produces rich chunks — keywords, NA concepts, definitions,
hierarchy, chunk roles. The Markdown pipeline (PDF → md → chunks → FAISS) is
the primary ingestion path, and its chunks lack the metadata that the RAG
service already expects and uses (keyword boost, definition expansion).

## Scope

Refactor `md_chunker.py` only. No changes to `docx_parser.py`, `service.py`,
`chunk_loader.py`, or any other module — the output format stays compatible
with the existing loader.

## Output format

Every chunk produces a JSON file with this shape:

```python
{
  "content": "...",
  "metadata": {
    "chunk_id": "md5:16",
    "source": "filename",
    "book_title": "filename",
    "part": null,
    "chapter": "...",
    "section": "...",
    "element_type": "main_text" | "step" | "tradition",
    "element_number": null | int,
    "chunk_role": "body" | "definition",
    "definition_ref_id": null | str,
    "citation_label": "TBD",
    "na_concepts": [...],
    "keywords": [...],
    "paragraph_index": 0
  }
}
```

`citation_label` is deferred — the format will be designed in a follow-up.

## Changes

### 1. Heading detection

Lines starting with `# ` at the beginning of a paragraph are treated as
H1 (chapter). Lines starting with `## ` as H2 (section). No other levels
are tracked.

When a heading is detected:
- It is NOT emitted as a chunk (headers are structural metadata, not content).
- It updates the current hierarchy (`chapter` / `section`).
- If the heading matches `шаг \d+` → `element_type = "step"`,
  `element_number = <digit>`.
- If the heading matches `традици[яюи] \d+` → `element_type = "tradition"`,
  `element_number = <digit>`.
- Otherwise → `element_type = "main_text"`, `element_number = null`.

### 2. Hierarchy inheritance

A `current_hierarchy` dict is maintained during processing:

```python
current_hierarchy = {
    "book_title": file_stem,
    "part": None,
    "chapter": None,
    "section": None,
    "element_type": "main_text",
    "element_number": None,
}
```

H1 → sets `chapter`, resets `section`.
H2 → sets `section`.
Every content paragraph inherits the current hierarchy values.

### 3. Definition detection

A paragraph that starts with `«` and ends with `»` (after stripping
`.!?,`) is a `definition` chunk. It generates a `definition_ref_id`
(md5 of first 100 chars). Every following body chunk receives that
`definition_ref_id` until a new definition or chapter heading resets it.

Definitions are NOT merged with adjacent paragraphs.

### 4. NA concepts

A shared set of NA-related keywords is maintained in
`src/rag/concepts.py`:

```python
NA_CONCEPTS = {
    "капитуляция", "смирение", "Высшая Сила", "групповое сознание",
    "духовное пробуждение", "спонсорство", "только сегодня", "бессилие",
    "неуправляемость", "честность", "открытость", "готовность",
    "единство", "служение", "терапевтическая ценность", "выздоровление",
    "духовность", "принципы", "традиции", "шаги",
}
```

At chunk creation time, we check which of these appear (case-insensitive,
substring) in the paragraph text and store the matches in `na_concepts`.

### 5. Keywords

`_extract_keywords(text, top_n=5)` is moved from `docx_parser.py` into
`src/utils/text.py` so both parsers share the same implementation. It
uses natasha (Segmenter + NewsMorphTagger + MorphVocab), filters
NOUN/PROPN, deduplicates, and returns top-N lemmas.

### 6. Chunk merging / splitting

Replace `merge_short_paragraphs` / `merge_threshold` with:

- **Merge**: If a body chunk token count < `min_chunk_tokens` (250),
  merge its content with the next body chunk. Definitions are NOT merged.
- **Split**: If a body chunk token count > `max_chunk_tokens` (1200),
  split by sentence boundaries (`[.!?]`), keep overlap of 15% of
  `max_chunk_tokens`. Definitions are NOT split.

Token estimation: `len(text.split()) * 1.3` (same as docx_parser).

### 7. Removed

- `merge_short_paragraphs`, `merge_threshold` constructor params.
- `cross_page_merge` is still present but deprecated — no `page`
  metadata means it becomes a plain paragraph-merge mechanism.
- `extract_pages_from_md` and related `<!-- Page X -->` logic is
  removed from `chunk_md()` (the method). The helper methods stay
  in the class but are not called by default.

### 8. CLI

Unchanged. Parameters `--min-tokens` / `--max-tokens` are NOT added
(design decision: internal constants are sufficient for now).

### 9. `Chunk` dataclass

Updated to include all new metadata fields. Not replaced with
`DocxChunk` — `Chunk` is the md_chunker's own class.

## Files touched

| File | Change |
|------|--------|
| `src/rag/md_chunker.py` | Major refactor |
| `src/utils/text.py` | New — `_extract_keywords` moved here |
| `src/rag/concepts.py` | New — `NA_CONCEPTS` set |
| `src/rag/docx_parser.py` | Remove `_extract_keywords`, import from utils.text |
| `src/rag/__init__.py` | Possibly unchanged |

## Non-goals

- No embedding / FAISS integration
- No `citation_label` format (deferred)
- No changes to `chunk_loader.py` or `service.py`
- No changes to `docx_parser.py` beyond the keyword extraction move
