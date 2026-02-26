# 📚 Chunking System - Быстрый старт

## 🎯 Назначение

Система разбивает Markdown документы на чанки с метаданными (источник, страница) для последующего RAG поиска.

## 📋 Полный пайплайн

### Шаг 1: PDF → Markdown
```bash
python scripts/pdf_to_markdown.py \
    --input-dir data/documents/pdf_docs \
    --output-dir data/documents/md_docs
```

### Шаг 2: Markdown → Chunks
```bash
python scripts/chunk_documents.py \
    --input-dir data/documents/md_docs \
    --output-dir data/documents/chunks \
    --chunk-size 500 \
    --overlap 50
```

### Шаг 3: Chunks → Vector Store
```bash
python -m src.rag.chunk_loader \
    --chunks-dir data/documents/chunks \
    --clear
```

### Шаг 4: Поиск
```bash
python -m src.rag.chunk_loader \
    --chunks-dir data/documents/chunks \
    --search "ваш запрос"
```

## 🔍 Поиск в коде

```python
from src.rag import RAGService

rag = RAGService()

# Поиск с метаданными
results = rag.query_with_metadata("запрос", top_k=3)

for result in results:
    print(f"📄 Источник: {result.source}")
    print(f"📑 Страница: {result.page}")
    print(f"📝 Текст: {result.content[:200]}")
```

## 📁 Структура чанка

```json
{
  "content": "Текст чанка...",
  "metadata": {
    "chunk_id": "a1b2c3d4e5f6g7h8",
    "source": "document_name",
    "page": 5,
    "chunk_index": 2,
    "start_char": 1500,
    "end_char": 2000,
    "total_chunks": 10
  }
}
```

## 🧪 Тесты

```bash
python -m pytest tests/test_chunking.py -v
```

## 📖 Примеры

```bash
python examples/rag_chunking_example.py
```

## 📝 Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--chunk-size` | 500 | Размер чанка в символах |
| `--overlap` | 50 | Перекрытие между чанками |
| `--top-k` | 3 | Количество результатов поиска |

## ⚙️ Конфигурация

В `.env`:
```bash
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K=3
EMBEDDING_MODEL=all-MiniLM-L6-v2
```
