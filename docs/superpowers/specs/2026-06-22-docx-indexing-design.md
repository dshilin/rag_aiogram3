# Docx Indexing — иерархический парсер с метаданными

## Цель

Заменить пайплайн PDF→MD→clean→chunk на прямой парсинг .docx с сохранением иерархии книги (Часть → Шаг/Традиция → Подраздел → Абзац), обогащением метаданных и поддержкой фильтрации при поиске.

## Что меняем

### 1. Новый файл: `src/rag/docx_parser.py`

Парсер .docx на `python-docx`. Извлекает иерархию, наследует контекст, создаёт чанки.

**Определение заголовков:**
- Heading 1 (MS Word style или первый абзац с жирным+крупным) → `book_title`
- Heading 2 (или паттерны `КНИГА ...`) → `part`
- Heading 3 (или `Шаг ...`, `Традиция ...`) → `chapter`
- Heading 4 → `section`
- Эвристика для немаркированных заголовков: `is_header_line()` — строка ≤5 слов, без точки, окружена пустыми строками

**Цитата-девиз (chunk_role: definition):**  
- Первый абзац главы в кавычках `«...»` и/или жирным шрифтом → `chunk_role: definition`, `element_type: step|tradition`
- Атомарный, не режется, не склеивается
- Его `chunk_id` записывается в `definition_ref_id` всех body-чанков этой главы

**Чанкинг:**
- Единица — абзац (разделитель: `\n\n` или double break)
- < 250 токенов → склеить со следующим (до 250 или границы главы)
- > 1200 токенов → резать по предложениям с overlap 10-15% токенов
- Cross-reference (начинается с префикса `В ... Шаге`, `Как мы узнали из...`, `Теперь мы должны перейти к...`) — не разрывать
- Вступление (текст до первого `Шаг`/`Традиция`) → `chunk_role: body`, `chapter: "Введение"`

**na_concepts:**
- Статический словарь ~20 терминов АН: `"капитуляция"`, `"смирение"`, `"Высшая Сила"`, `"групповое сознание"`, `"духовное пробуждение"`, `"спонсорство"`, `"Только сегодня"`, ...
- Каждый чанк сканируется, совпадения → `metadata.na_concepts`
- `keywords` — топ-5 существительных из чанка (TF), для гибридного поиска

**Интерфейс:**
```python
@dataclass
class DocxChunk:
    content: str
    chunk_id: str
    metadata: dict

class DocxParser:
    def __init__(self, min_chunk_tokens=250, max_chunk_tokens=1200, overlap_ratio=0.15):
        ...
    def parse(self, path: Path) -> list[DocxChunk]:
        ...
```

### 2. Схема метаданных

```python
{
    # --- 1. Идентификация и Навигация ---
    "chunk_id":             str,             # Уникальный ID чанка
    "book_title":           str,             # "Базовый текст АН" | "Это работает"
    "part":                 str | None,      # "Книга Первая: Шаги" | "Личные истории" | None
    "chapter":              str,             # "Шаг Первый" | "Традиция Третья" | "Введение"
    "section":              str | None,      # Подзаголовок (напр., "Бессилие и неуправляемость")
    "page":                 int | None,      # Номер страницы (для сверки с печатной книгой)

    # --- 2. Структурная типизация ---
    "element_type":         str,             # step | tradition | story | main_text | preface | definition
    "element_number":       int | None,      # 1-12 для шагов и традиций
    "chunk_role":           str,             # definition (жирный текст шага) | body | story_intro

    # --- 3. Оптимизация для LLM и Цитирования ---
    "citation_label":       str,             # ПРЕДВАРИТЕЛЬНО СОБРАННАЯ строка для цитаты!
                                             # "«Базовый текст АН», Глава «Шаг Первый», Раздел «Бессилие»"
    "definition_ref_id":    str | None,      # ID чанка с definition этого элемента (связывает body с определением)

    # --- 4. Семантика и Гибридный поиск ---
    "na_concepts":          list[str],       # Стандартизированные теги АН
    "keywords":             list[str],       # Ключевые слова для BM25

    # --- 5. Совместимость со старым кодом ---
    "source":               str,             # = book_title (для ChunkResult.source)
}
```

### 3. Изменение: `src/rag/service.py`

#### `ChunkResult` — добавить поле `metadata`

```python
@dataclass
class ChunkResult:
    content: str
    source: str
    page: int
    chunk_id: str
    score: float = 0.0
    metadata: dict = None   # новый
```

#### `query_with_metadata()` — поддержка metadata_filter и definition_ref_id

```python
def query_with_metadata(
    self,
    question: str,
    top_k: Optional[int] = None,
    score_threshold: float = 0.0,
    metadata_filter: Optional[dict] = None,
    expand_definitions: bool = True,
) -> list[ChunkResult]:
```

Логика:
1. FAISS `similarity_search_with_score(question, k=top_k*2)`
2. Post-filter по `metadata_filter` (если передан)
3. Dedup по (source, page)
4. Если `expand_definitions` — для каждого чанка с `chunk_role == "body"` и `definition_ref_id`, подтянуть definition-чанк из docstore и **склеить**: `"[Определение]\n{definition.content}\n\n{chunk.content}"` → записать в `content`
5. Вернуть `top_k` результатов

#### `add_documents()` — принимать метаданные

Уже принимает `metadatas: Optional[list[dict]]` — без изменений.

#### `_save_index()` / `_load_index()`

Без изменений. Метаданные уже сохраняются в `chunks_metadata.json`.

### 4. Новый CLI: `python -m src.rag.docx_parser`

```bash
python -m src.rag.docx_parser data/documents/eto_rabotaet.docx
python -m src.rag.docx_parser data/documents/ --clear
```

- `__main__` в `docx_parser.py`, как в `md_chunker.py`
- Читает .docx, парсит, загружает через `RAGService.add_documents()`

### 5. Старые скрипты

`pdf_to_markdown.py`, `clean_markdown.py`, `md_chunker.py` — остаются, не удаляем.

## Что НЕ меняем

- `handlers.py`, `web/router.py`, `session.py`, `classifier.py` — без изменений
- `base.py`, `factory.py`, `yandex_gpt.py`, `vsegpt.py`, `openai_client.py` — без изменений
- `RAGService.__init__()`, `_load_index()`, `_save_index()`, `add_documents()`, `clear()` — без изменений
- `chunk_loader.py`, `search.py` — без изменений
- FAISS + JSON формат хранения — без изменений

## Тесты (TDD)

Первыми пишутся тесты для `DocxParser` и `RAGService`:

### DocxParserTest

**HierarchyTest:**
- `test_h1_detected_as_book_title` — заголовок → `metadata.book_title`
- `test_h2_h3_h4_nesting` — вложенные заголовки → наследование
- `test_plain_text_heading_heuristic` — заголовок без стиля → эвристика

**StepDefinitionTest:**
- `test_first_paragraph_in_quotes_is_definition` → `chunk_role: definition`
- `test_definition_is_atomic` — не разбивается
- `test_definition_ref_id_propagated` — `definition_ref_id` во всех body-чанках главы
- `test_citation_label_format` — `"«{book_title}», Глава «{chapter}», Раздел «{section}»"`

**ChunkingTest:**
- `test_paragraph_is_unit` — абзац не режется внутри
- `test_short_paragraphs_merged` — < 250 токенов склеиваются
- `test_long_paragraph_split` — > 1200 токенов режется с overlap
- `test_cross_reference_not_split` — отсылка не разрывает

**NaConceptsTest:**
- `test_concept_detected_in_chunk` — термин из словаря → `metadata.na_concepts`
- `test_keywords_generated` — top-5 существительных

**IntegrationTest:**
- `test_parse_then_index_then_search` — парсит → загружает → ищет
- `test_metadata_filter` — фильтр по `book_title` возвращает только нужные
- `test_definition_expansion` — body-чанк с `definition_ref_id` получает склеенный content
