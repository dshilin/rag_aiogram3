import pytest

import requests

from src.llm.yandex_gpt import YandexGPTClient
from src.core.config import settings


class DummyResponse:
    def __init__(self, ok=True, status_code=200, text="", json_data=None):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


def test_build_model_uri_variants(monkeypatch):
    # Проверяем, что мы можем вычислить URI из folder id
    monkeypatch.setattr(settings, "yandex_folder_id", "folder123")

    client = YandexGPTClient()
    assert client._build_model_uri() == "gpt://folder123/yandexgpt/latest"

    client2 = YandexGPTClient(model="yandexgpt-lite")
    assert client2._build_model_uri() == "gpt://folder123/yandexgpt-lite/latest"

    # если модель уже полный URI, он должен быть использован без изменений
    raw = "gpt://folder123/special-model/v1"
    client3 = YandexGPTClient(model=raw)
    assert client3._build_model_uri() == raw


def test_build_model_uri_fails_without_folder(monkeypatch):
    monkeypatch.setattr(settings, "yandex_folder_id", "")
    client = YandexGPTClient()
    with pytest.raises(ValueError):
        client._build_model_uri()


def test_ask_sends_correct_payload(monkeypatch):
    monkeypatch.setattr(settings, "yandex_folder_id", "folder123")
    monkeypatch.setattr(settings, "yandex_api_key", "token")

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return DummyResponse(
            ok=True,
            status_code=200,
            json_data={"result": {"alternatives": [{"message": {"text": "ok"}}]}}
        )

    monkeypatch.setattr(requests, "post", fake_post)

    client = YandexGPTClient(model="yandexgpt-lite")
    result = client.ask("hello")

    assert result == "ok"
    assert captured['json']['modelUri'] == "gpt://folder123/yandexgpt-lite/latest"
    assert captured['headers']['Authorization'] == "Bearer token"

    # проверяем, что явный URI сохраняется
    client2 = YandexGPTClient(model="gpt://folder123/custom/v2")
    result2 = client2.ask("hi")
    assert captured['json']['modelUri'] == "gpt://folder123/custom/v2"


def test_ask_reports_unconfigured(monkeypatch):
    # если folder id или api key отсутствуют, получаем предупреждение
    monkeypatch.setattr(settings, "yandex_folder_id", None)
    monkeypatch.setattr(settings, "yandex_api_key", None)
    client = YandexGPTClient()
    reply = client.ask("foo")
    assert "не настроен" in reply
