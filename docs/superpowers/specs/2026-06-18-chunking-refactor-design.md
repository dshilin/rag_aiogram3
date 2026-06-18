# Chunking System Refactor

## Pipeline

```
PDF → pdf_to_md.py → MD → clean_markdown.py → чистый MD → md_chunker.py → JSON chunks → chunk_loader.py → FAISS
```

## Changes

### 1. md_chunker.py — склейка межстраничных абзацев

- Убрать эвристику 300/100 (разбивка на предложения). Каждый абзац = один чанк.
- Добавить `cross_page_merge: bool = True` — если последний абзац страницы не заканчивается на `. ! ?`, склеить его с первым абзацем следующей страницы.
- Добавить `merge_short_paragraphs: bool = True`, `merge_threshold: int = 50` — абзацы короче порога присоединять к предыдущему чанку.
- `min_paragraph_length: int = 10` — оставить без изменений.

### 2. clean_markdown.py — фильтрация мусора

Хардкод-паттерны в `clean_markdown_content()`:

- Удалять строки с `# Конвертированный документ`
- Удалять строки с `**Источник:** *.pdf`
- Удалять `## Страница N`
- Удалять `*[Страница пуста или содержит только изображения]*`
- Удалять строки с ISBN, копирайт-уведомления (`©`, `Copyright`, `All rights reserved`)
- Отсекать колофон: всё после `***` или `---` в конце документа

### 3. Удалить дублирующиеся файлы

- `src/rag/chunker.py` — прямой PDF-чанкинг не нужен
- `src/rag/md_search.py` — дубликат `search.py`
- `scripts/build_faiss_index.py` — дубликат `chunk_loader.py`

### 4. Обновить rag_tools.sh

- Заменить `python -m src.rag.chunker` на `python -m src.rag.md_chunker` в командах `chunk` и `full`
- Добавить шаг `clean_markdown.py` перед чанкингом в `full`

### 5. Обновить __init__.py

Экспортировать `RAGService`, `ChunkResult`, `search_query`, `format_citation`.

### 6. Обновить search.py

Сообщение об ошибке: `"Используйте: python -m src.rag.md_chunker"` вместо ссылки на `chunker`.

## Что не меняем

- `chunk_loader.py` — работает, менять не нужно
- `service.py` (RAGService) — загрузка/поиск корректны
- `search.py` — логика поиска корректна, только сообщение об ошибке
