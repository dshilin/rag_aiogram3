# RAG Telegram Bot (aiogram3)

Telegram бот с RAG (Retrieval-Augmented Generation) для ответов на вопросы по базе знаний.

## Структура проекта

```
rag_aiogram3/
├── src/
│   ├── bot/           # Обработчики и диспетчер бота
│   ├── rag/           # RAG сервис и загрузчик чанков
│   ├── core/          # Конфигурация
│   └── utils/         # Утилиты (логирование)
├── scripts/           # Скрипты обработки документов
│   ├── pdf_to_markdown.py    # Конвертация PDF → Markdown
│   ├── chunk_documents.py    # Разделение на чанки
│   └── clean_markdown.py     # Очистка Markdown
├── examples/          # Примеры использования
├── docs/              # Документация
├── tests/             # Тесты
├── data/              # Данные
│   ├── documents/     # Документы (PDF, Markdown, Chunks)
│   └── embeddings/    # FAISS индекс
└── logs/              # Логи
```

## Установка

1. Клонируйте репозиторий
2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Скопируйте `.env.example` в `.env` и заполните:
```bash
cp .env.example .env
```

## Подготовка базы знаний

### 1. Конвертация PDF в Markdown

```bash
python scripts/pdf_to_markdown.py \
    --input-dir data/documents/pdf_docs \
    --output-dir data/documents/md_docs
```

### 2. Разделение на чанки с метаданными

```bash
python scripts/chunk_documents.py \
    --input-dir data/documents/md_docs \
    --output-dir data/documents/chunks \
    --chunk-size 500 \
    --overlap 50
```

### 3. Загрузка чанков в RAG систему

```bash
python -m src.rag.chunk_loader \
    --chunks-dir data/documents/chunks \
    --clear
```

### 4. Тестовый поиск

```bash
python -m src.rag.chunk_loader \
    --chunks-dir data/documents/chunks \
    --search "ваш запрос"
```

## Запуск бота

```bash
python main.py
```

## Команды бота

- `/start` - Запустить бота
- `/help` - Показать справку
- `/add` - Добавить документ
- `/status` - Показать статус базы знаний
- `/search <запрос>` - Поиск по базе знаний

## Примеры использования

### Поиск с метаданными в коде

```python
from src.rag import RAGService

rag = RAGService()

# Поиск с метаданными (источник, страница)
results = rag.query_with_metadata("ваш запрос", top_k=3)

for result in results:
    print(f"Источник: {result.source}")
    print(f"Страница: {result.page}")
    print(f"Текст: {result.content[:200]}")
```

### Форматированный ответ

```python
from src.rag import search_and_format, RAGService

rag = RAGService()
response = search_and_format("ваш запрос", rag, top_k=3)
print(response)
```

**Вывод:**
```
🔍 Найдено результатов: 3

──────────────────────────────────────
**Результат 1**
📄 **Источник**: technical_doc
📑 **Страница**: 5
📝 **Текст**:
Содержание чанка...
```

### Запуск примеров

```bash
python examples/rag_chunking_example.py
```

## Технологии

- **aiogram 3** - фреймворк для Telegram ботов
- **LangChain** - работа с RAG
- **FAISS** - векторное хранилище (CPU)
- **HuggingFace** - эмбеддинги (all-MiniLM-L6-v2)
- **PyMuPDF** - обработка PDF
- **loguru** - логирование

## Документация

- [CHUNKING.md](docs/CHUNKING.md) - Подробная документация по системе чанков

## Конфигурация

Основные параметры в `.env`:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `CHUNK_SIZE` | Размер чанка | 500 |
| `CHUNK_OVERLAP` | Перекрытие чанков | 50 |
| `TOP_K` | Количество результатов поиска | 3 |
| `EMBEDDING_MODEL` | Модель эмбеддингов | all-MiniLM-L6-v2 |
