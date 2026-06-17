# FastAPI Web UI Design

## Overview

Веб-чат поверх существующей RAG + LLM логики Telegram бота. Состоит из одной HTML-страницы с диалоговым окном. FastAPI запускается в том же процессе, что и Telegram-бот.

## Architecture

```
main.py
├── asyncio.gather(
│   ├── dispatcher.start_polling()   # Telegram bot
│   └── uvicorn.Server.serve()       # FastAPI web server
│   )
```

FastAPI приложение инициализируется в `main.py`, роутер регистрируется на `app.include_router()`. Новый модуль `src/web/`:

```
src/web/
├── __init__.py
├── router.py          # FastAPI router (endpoints)
├── templates/
│   └── chat.html      # Jinja2 template, single page
└── static/
    └── chat.js        # Vanilla JS
```

Все существующие классы используются напрямую:
- `SessionManager` — для сессионной памяти
- `QueryClassifier` — для классификации запросов
- `RAGService` — для поиска по базе знаний
- `LLMFactory` / `LLMClient` — для генерации ответов

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | HTML page with chat |
| POST | `/api/chat` | Send message, get reply |
| POST | `/api/session/new` | Reset session (clear history) |

### POST /api/chat

Request:
```json
{
  "message": "string",
  "session_id": "string (UUID)"
}
```

Response (greeting/help/off_topic):
```json
{
  "reply": "string",
  "category": "greeting|help_request|off_topic"
}
```

Response (an_question):
```json
{
  "reply": "string",
  "category": "an_question",
  "sources": [
    {"source": "string", "page": "int|null", "content": "string"}
  ]
}
```

### POST /api/session/new

Request:
```json
{
  "session_id": "string (UUID)"
}
```

Response:
```json
{
  "success": true
}
```

## Data Flow

```
Browser → POST /api/chat {message, session_id}
  → SessionManager.get_session(session_id)
  → QueryClassifier.classify(message)
    ├─ greeting     → immediate reply (no RAG/LLM)
    ├─ help_request → standard NA help reply
    ├─ off_topic    → refusal reply
    └─ an_question  →
        → RAGService.query_with_metadata(message, top_k=3)
        → LLMClient.ask(question=message, context=chunks, sources=sources, history=messages)
        → SessionManager.add_message(session_id, user_msg, bot_reply)
  → JSON response
```

Pipeline идентичен Telegram-боту (handlers.py), только вход — HTTP вместо Telegram update.

## Session Management

- При первом GET `/` сервер генерирует UUID и возвращает в cookie
- UUID используется как `session_id` (user_id в SessionManager)
- Клиент прикрепляет session_id к каждому запросу
- В историю сохраняются только вопросы категории `an_question` (как и в Telegram боте)

## Web Interface

### HTML (chat.html)

- `<div id="messages">` — история диалога
- `<input id="message-input">` — поле ввода
- `<button id="new-session-btn">🔄 Новая сессия</button>` — одна кнопка управления
- Никаких заголовков, меню, футеров

### JS (chat.js, vanilla)

- `fetch` POST `/api/chat` при отправке сообщения
- Добавление сообщения пользователя и ответа бота в `#messages`
- Автоскролл вниз
- Кнопка "🔄 Новая сессия" → POST `/api/session/new` → очистка окна
- Формат ответа бота: текст + ссылки на источники под ответом

### CSS

- Минимальный CSS (встроен в `<style>` в chat.html)
- Светлый фон, отступы
- Сообщения пользователя справа, бота — слева
- Без внешних библиотек и CDN

## Dependencies

Добавить в `requirements.txt`:
- `fastapi>=0.110.0`
- `uvicorn[standard]>=0.29.0`
- `jinja2>=3.1.0`
- `python-multipart>=0.0.9`

## Docker

В `main.py` FastAPI запускается через `uvicorn.Server.serve()` как asyncio задача. Порты не добавляются — веб-сервер слушает на существующем `EXPOSE 8080` в Dockerfile.

## Testing

- `tests/test_web.py` — тесты эндпоинтов через `TestClient`
  - Проверка POST `/api/chat` с разными категориями
  - Проверка POST `/api/session/new`
  - Проверка GET `/`
  - Моками для RAG/LLM/Classifer (как в существующих тестах)

## Files to Create

1. `src/web/__init__.py` — пустой
2. `src/web/router.py` — FastAPI роутер
3. `src/web/templates/chat.html` — Jinja2 шаблон
4. `src/web/static/chat.js` — клиентский JS
5. `tests/test_web.py` — тесты

## Files to Modify

1. `main.py` — добавить инициализацию FastAPI, запуск uvicorn в asyncio.gather
2. `requirements.txt` — добавить зависимости
