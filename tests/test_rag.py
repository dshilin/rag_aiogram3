import pytest

from src.rag.service import RAGService


@pytest.fixture
def rag_service():
    """Создать RAG сервис для тестов"""
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
