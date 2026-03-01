# RAG Telegram Bot (aiogram3)

Telegram бот с RAG (Retrieval-Augmented Generation) для ответов на вопросы по базе знаний с использованием LLM.

## Особенности

- 🔍 **RAG поиск** — поиск по базе знаний с метаданными (источник, страница)
- 🤖 **LLM интеграция** — поддержка OpenAI, YandexGPT, VseGPT
- 💬 **Сессионная память** — хранение истории диалога в рамках сессии
- 🎯 **Классификация запросов** — LLM-классификатор для оптимизации ответов
- ⌨️ **Кнопки управления** — быстрое управление сессиями

## Структура проекта

```
rag_aiogram3/
├── src/
│   ├── bot/           # Обработчики, сессии, классификатор
│   ├── rag/           # RAG сервис и загрузчик чанков
│   ├── llm/           # LLM клиенты (OpenAI, YandexGPT, VseGPT)
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

## Конфигурация

### Переменные окружения

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `CHUNK_SIZE` | Размер чанка | 500 |
| `CHUNK_OVERLAP` | Перекрытие чанков | 50 |
| `TOP_K` | Количество результатов поиска | 3 |
| `EMBEDDING_MODEL` | Модель эмбеддингов | all-MiniLM-L6-v2 |
| `LLM_PROVIDER` | LLM провайдер (`openai`, `yandex`, `vsegpt`) | - |
| `LLM_MODEL` | Название модели | gpt-3.5-turbo |
| `LLM_TEMPERATURE` | Температура генерации | 0.3 |
| `LLM_MAX_TOKENS` | Максимум токенов в ответе | 500 |
| `OPENAI_API_KEY` | API ключ OpenAI | - |
| `YANDEX_API_KEY` | API ключ Yandex | - |
| `YANDEX_FOLDER_ID` | Folder ID Yandex Cloud | - |
| `VSEGPT_API_KEY` | API ключ VseGPT | - |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - |

### Выбор LLM провайдера

**OpenAI:**
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=your-api-key
```

**YandexGPT:**
```env
LLM_PROVIDER=yandex
LLM_MODEL=yandexgpt
YANDEX_API_KEY=your-api-key
YANDEX_FOLDER_ID=your-folder-id
```

**VseGPT:**
```env
LLM_PROVIDER=vsegpt
LLM_MODEL=gpt-4o-mini
VSEGPT_API_KEY=your-api-key
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

| Команда | Описание |
|---------|----------|
| `/start` | Начать новую сессию |
| `/end` | Завершить текущую сессию |
| `/help` | Показать справку |
| `/add` | Добавить документ |
| `/status` | Показать статус базы знаний |

## Кнопки управления сессией

После команды `/start` появляется клавиатура:

- **🔄 Новая сессия** — начать диалог заново (сброс истории)
- **⏹️ Завершить сессию** — завершить сессию и скрыть клавиатуру

## Классификация запросов

Бот автоматически классифицирует входящие сообщения:

| Категория | Описание | Реакция |
|-----------|----------|---------|
| `greeting` | Приветствие | Быстрый ответ без RAG |
| `help_request` | Просьба о помощи | Цитата + рекомендация группы АН |
| `off_topic` | Не относится к АН | Отказ отвечать |
| `an_question` | Вопрос по теме АН | Запуск RAG + LLM ответ |

Классификация происходит через LLM (один короткий запрос ~50 токенов).

## Сессионная память

- История диалога хранится в памяти (последние 10 сообщений)
- Сессия привязана к `user_id`
- Только вопросы по теме АН сохраняются в историю
- Приветствия и off-topic запросы не сохраняются

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

## Тесты

```bash
# Запустить все тесты
pytest tests/

# Запустить тесты классификатора
pytest tests/test_classifier.py -v

# Запустить тесты YandexGPT клиента
pytest tests/test_yandex_gpt_client.py -v
```

## Технологии

- **aiogram 3** — фреймворк для Telegram ботов
- **LangChain** — работа с RAG
- **FAISS** — векторное хранилище (CPU)
- **HuggingFace** — эмбеддинги (all-MiniLM-L6-v2)
- **PyMuPDF** — обработка PDF
- **loguru** — логирование
- **OpenAI API** — LLM провайдер
- **YandexGPT API** — LLM провайдер
- **VseGPT API** — LLM провайдер

## Документация

- [CHUNKING.md](docs/CHUNKING.md) — Подробная документация по системе чанков

## Архитектура обработки запроса

```
Сообщение пользователя
    ↓
LLM Классификатор
    ↓
┌─────────────────────────────────────┐
│ greeting     → быстрый ответ        │
│ help_request → цитата + рекомендация│
│ off_topic    → отказ                │
│ an_question  → RAG + LLM            │
└─────────────────────────────────────┘
```
