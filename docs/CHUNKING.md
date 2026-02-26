# Chunking System Documentation

Система разделения документов на чанки с метаданными для RAG поиска.

## Архитектура

```
PDF Documents → pdf_to_markdown.py → Markdown Files
                                             ↓
Markdown Files → chunk_documents.py → JSON Chunks (с метаданными)
                                             ↓
JSON Chunks → chunk_loader.py → FAISS Vector Store
                                             ↓
Vector Store → RAG Service → Поиск с метаданными
```

## Структура чанка

Каждый чанк сохраняется в отдельном JSON файле:

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

## Использование

### 1. Конвертация PDF в Markdown

```bash
python scripts/pdf_to_markdown.py --input-dir data/documents/pdf_docs --output-dir data/documents/md_docs
```

### 2. Разделение на чанки

```bash
python scripts/chunk_documents.py \
    --input-dir data/documents/md_docs \
    --output-dir data/documents/chunks \
    --chunk-size 500 \
    --overlap 50
```

**Параметры:**
- `--chunk-size`: Размер чанка в символах (по умолчанию: 500)
- `--overlap`: Перекрытие между чанками (по умолчанию: 50)

### 3. Загрузка в RAG систему

```bash
python -m src.rag.chunk_loader \
    --chunks-dir data/documents/chunks \
    --clear
```

**Параметры:**
- `--clear`: Очистить существующий индекс перед загрузкой
- `--search "запрос"`: Выполнить тестовый поиск

### 4. Поиск с метаданными в коде

```python
from src.rag.service import RAGService

rag = RAGService()

# Поиск с метаданными
results = rag.query_with_metadata("ваш запрос", top_k=3)

for result in results:
    print(f"Источник: {result.source}")
    print(f"Страница: {result.page}")
    print(f"Текст: {result.content[:200]}")
    print(f"Score: {result.score}")
    print("---")
```

### 5. Форматированный ответ

```python
from src.rag.chunk_loader import search_and_format
from src.rag.service import RAGService

rag = RAGService()
response = search_and_format("ваш запрос", rag, top_k=3)
print(response)
```

**Пример вывода:**
```
🔍 Найдено результатов: 3

──────────────────────────────────────
**Результат 1**
📄 **Источник**: technical_doc
📑 **Страница**: 5
📝 **Текст**:
Содержание чанка...

──────────────────────────────────────
**Результат 2**
📄 **Источник**: technical_doc
📑 **Страница**: 12
📝 **Текст**:
Содержание чанка...
```

## Поиск тестового запроса

Можно найти чанк по тексту (без векторного поиска):

```bash
python scripts/chunk_documents.py \
    --output-dir data/documents/chunks \
    --search "ключевые слова"
```

## Структура выходных данных

```
data/documents/chunks/
├── document_name_1/
│   ├── index.json              # Индекс документа
│   ├── a1b2c3d4e5f6g7h8.json   # Чанк 1
│   ├── b2c3d4e5f6g7h8i9.json   # Чанк 2
│   └── ...
├── document_name_2/
│   ├── index.json
│   └── ...
└── processing_stats.json        # Статистика обработки
```

## Интеграция с ботом

```python
from src.rag import RAGService, search_and_format

# В хендлере бота
@dp.message(Command("search"))
async def search_command(message: Message, command: CommandObject):
    query = command.args
    rag = RAGService()
    
    results = rag.query_with_metadata(query, top_k=3)
    
    if not results:
        await message.answer("❌ Ничего не найдено")
        return
    
    response = search_and_format(query, rag, top_k=3)
    await message.answer(response)
```

## Метаданные чанка

| Поле | Описание |
|------|----------|
| `chunk_id` | Уникальный MD5 хеш идентификатор |
| `source` | Имя файла-источника (без расширения) |
| `page` | Номер страницы в исходном документе |
| `chunk_index` | Индекс чанка в пределах страницы |
| `start_char` | Позиция начала в тексте страницы |
| `end_char` | Позиция конца в тексте страницы |
| `total_chunks` | Общее количество чанков на странице |

## Преимущества

1. **Точное цитирование**: Агент возвращает не только текст, но и источник с номером страницы
2. **Верификация**: Пользователь может проверить информацию в оригинальном документе
3. **Контекст**: Метаданные помогают понять контекст найденной информации
4. **Масштабируемость**: JSON формат позволяет легко добавлять новые метаданные
