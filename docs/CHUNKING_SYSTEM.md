# Система разбиения документов на чанки и поиска

## Обзор

Система предназначена для разбиения PDF документов на смысловые чанки (по абзацам) с последующим поиском по векторной базе данных с указанием точных цитат и источников.

## Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  PDF Документы  │ ──> │   Chunker        │ ──> │  JSON Чанки     │
│  (data/documents)│     │  (chunker.py)    │     │  (chunks/)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Ответ с        │ <── │   Search         │ <── │  FAISS Index    │
│  цитатами       │     │  (search.py)     │     │  (embeddings/)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Компоненты

### 1. Chunker (`src/rag/chunker.py`)

Разбивает PDF документы на чанки по абзацам.

**Ключевые особенности:**
- Разбиение по абзацам (разделитель: `\n\n`)
- Сохранение метаданных: источник, страница, уникальный ID
- **Универсальное решение для межстраничных абзацев:**
  - Абзац целиком относится к странице, где он **НАЧИНАЕТСЯ**
  - Предотвращает дублирование контента
  - Сохраняет целостность мысли

**Структура чанка:**
```json
{
  "content": "Текст абзаца...",
  "metadata": {
    "source": "document_name",
    "page": 5,
    "chunk_id": "a1b2c3d4e5f6",
    "paragraph_index": 42
  }
}
```

**Использование:**
```bash
# Разбить все PDF в data/documents
python -m src.rag.chunker

# Разбить с указанием директорий
python -m src.rag.chunker --input-dir data/documents --output-dir data/documents/chunks

# Только статистика без сохранения
python -m src.rag.chunker --no-save

# Превью первых 5 чанков
python -m src.rag.chunker --preview 5
```

### 2. Chunk Loader (`src/rag/chunk_loader.py`)

Загружает чанки из JSON файлов в векторное хранилище FAISS.

**Использование:**
```bash
# Индексация всех чанков
python -m src.rag.chunk_loader

# С очисткой существующего индекса
python -m src.rag.chunk_loader --clear

# С тестовым поиском
python -m src.rag.chunk_loader --search "Ваш вопрос"

# Пакетная загрузка (по 50 чанков)
python -m src.rag.chunk_loader --batch-size 50
```

### 3. Search (`src/rag/search.py`)

Поиск по векторной базе с выводом цитат и источников.

**Использование:**
```bash
# Единичный запрос
python -m src.rag.search "Что такое машинное обучение?"

# С указанием количества результатов
python -m src.rag.search "Ваш вопрос" --top-k 10

# С порогом схожести
python -m src.rag.search "Ваш вопрос" --threshold 0.5

# Подробный вывод
python -m src.rag.search "Ваш вопрос" --verbose

# Краткий формат (для Telegram)
python -m src.rag.search "Ваш вопрос" --short

# Интерактивный режим
python -m src.rag.search --interactive
```

**Пример вывода:**
```
────────────────────────────────────────────────────────────
📌 Результат #1 (релевантность: 0.8542)

📚 Источник: `machine_learning_basics`
📑 Страница: 15
🆔 ID чанка: `a1b2c3d4e5f6`

💬 Цитата:
> Машинное обучение — это подраздел искусственного интеллекта,
> который позволяет системам автоматически улучшать свою 
> производительность на основе опыта...
```

### 4. RAG Tools (`scripts/rag_tools.sh`)

Удобный скрипт для управления всем циклом.

**Использование:**
```bash
# Показать справку
./scripts/rag_tools.sh help

# Разбиение документов
./scripts/rag_tools.sh chunk

# Поиск
./scripts/rag_tools.sh search --query "Ваш вопрос"

# Интерактивный поиск
./scripts/rag_tools.sh search --interactive

# Полный цикл: разбиение + индексация + поиск
./scripts/rag_tools.sh full --query "Ваш вопрос"

# Полный цикл с очисткой базы
./scripts/rag_tools.sh full --query "Ваш вопрос" --clear
```

## Быстрый старт

### 1. Подготовка документов

Поместите PDF файлы в директорию `data/documents/`:
```bash
cp /path/to/your/document.pdf data/documents/
```

### 2. Разбиение на чанки

```bash
python -m src.rag.chunker
```

### 3. Индексация

```bash
python -m src.rag.chunk_loader --clear
```

### 4. Поиск

```bash
python -m src.rag.search "Ваш вопрос" --verbose
```

Или используйте интерактивный режим:
```bash
python -m src.rag.search --interactive
```

## Стратегия работы с межстраничными абзацами

**Проблема:** Абзац может начинаться на одной странице и продолжаться на другой.

**Решение:** Абзац целиком относится к странице, где он **НАЧИНАЕТСЯ**.

**Преимущества:**
1. ✅ Нет дублирования контента
2. ✅ Сохраняется целостность мысли
3. ✅ Пользователь получает полный контекст
4. ✅ Указание одной страницы (не диапазона)

**Пример:**
```
Страница 5:
  ...конец предыдущего абзаца.
  
  Начало нового важного абзаца, который описывает
  ключевую концепцию и продолжается на...

Страница 6:
  ...следующей странице. Этот абзац содержит важное
  объяснение...
```

**Результат:** Весь абзац будет в чанке с указанием `page: 5`

## API для программного использования

```python
from src.rag import (
    ParagraphChunker, 
    RAGService, 
    search_query,
    format_citation
)

# Разбиение документа
chunker = ParagraphChunker()
chunks, stats = chunker.chunk_pdf(Path("document.pdf"))

# Индексация
rag_service = RAGService()
rag_service.add_documents(
    texts=[c.content for c in chunks],
    metadatas=[c.to_dict()["metadata"] for c in chunks]
)

# Поиск
results = search_query(
    query="Ваш вопрос",
    rag_service=rag_service,
    top_k=5
)

# Форматирование результата
for i, result in enumerate(results, 1):
    print(format_citation(result, i))
```

## Настройки

Настройки находятся в `.env` файле:

```env
# RAG Settings
EMBEDDING_MODEL=all-MiniLM-L6-v2
CHUNK_SIZE=500        # Не используется при разбиении по абзацам
CHUNK_OVERLAP=50      # Не используется при разбиении по абзацам
TOP_K=5               # Количество результатов по умолчанию
EMBEDDINGS_DB_PATH=./data/embeddings
```

## Структура файлов

```
data/
├── documents/           # Исходные PDF файлы
│   ├── doc1.pdf
│   └── doc2.pdf
├── documents/chunks/    # Разбитые чанки (JSON)
│   ├── doc1/
│   │   ├── index.json
│   │   ├── chunk_0000.json
│   │   └── ...
│   └── doc2/
│       └── ...
└── embeddings/          # Векторное хранилище FAISS
    ├── faiss_index/
    │   ├── index.faiss
    │   └── index.pkl
    └── index_meta.pkl
```

## Troubleshooting

### Ошибка: "Векторная база пуста"
**Решение:** Сначала выполните разбиение и индексацию:
```bash
python -m src.rag.chunker
python -m src.rag.chunk_loader --clear
```

### Ошибка: "Директория не найдена"
**Решение:** Проверьте путь к директории с документами:
```bash
ls -la data/documents/
```

### Низкое качество поиска
**Решения:**
1. Увеличьте `top_k` для большего количества результатов
2. Установите порог схожести `--threshold 0.3`
3. Проверьте качество эмбеддингов (модель в настройках)

## Дополнительные ресурсы

- [LangChain Text Splitters](https://python.langchain.com/docs/modules/data_connection/document_transformers/)
- [FAISS Documentation](https://faiss.ai/)
- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
