import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import faiss
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


_embeddings_cache = {}


def _get_embeddings():
    model_name = settings.embedding_model
    if model_name not in _embeddings_cache:
        _embeddings_cache[model_name] = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings_cache[model_name]


class RAGService:
    """Сервис для работы с RAG (Retrieval-Augmented Generation)"""

    def __init__(self):
        self.embeddings = _get_embeddings()

        # Загружаем существующий индекс или создаем новый
        self.vectorstore = self._load_index()

    def _load_index(self):
        """
        Загрузить FAISS индекс (новый формат: faiss.index + chunks_metadata.json)

        Returns:
            FAISS векторное хранилище или None
        """
        index_path = Path(settings.embeddings_db_path) / "faiss.index"
        chunks_meta_path = Path(settings.embeddings_db_path) / "chunks_metadata.json"

        if not index_path.exists() or not chunks_meta_path.exists():
            logger.warning("FAISS индекс не найден. Создайте через chunk_loader")
            return None

        log_call_flow(f"Loading index: {index_path}")
        try:
            import json
            index = faiss.read_index(str(index_path))

            # Загружаем метаданные чанков
            chunks_data = json.loads(chunks_meta_path.read_text(encoding="utf-8"))
            chunks = chunks_data.get("chunks", [])
            id_mapping = chunks_data.get("id_mapping", {})

            # Создаем документы и docstore
            from langchain_core.documents import Document

            docstore_dict = {}
            for idx_str, chunk_id in id_mapping.items():
                idx = int(idx_str)
                if idx < len(chunks):
                    chunk = chunks[idx]
                    doc = Document(
                        page_content=chunk.get("content", ""),
                        metadata=chunk.get("metadata", {})
                    )
                    docstore_dict[chunk_id] = doc

            docstore = InMemoryDocstore(docstore_dict)
            vectorstore = FAISS(self.embeddings, index, docstore, {})

            # Восстанавливаем маппинг index_to_docstore_id
            for idx_str, chunk_id in id_mapping.items():
                idx = int(idx_str)
                if idx < index.ntotal:
                    vectorstore.index_to_docstore_id[idx] = chunk_id

            doc_count = len(docstore_dict)
            logger.info(f"✓ Загружен FAISS индекс: {doc_count} документов")
            return vectorstore

        except Exception as e:
            logger.error(f"Ошибка загрузки индекса: {e}")
            import traceback
            logger.debug(traceback.format_exc())
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

        chunk_results.sort(key=lambda x: x.score, reverse=True)

        # ponytail: dedup by (source, page), keep highest score
        seen = set()
        deduped = []
        for r in chunk_results:
            key = (r.source, r.page)
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        log_call_flow(f"RAG query returned {len(deduped)} results (deduped from {len(chunk_results)})")
        return deduped

    def _save_index(self):
        """Сохранить индекс на диск в новом формате (faiss.index + JSON метаданные)"""
        import json
        from datetime import datetime

        output_dir = Path(settings.embeddings_db_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Сохраняем FAISS индекс
        index = self.vectorstore.index
        index_path = output_dir / "faiss.index"
        faiss.write_index(index, str(index_path))

        # Собираем метаданные чанков из docstore
        chunks = []
        id_mapping = {}
        for idx, doc_id in self.vectorstore.index_to_docstore_id.items():
            doc = self.vectorstore.docstore.search(doc_id)
            if doc:
                doc = Document(page_content=doc, metadata={}) if isinstance(doc, str) else doc
                chunk = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                }
                chunks.append(chunk)
                id_mapping[str(idx)] = doc_id

        # Сохраняем метаданные чанков
        chunks_data = {"chunks": chunks, "id_mapping": id_mapping}
        chunks_path = output_dir / "chunks_metadata.json"
        chunks_path.write_text(
            json.dumps(chunks_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Сохраняем метаданные индекса
        metadata = {
            "model_name": settings.embedding_model,
            "embedding_dim": index.d,
            "total_chunks": len(chunks),
            "created_at": datetime.now().isoformat(),
        }
        meta_path = output_dir / "index_metadata.json"
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(f"✓ Сохранён новый формат индекса: {len(chunks)} документов")

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
        db_path = Path(settings.embeddings_db_path)
        for f in ["faiss.index", "chunks_metadata.json", "index_metadata.json"]:
            p = db_path / f
            if p.exists():
                p.unlink()
        old_dir = db_path / "faiss_index"
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)
        old_pkl = db_path / "index_meta.pkl"
        if old_pkl.exists():
            old_pkl.unlink()
