# Система разбиения документов на чанки и поиска

## Обзор

Система предназначена для поиска точных цитат из PDF-документов с указанием источника и страницы. Пайплайн:

```
PDF документ
    │
    ▼ [1] pdf_to_markdown.py
Markdown (<!-- Page X -->)
    │
    ▼ [2] clean_markdown.py
Очищенный Markdown
    │
    ▼ [3] md_chunker.py
JSON чанки с метаданными
    │
    ▼ [4] chunk_loader.py
FAISS индекс (векторное хранилище)
    │
    ▼ [5] search.py
Поиск с цитатами и источниками
```

Зачем конвертировать PDF → MD перед чанкингом:
1. **Предсказуемость** — можно прочитать Markdown и проверить, что получилось
2. **Очистка** — возможность убрать мусор (конвертационные заголовки, номера ISBN, копирайты, артефакты форматирования)
3. **Контроль** — можно править Markdown вручную перед чанкингом

## Этап 1: PDF → Markdown

```bash
python scripts/pdf_to_markdown.py \
    --input-dir data/documents/pdf_docs \
    --output-dir data/documents/md_docs
```

**Что делает:**
- Извлекает текст из PDF через PyMuPDF
- Детектирует абзацы по координатам, шрифтам и вертикальным промежуткам
- Распознаёт заголовки глав (оформляет как `# Заголовок`)
- Вставляет маркеры страниц: `<!-- Page N -->`
- Сохраняет как Markdown с разделением абзацев через `\n\n`

**Вход:** `data/documents/pdf_docs/*.pdf`
**Выход:** `data/documents/md_docs/*.md`

## Этап 2: Очистка Markdown

```bash
python scripts/clean_markdown.py \
    --input-dir data/documents/md_docs
```

**Что делает:**
- Удаляет строки короче 2 символов (кроме маркеров страниц)
- Удаляет строки из спецсимволов
- Склеивает строки, разорванные переносом слов (в середине предложения)
- Удаляет подряд идущие дубликаты строк
- Ограничивает пустые строки (максимум 2 подряд)
- Создаёт `.bak` перед изменениями

**Вход:** `data/documents/md_docs/*.md`
**Выход:** те же файлы (изменяются на месте)

## Этап 3: Разбиение на чанки

```bash
python -m src.rag.md_chunker \
    --input-dir data/documents/md_docs \
    --output-dir data/documents/chunks
```

**Что делает:**
- Читает Markdown с маркерами `<!-- Page X -->`
- Разбивает на страницы по маркерам
- Внутри каждой страницы разбивает текст на абзацы (по `\n\n`)
- Каждый абзац → чанк с метаданными

**Структура чанка:**

```json
{
  "content": "Текст абзаца...",
  "metadata": {
    "source": "document_name",
    "page": 5,
    "chunk_id": "a1b2c3d4e5f6g7h8",
    "paragraph_index": 42
  }
}
```

**Метаданные:**
| Поле | Описание |
|------|----------|
| `source` | Имя файла без расширения |
| `page` | Номер страницы из маркера `<!-- Page X -->` |
| `chunk_id` | MD5-хеш от контента + метаданных (первые 16 символов) |
| `paragraph_index` | Глобальный порядковый номер абзаца в документе |

**Выход:** `data/documents/chunks/<doc_name>/chunk_NNNN.json` + `index.json`

## Этап 4: Индексация в FAISS

```bash
python -m src.rag.chunk_loader --clear
```

**Что делает:**
- Загружает все JSON-чанки из `data/documents/chunks/`
- Генерирует эмбеддинги через `HuggingFaceEmbeddings`
- Сохраняет FAISS индекс (точный поиск, Inner Product для нормализованных векторов)

**Выход:** `data/embeddings/`
```
data/embeddings/
├── faiss.index              # FAISS векторный индекс
├── chunks_metadata.json     # Тексты чанков + id_mapping
└── index_metadata.json      # Модель, размерность, дата
```

## Этап 5: Поиск

```bash
# Разовый запрос
python -m src.rag.search "Ваш вопрос" --verbose

# Интерактивный режим
python -m src.rag.search --interactive

# Краткий формат
python -m src.rag.search "Ваш вопрос" --short
```

**Пример вывода:**
```
📌 Результат #1 (релевантность: 0.8542)
📚 Источник: document_name
📑 Страница: 15
🆔 ID чанка: a1b2c3d4e5f6g7h8
💬 Цитата:
> Текст найденного абзаца...
```

## Полный цикл

```bash
# Всё одной командой
./scripts/rag_tools.sh full --query "Ваш вопрос" --clear

# Или по шагам
python scripts/pdf_to_markdown.py --input-dir data/documents/pdf_docs --output-dir data/documents/md_docs
python scripts/clean_markdown.py --input-dir data/documents/md_docs
python -m src.rag.md_chunker --input-dir data/documents/md_docs --output-dir data/documents/chunks
python -m src.rag.chunk_loader --clear
python -m src.rag.search "Ваш вопрос" --verbose
```

## Архитектура

```
data/
├── documents/
│   ├── pdf_docs/            # Исходные PDF (gitignored)
│   │   └── *.pdf
│   ├── md_docs/             # Markdown после конвертации и очистки
│   │   └── *.md
│   └── chunks/              # JSON чанки
│       ├── doc_name/
│       │   ├── index.json
│       │   ├── chunk_0000.json
│       │   └── ...
│       └── ...
└── embeddings/              # FAISS индекс
    ├── faiss.index
    ├── chunks_metadata.json
    └── index_metadata.json
```

## Настройки (.env)

```env
# RAG Settings
EMBEDDING_MODEL=all-MiniLM-L6-v2
TOP_K=3
EMBEDDINGS_DB_PATH=./data/embeddings
```

## Программное использование

```python
from src.rag import RAGService, ChunkResult

rag = RAGService()

# Поиск с метаданными
results = rag.query_with_metadata("ваш запрос", top_k=3)
for result in results:
    print(f"{result.source} (стр. {result.page}): {result.content[:100]}...")
```

## Стратегия работы с межстраничными абзацами

Абзац, начавшийся на одной странице и продолжающийся на другой, целиком относится к странице начала. Это сохраняет целостность мысли и предотвращает дублирование.

*Реализация в `md_chunker.py` — требуется доработка (см. следующий раздел).*

## Известные ограничения (требуют доработки)

1. **Межстраничные абзацы** — `md_chunker.py` пока обрабатывает каждую страницу независимо
2. **Слияние коротких абзацев** — нет объединения фрагментов < 50 символов с соседними чанками
3. **Фильтрация мусора** — `clean_markdown.py` не удаляет конвертационные заголовки (`# Конвертированный документ`), ISBN, копирайты
4. **Разбивка предложений** — эвристика 300/100 символов может дробить абзацы

## Troubleshooting

### Векторная база пуста
```bash
python -m src.rag.md_chunker
python -m src.rag.chunk_loader --clear
```

### Низкое качество поиска
1. Увеличьте `top_k` (больше результатов)
2. Снизьте `score_threshold` (выше召回)
3. Проверьте эмбеддинг-модель в `.env`

### Мусор в результатах
Проверьте Markdown после `clean_markdown.py` — если в нём есть конвертационные заголовки, номера страниц `## Страница 1` или плейсхолдеры, очистка работает некорректно.
