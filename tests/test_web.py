import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from src.web.router import router
from src.bot.classifier import QueryCategory
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_chat_greeting(client):
    """POST /api/chat with greeting returns greeting category"""
    with patch("src.web.router.classify_query", return_value=QueryCategory.GREETING):
        response = await client.post("/api/chat", json={
            "message": "Привет",
            "session_id": "test-session-1"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "greeting"
        assert "RAG-бот" in data["reply"]


@pytest.mark.asyncio
async def test_chat_help_request(client):
    with patch("src.web.router.classify_query", return_value=QueryCategory.HELP_REQUEST):
        response = await client.post("/api/chat", json={
            "message": "Помогите",
            "session_id": "test-session-2"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "help_request"
        assert "Анонимные Наркоманы" in data["reply"]


@pytest.mark.asyncio
async def test_chat_off_topic(client):
    with patch("src.web.router.classify_query", return_value=QueryCategory.OFF_TOPIC):
        response = await client.post("/api/chat", json={
            "message": "Погода",
            "session_id": "test-session-3"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "off_topic"


@pytest.mark.asyncio
async def test_chat_greeting_exact_reply(client):
    with patch("src.web.router.classify_query", return_value=QueryCategory.GREETING):
        response = await client.post("/api/chat", json={
            "message": "Привет",
            "session_id": "test-session-4"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "greeting"
        assert "RAG-бот" in data["reply"]


@pytest.mark.asyncio
async def test_chat_missing_message(client):
    """422 validation error for missing message"""
    response = await client.post("/api/chat", json={
        "session_id": "test-session-5"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_new_session(client):
    """POST /api/session/new resets session"""
    response = await client.post("/api/session/new", json={
        "session_id": "test-session-new"
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
