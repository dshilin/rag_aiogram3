import pytest
import shutil
from pathlib import Path

from src.rag.service import RAGService


@pytest.fixture
def test_index_path(tmp_path):
    """Создать временную директорию для индекса"""
    index_path = tmp_path / "faiss_test"
    yield index_path
    if index_path.exists():
        shutil.rmtree(index_path)


@pytest.fixture
def rag_service(test_index_path, monkeypatch):
    """Создать RAG сервис для тестов"""
    # Переопределяем путь к индексу для тестов
    monkeypatch.setattr(
        "src.rag.service.settings.embeddings_db_path",
        str(test_index_path.parent),
    )
    service = RAGService()
    yield service
    service.clear()


def test_add_and_query(rag_service: RAGService):
    """Тест добавления и поиска документов"""
    # Добавляем тестовый документ
    test_text = "Москва - столица России. Население около 12 миллионов человек."
    rag_service.add_documents([test_text])
    
    # Выполняем поиск
    result = rag_service.query("Какой город столица России?")
    
    assert result is not None
    assert "Москва" in result


def test_empty_query(rag_service: RAGService):
    """Тест поиска по пустой базе"""
    result = rag_service.query("Любой вопрос")
    assert result is None


def test_document_count(rag_service: RAGService):
    """Тест подсчета документов"""
    initial_count = rag_service.get_document_count()
    
    rag_service.add_documents(["Тестовый документ 1"])
    rag_service.add_documents(["Тестовый документ 2"])
    
    final_count = rag_service.get_document_count()
    assert final_count >= initial_count + 2


class TestMetadataFilter:
    def test_filter_by_book_title(self, rag_service):
        rag_service.add_documents(
            ["Текст про первый шаг.", "Текст про второй шаг."],
            [{"book_title": "Базовый текст АН"}, {"book_title": "Это работает"}],
        )
        results = rag_service.query_with_metadata(
            "первый шаг", top_k=5, metadata_filter={"book_title": "Базовый текст АН"}
        )
        assert all(r.metadata.get("book_title") == "Базовый текст АН" for r in results)

    def test_filter_excludes_non_matching(self, rag_service):
        rag_service.add_documents(
            ["Текст про капитуляцию.", "Текст про смирение."],
            [{"book_title": "Базовый текст АН"}, {"book_title": "Это работает"}],
        )
        results = rag_service.query_with_metadata(
            "капитуляция", top_k=5, metadata_filter={"book_title": "Несуществующая книга"}
        )
        assert len(results) == 0


class TestDefinitionExpansion:
    def test_definition_prepended_to_body(self, rag_service):
        def_id = "def_001"
        rag_service.add_documents(
            ["Текст главы."],
            [{"definition_ref_id": def_id, "chunk_role": "body", "book_title": "Тест"}],
        )
        rag_service.add_documents(
            ["«Определение шага.»"],
            [{"chunk_id": def_id, "chunk_role": "definition", "book_title": "Тест"}],
        )
        results = rag_service.query_with_metadata(
            "текст главы", top_k=5, expand_definitions=True
        )
        assert any("[Определение]" in r.content for r in results)
