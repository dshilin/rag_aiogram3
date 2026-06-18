# FastAPI Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-page web chat UI (FastAPI) alongside the existing Telegram bot, sharing the same RAG + LLM + Session logic.

**Architecture:** FastAPI app runs in the same process as the aiogram bot via `asyncio.gather`. Web router in `src/web/router.py`. Session identified via UUID cookie, mapped to `int` for `SessionManager`. All backend classes reused directly — no duplication.

**Tech Stack:** FastAPI, uvicorn, Jinja2, vanilla JS, existing RAG/LLM/Session modules

---

## File Structure

### Create:
```
src/web/__init__.py
src/web/router.py         # FastAPI router with endpoints
src/web/templates/chat.html  # Jinja2 template
src/web/static/chat.js    # Client-side JS
tests/test_web.py         # Web endpoint tests
```

### Modify:
```
requirements.txt           # Add fastapi, uvicorn, jinja2, python-multipart
main.py                    # Init FastAPI, run uvicorn alongside polling
```

---

### Task 1: Add dependencies and create package

**Files:**
- Modify: `requirements.txt`
- Create: `src/web/__init__.py`

- [ ] **Step 1: Add FastAPI dependencies to requirements.txt**

```
# Web UI
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
jinja2>=3.1.0
python-multipart>=0.0.9

# Testing (add to existing pytest lines)
httpx>=0.27.0
```

- [ ] **Step 2: Create src/web package**

Create empty `src/web/__init__.py`.

- [ ] **Step 3: Commit**

```
git add requirements.txt src/web/__init__.py
git commit -m "chore: add FastAPI dependencies and web package"
```

---

### Task 2: Web router with POST /api/chat

**Files:**
- Create: `src/web/router.py`
- Test: `tests/test_web.py`

This endpoint receives a message + session_id, runs it through the same pipeline as `handlers.py:handle_text`, returns the bot reply as JSON.

- [ ] **Step 1: Write failing test for /api/chat endpoint**

`tests/test_web.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, Mock
from src.web.router import router
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_chat_greeting(client):
    """POST /api/chat with greeting returns immediate reply"""
    response = await client.post("/api/chat", json={
        "message": "Привет",
        "session_id": "test-session-1"
    })
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["category"] in ["greeting", "help_request", "off_topic", "an_question"]
```

- [ ] **Step 2: Run to verify it fails**

```
cd /home/claw/workspace/rag_aiogram3
pip install httpx
pytest tests/test_web.py::test_chat_greeting -v
```
Expected: ImportError (router module doesn't exist yet)

- [ ] **Step 3: Create FastAPI router with /api/chat**

`src/web/router.py`:
```python
import uuid
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.rag.service import RAGService
from src.llm import get_llm_client
from src.core.config import settings
from src.bot.session import session_manager
from src.bot.classifier import classify_query, QueryCategory

router = APIRouter()

rag_service = RAGService()

llm_client = None
USE_LLM = False
try:
    llm_client = get_llm_client(
        provider=settings.llm_provider,
        model=settings.llm_model or None,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    USE_LLM = True
except (ValueError, Exception):
    llm_client = None
    USE_LLM = False


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    reply: str
    category: str
    sources: Optional[list[dict]] = None


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    user_id = abs(hash(req.session_id))
    query = req.message

    if USE_LLM and llm_client:
        category = classify_query(llm_client, query)

        if category == QueryCategory.GREETING:
            return ChatResponse(
                reply="👋 Привет! Я RAG-бот с литературой АН. Задайте вопрос по теме выздоровления.",
                category="greeting",
            )

        elif category == QueryCategory.HELP_REQUEST:
            return ChatResponse(
                reply=(
                    "В нашей литературе на эту тему сказано:\n\n"
                    "«Анонимные Наркоманы — это сообщество мужчин и женщин, которые делятся своим опытом, "
                    "силой и надеждой, чтобы помочь друг другу выздороветь от наркомании.»\n\n"
                    "Базовый текст АН, стр. XXI\n\n"
                    "Рекомендуем посетить ближайшую группу АН в вашем регионе."
                ),
                category="help_request",
            )

        elif category == QueryCategory.OFF_TOPIC:
            return ChatResponse(
                reply="Этот вопрос не относится к литературе АН.",
                category="off_topic",
            )

    session_history = session_manager.get_history(user_id, limit=10)

    if USE_LLM and llm_client:
        results = rag_service.query_with_metadata(query, top_k=5, score_threshold=0.3)

        if results:
            context_parts = []
            sources = []
            for chunk in results:
                context_parts.append(
                    f"[Источник: {chunk.source}, стр. {chunk.page}]\n{chunk.content}"
                )
                sources.append({
                    "source": chunk.source,
                    "page": chunk.page,
                    "content": chunk.content[:200],
                })

            context = "\n\n---\n\n".join(context_parts)

            answer = llm_client.ask(
                question=query,
                context=context,
                sources=[f"{s['source']} (стр. {s['page']})" for s in sources],
                conversation_history=session_history,
            )

            if sources:
                sources_text = "\n\n📚 **Источники:**\n"
                sources_text += "\n".join(f"• {s['source']} (стр. {s['page']})" for s in sources)
                answer += sources_text

            response = answer
        else:
            response = (
                "😕 Не нашел информацию по вашему запросу в литературе АН.\n\n"
                "Попробуйте переформулировать вопрос или обратитесь к:\n"
                "• Базовому тексту АН\n"
                "• Ежедневнику «Только Сегодня»\n"
                "• Книге «Это работает – как и почему»"
            )
    else:
        result = rag_service.query(query)
        if result:
            response = f"💡 Ответ:\n\n{result}"
        else:
            response = (
                "😕 Не нашел информацию по вашему запросу.\n\n"
                "Попробуйте переформулировать вопрос или добавьте больше документов в базу знаний."
            )

    session_manager.add_message(user_id, "user", query)
    session_manager.add_message(user_id, "assistant", response)

    return ChatResponse(reply=response, category="an_question", sources=sources if USE_LLM else None)
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/claw/workspace/rag_aiogram3
pytest tests/test_web.py::test_chat_greeting -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```
git add src/web/router.py tests/test_web.py
git commit -m "feat: add /api/chat endpoint"
```

---

### Task 3: POST /api/session/new and GET /

**Files:**
- Modify: `src/web/router.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_web.py`:
```python
@pytest.mark.asyncio
async def test_new_session(client):
    """POST /api/session/new resets session"""
    response = await client.post("/api/session/new", json={
        "session_id": "test-session-1"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_get_index(client):
    """GET / returns HTML page"""
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_web.py::test_new_session tests/test_web.py::test_get_index -v
```
Expected: 404 Not Found

- [ ] **Step 3: Add endpoints to router**

Add to `src/web/router.py`:
```python
class NewSessionRequest(BaseModel):
    session_id: str


class NewSessionResponse(BaseModel):
    success: bool


@router.post("/api/session/new", response_model=NewSessionResponse)
async def new_session(req: NewSessionRequest):
    user_id = abs(hash(req.session_id))
    session_manager.start_new_session(user_id)
    return NewSessionResponse(success=True)


@router.get("/")
async def index(request: Request):
    return HTMLResponse(INDEX_HTML)
```

Also add import at top of router.py:
```python
from fastapi.responses import HTMLResponse
```

Add `INDEX_HTML` constant at end of `router.py` (placeholder — will be replaced by template in Task 4):
```python
INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>RAG Chat</title></head>
<body><p>Loading...</p></body>
</html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_web.py::test_new_session tests/test_web.py::test_get_index -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```
git add src/web/router.py tests/test_web.py
git commit -m "feat: add /api/session/new and GET / endpoints"
```

---

### Task 4: Frontend — HTML template

**Files:**
- Create: `src/web/templates/chat.html`

- [ ] **Step 1: Create chat.html with inline CSS**

`src/web/templates/chat.html`:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; height: 100vh; display: flex; flex-direction: column; background: #f5f5f5; }
        #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.4; white-space: pre-wrap; }
        .msg.user { align-self: flex-end; background: #007aff; color: #fff; }
        .msg.bot { align-self: flex-start; background: #e9e9eb; color: #000; }
        #input-area { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #ccc; background: #fff; }
        #message-input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; }
        #send-btn, #new-session-btn { padding: 10px 16px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; }
        #send-btn { background: #007aff; color: #fff; }
        #new-session-btn { background: #e9e9eb; color: #000; }
        #send-btn:disabled { opacity: 0.5; }
    </style>
</head>
<body>
    <div id="messages"></div>
    <div id="input-area">
        <input id="message-input" type="text" placeholder="Введите сообщение..." autofocus>
        <button id="send-btn">Отправить</button>
        <button id="new-session-btn">🔄 Новая сессия</button>
    </div>
    <script src="/static/chat.js"></script>
</body>
</html>
```

- [ ] **Step 2: Update router.py to serve the template**

In `src/web/router.py`, update the import and the `GET /` handler:
```python
from pathlib import Path
from fastapi.responses import HTMLResponse

TEMPLATE_DIR = Path(__file__).parent / "templates"


@router.get("/")
async def index():
    html = (TEMPLATE_DIR / "chat.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
```

Remove the `INDEX_HTML` constant.

- [ ] **Step 3: Update test to verify HTML is served correctly**

```python
@pytest.mark.asyncio
async def test_get_index_contains_chat(client):
    response = await client.get("/")
    assert "RAG Chat" in response.text
    assert "message-input" in response.text
```

- [ ] **Step 4: Commit**

```
git add src/web/templates/chat.html src/web/router.py tests/test_web.py
git commit -m "feat: add chat HTML template"
```

---

### Task 5: Frontend — JS client

**Files:**
- Create: `src/web/static/chat.js`

- [ ] **Step 1: Create chat.js**

`src/web/static/chat.js`:
```javascript
(function() {
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const newSessionBtn = document.getElementById('new-session-btn');

    function getSessionId() {
        let sid = localStorage.getItem('session_id');
        if (!sid) {
            sid = crypto.randomUUID();
            localStorage.setItem('session_id', sid);
        }
        return sid;
    }

    function addMessage(text, role) {
        const el = document.createElement('div');
        el.className = 'msg ' + role;
        el.textContent = text;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text) return;
        inputEl.value = '';
        sendBtn.disabled = true;

        addMessage(text, 'user');

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, session_id: getSessionId() }),
            });
            const data = await res.json();
            addMessage(data.reply, 'bot');
        } catch (e) {
            addMessage('⚠️ Ошибка соединения с сервером', 'bot');
        } finally {
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    async function newSession() {
        await fetch('/api/session/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: getSessionId() }),
        });
        messagesEl.innerHTML = '';
        addMessage('🔄 Новая сессия начата. История диалога очищена.', 'bot');
        inputEl.focus();
    }

    sendBtn.addEventListener('click', sendMessage);
    inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') sendMessage();
    });
    newSessionBtn.addEventListener('click', newSession);
})();
```

- [ ] **Step 2: Configure FastAPI to serve static files**

No changes to router.py — static files are mounted in `main.py` (Task 6).

- [ ] **Step 3: Commit**

```
git add src/web/static/chat.js
git commit -m "feat: add client-side JS for chat"
```

---

### Task 6: Integration — update main.py

**Files:**
- Modify: `main.py`
- Modify: `src/web/router.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_web.py`:
```python
@pytest.mark.asyncio
async def test_chat_flow(client):
    """Full flow: new session -> send message -> get reply"""
    # Start new session
    await client.post("/api/session/new", json={"session_id": "flow-test-1"})
    # Send message
    resp = await client.post("/api/chat", json={
        "message": "Привет",
        "session_id": "flow-test-1"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
```

- [ ] **Step 2: Update main.py to init FastAPI and run both servers**

```python
import asyncio
from pathlib import Path

from loguru import logger
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.bot.dispatcher import dp, bot
from src.bot.handlers import router
from src.utils.logging import setup_logging, set_request_id, generate_request_id
from src.web.router import router as web_router

# FastAPI app
app = FastAPI(title="RAG Chat")
app.include_router(web_router)

STATIC_DIR = Path(__file__).parent / "src" / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def main():
    set_request_id(generate_request_id())
    setup_logging()

    # Telegram bot
    dp.include_router(router)
    logger.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)

    # FastAPI web server
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)

    # Run both
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
```

- [ ] **Step 3: Run tests to verify**

```
cd /home/claw/workspace/rag_aiogram3
pytest tests/test_web.py -v
```
Expected: All tests PASS

- [ ] **Step 4: Commit**

```
git add main.py tests/test_web.py
git commit -m "feat: integrate FastAPI with bot in main.py"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run all existing tests**

```
cd /home/claw/workspace/rag_aiogram3
pytest -v
```
Expected: All tests PASS (both old and new)

- [ ] **Step 2: Commit any final adjustments**

```
git add -A
git commit -m "chore: final adjustments after FastAPI integration"
```
