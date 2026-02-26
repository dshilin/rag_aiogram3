import os
import pickle
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import faiss
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore

from src.core.config import settings

# Константы
TEST_EMBEDDING_TEXT = "test"
DEFAULT_METADATA = {}


@dataclass
class ChunkResult:
    """Результат поиска с метаданными"""
    content: str
    source: str
    page: int
    chunk_id: str
    score: float = 0.0

    def to_dict(self) -> dict:
        """Конвертировать в словарь"""
        return {
            "content": self.content,
            "source": self.source,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "score": self.score,
        }

    def format_for_response(self) -> str:
        """Форматировать для ответа пользователю"""
        return (
            f"📄 **Источник**: {self.source}\n"
            f"📑 **Страница**: {self.page}\n"
            f"📝 **Текст**:\n{self.content}"
        )


class RAGService:
    """Сервис для работы с RAG (Retrieval-Augmented Generation)"""

    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        self.index_path = Path(settings.embeddings_db_path) / "faiss_index"
        self.meta_path = Path(settings.embeddings_db_path) / "index_meta.pkl"

        # Загружаем существующий индекс или создаем новый
        if self.index_path.exists() and self.meta_path.exists():
            self.vectorstore = FAISS.load_local(
                str(self.index_path),
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
        else:
            self.vectorstore = None

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
        )

    def _ensure_index(self):
        """Создать индекс если не существует"""
        if self.vectorstore is not None:
            return

        # Определяем размерность на основе тестового вектора
        sample_embedding = self.embeddings.embed_query(TEST_EMBEDDING_TEXT)
        dim = len(sample_embedding)

        # Инициализируем FAISS индекс
        index = faiss.IndexFlatL2(dim)
        docstore = InMemoryDocstore()
        self.vectorstore = FAISS(self.embeddings, index, docstore, DEFAULT_METADATA)

        # Инициализируем индекс с пустым документом, затем удаляем его
        self.vectorstore.add_texts([TEST_EMBEDDING_TEXT])
        first_doc_id = next(iter(self.vectorstore.index_to_docstore_id.values()), None)
        if first_doc_id:
            self.vectorstore.delete([first_doc_id])

    def add_documents(self, texts: list[str], metadatas: Optional[list[dict]] = None):
        """
        Добавить документы в векторное хранилище

        Args:
            texts: Список текстов для добавления
            metadatas: Список метаданных для каждого текста
                      (source, page, chunk_id, etc.)
        """
        self._ensure_index()

        documents = []
        for i, text in enumerate(texts):
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {}
            documents.append(Document(page_content=text, metadata=metadata))

        if documents:
            self.vectorstore.add_documents(documents)
            self._save_index()

    def query(self, question: str, top_k: Optional[int] = None) -> Optional[str]:
        """Выполнить поиск и вернуть ответ (без метаданных, для совместимости)"""
        results = self.query_with_metadata(question, top_k)

        if not results:
            return None

        # Конкатенируем найденные фрагменты
        context = "\n\n".join([r.content for r in results])
        return context

    def query_with_metadata(
        self,
        question: str,
        top_k: Optional[int] = None,
        score_threshold: float = 0.0,
    ) -> list[ChunkResult]:
        """
        Выполнить поиск с возвратом метаданных

        Args:
            question: Запрос для поиска
            top_k: Количество результатов
            score_threshold: Порог схожести

        Returns:
            Список ChunkResult с метаданными
        """
        if self.vectorstore is None:
            return []

        if top_k is None:
            top_k = settings.top_k

        # Поиск с оценкой схожести
        results = self.vectorstore.similarity_search_with_score(question, k=top_k)

        if not results:
            return []

        chunk_results = []
        for doc, score in results:
            if score < score_threshold:
                continue

            metadata = doc.metadata
            chunk_result = ChunkResult(
                content=doc.page_content,
                source=metadata.get("source", "unknown"),
                page=metadata.get("page", 0),
                chunk_id=metadata.get("chunk_id", metadata.get("chunk_index", "unknown")),
                score=score,
            )
            chunk_results.append(chunk_result)

        # Сортируем по score (лучшие сначала)
        chunk_results.sort(key=lambda x: x.score, reverse=True)

        return chunk_results

    def _save_index(self):
        """Сохранить индекс на диск"""
        self.index_path.mkdir(parents=True, exist_ok=True)
        self.vectorstore.save_local(str(self.index_path))

        # Сохраняем метаданные
        with open(self.meta_path, "wb") as f:
            pickle.dump({"doc_count": len(self.vectorstore.index_to_docstore_id)}, f)

    def get_document_count(self) -> int:
        """Получить количество документов в хранилище"""
        if self.vectorstore is None:
            return 0
        try:
            return len(self.vectorstore.index_to_docstore_id)
        except Exception:
            return 0

    def clear(self):
        """Очистить векторное хранилище"""
        self.vectorstore = None
        if self.index_path.exists():
            # FAISS сохраняет в несколько файлов
            import shutil
            shutil.rmtree(self.index_path, ignore_errors=True)
        if self.meta_path.exists():
            os.remove(self.meta_path)
