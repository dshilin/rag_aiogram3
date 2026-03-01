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
from loguru import logger

from src.core.config import settings
from src.utils.logging import trace, log_call_flow

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

        # Пути к индексам (поддержка старого и нового формата)
        self.index_path = Path(settings.embeddings_db_path) / "faiss_index"
        self.meta_path = Path(settings.embeddings_db_path) / "index_meta.pkl"
        
        # Новый формат индекса (из build_faiss_index.py)
        self.new_index_path = Path(settings.embeddings_db_path) / "faiss.index"
        self.new_meta_path = Path(settings.embeddings_db_path) / "index_metadata.json"
        self.chunks_meta_path = Path(settings.embeddings_db_path) / "chunks_metadata.json"

        # Загружаем существующий индекс или создаем новый
        self.vectorstore = self._load_index()

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
        )

    def _load_index(self):
        """
        Загрузить FAISS индекс (поддержка старого и нового формата)

        Returns:
            FAISS векторное хранилище или None
        """
        # 1. Пробуем загрузить новый формат (faiss.index + chunks_metadata.json)
        if self.new_index_path.exists() and self.chunks_meta_path.exists():
            log_call_flow(f"Loading new format index: {self.new_index_path}")
            try:
                import json
                index = faiss.read_index(str(self.new_index_path))
                
                # Загружаем метаданные чанков
                chunks_data = json.loads(self.chunks_meta_path.read_text(encoding="utf-8"))
                chunks = chunks_data.get("chunks", [])
                
                # Создаем векторное хранилище с загруженным индексом
                from langchain_community.vectorstores import FAISS
                from langchain_core.documents import Document
                
                # Создаем документы и добавляем их в docstore
                docstore_dict = {}
                id_mapping = chunks_data.get("id_mapping", {})
                
                for idx_str, chunk_id in id_mapping.items():
                    idx = int(idx_str)
                    if idx < len(chunks):
                        chunk = chunks[idx]
                        doc = Document(
                            page_content=chunk.get("content", ""),
                            metadata=chunk.get("metadata", {})
                        )
                        docstore_dict[chunk_id] = doc
                
                # Создаем docstore с документами
                docstore = InMemoryDocstore(docstore_dict)
                
                # Создаем векторное хранилище
                vectorstore = FAISS(self.embeddings, index, docstore, {})
                
                # Восстанавливаем маппинг index_to_docstore_id
                for idx_str, chunk_id in id_mapping.items():
                    idx = int(idx_str)
                    if idx < index.ntotal:
                        vectorstore.index_to_docstore_id[idx] = chunk_id
                
                doc_count = len(docstore_dict)
                logger.info(f"✓ Загружен новый формат FAISS индекса: {doc_count} документов")
                return vectorstore
                
            except Exception as e:
                logger.warning(f"Ошибка загрузки нового формата индекса: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        # 2. Пробуем загрузить старый формат (faiss_index/ + index_meta.pkl)
        if self.index_path.exists() and self.meta_path.exists():
            log_call_flow(f"Loading old format index: {self.index_path}")
            try:
                vectorstore = FAISS.load_local(
                    str(self.index_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                doc_count = len(vectorstore.index_to_docstore_id)
                logger.info(f"✓ Загружен старый формат FAISS индекса: {doc_count} документов")
                return vectorstore
            except Exception as e:
                logger.warning(f"Ошибка загрузки старого формата индекса: {e}")

        # 3. Индекс не найден
        logger.warning("FAISS индекс не найден. Создайте индекс через build_faiss_index.py")
        return None

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
            # Удаление только что добавленного фиктивного документа может вызвать ошибку,
            # если внутренний docstore уже был очищен (наблюдалось в тестах).
            # Ошибка не критична, поэтому игнорируем её.
            try:
                self.vectorstore.delete([first_doc_id])
            except Exception:
                pass

    @trace()
    def add_documents(self, texts: list[str], metadatas: Optional[list[dict]] = None):
        """
        Добавить документы в векторное хранилище

        Args:
            texts: Список текстов для добавления
            metadatas: Список метаданных для каждого текста
                      (source, page, chunk_id, etc.)
        """
        if not texts:
            log_call_flow("add_documents called with empty texts list")
            return

        log_call_flow(f"Adding {len(texts)} documents to vector store")
        self._ensure_index()

        documents = [
            Document(
                page_content=text,
                metadata=metadatas[i] if metadatas and i < len(metadatas) else {}
            )
            for i, text in enumerate(texts)
        ]

        self.vectorstore.add_documents(documents)
        self._save_index()
        log_call_flow(f"Successfully added {len(texts)} documents")

    def query(self, question: str, top_k: Optional[int] = None) -> Optional[str]:
        """Выполнить поиск и вернуть ответ (без метаданных, для совместимости)"""
        results = self.query_with_metadata(question, top_k)

        if not results:
            return None

        # Конкатенируем найденные фрагменты
        context = "\n\n".join([r.content for r in results])
        return context

    @trace()
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
        log_call_flow(f"RAG query: '{question[:50]}...' top_k={top_k or settings.top_k}")
        
        if self.vectorstore is None:
            log_call_flow("Vector store is None, returning empty results")
            return []

        k = top_k or settings.top_k
        results = self.vectorstore.similarity_search_with_score(question, k=k)

        chunk_results = [
            ChunkResult(
                content=doc.page_content,
                source=doc.metadata.get("source", "unknown"),
                page=doc.metadata.get("page", 0),
                chunk_id=doc.metadata.get("chunk_id", doc.metadata.get("chunk_index", "unknown")),
                score=score,
            )
            for doc, score in results
            if score >= score_threshold
        ]

        log_call_flow(f"RAG query returned {len(chunk_results)} results")
        return sorted(chunk_results, key=lambda x: x.score, reverse=True)

    def _save_index(self):
        """Сохранить индекс на диск"""
        self.index_path.mkdir(parents=True, exist_ok=True)
        self.vectorstore.save_local(str(self.index_path))

        meta = {"doc_count": len(self.vectorstore.index_to_docstore_id)}
        with open(self.meta_path, "wb") as f:
            pickle.dump(meta, f)

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
            shutil.rmtree(self.index_path, ignore_errors=True)
        if self.meta_path.exists():
            os.remove(self.meta_path)
