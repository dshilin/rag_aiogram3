# RAG Telegram Bot (aiogram3)

Telegram бот с RAG (Retrieval-Augmented Generation) для ответов на вопросы по базе знаний.

## Структура проекта

```
rag_aiogram3/
├── src/
│   ├── bot/           # Обработчики и диспетчер бота
│   ├── rag/           # RAG сервис
│   ├── core/          # Конфигурация
│   └── utils/         # Утилиты (логирование)
├── tests/             # Тесты
├── data/              # Данные (документы, embeddings)
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

5. Запустите бота:
```bash
python main.py
```

## Команды бота

- `/start` - Запустить бота
- `/help` - Показать справку
- `/add` - Добавить документ
- `/status` - Показать статус базы знаний

## Технологии

- **aiogram 3** - фреймворк для Telegram ботов
- **LangChain** - работа с RAG
- **FAISS** - векторное хранилище (CPU)
- **HuggingFace** - эмбеддинги
