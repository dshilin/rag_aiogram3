import json
import re
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


@dataclass
class ChunkResult:
    """Результат поиска с метаданными"""
    content: str
    source: str
    page: int
    chunk_id: str
    score: float = 0.0
    metadata: dict = None

    @property
    def citation_label(self) -> str:
        meta_label = (self.metadata or {}).get("citation_label")
        if not meta_label or meta_label == "TBD":
            return self.source
        cleaned = re.sub(r'\s*#+\s*', ' ', meta_label).strip()
        # ponytail: strip trailing chunk text after `> «` — that's the body, not the heading
        idx = cleaned.find("> «")
        if idx != -1:
            cleaned = cleaned[:idx].rstrip(" ,>»")
        if self.source.lower() in cleaned.lower():
            return cleaned
        return f"{self.source}, {cleaned}" if cleaned else self.source

    def to_dict(self) -> dict:
        """Конвертировать в словарь"""
        return {
            "content": self.content,
            "source": self.source,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "metadata": self.metadata,
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
            logger.warning("FAISS индекс не найден. Будет создан при добавлении документов")
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
        self.vectorstore = FAISS(self.embeddings, index, docstore, {})

    @trace
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

        batch_size = 50
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size] if metadatas else None
            documents = [
                Document(
                    page_content=text,
                    metadata=batch_metas[j] if batch_metas and j < len(batch_metas) else {}
                )
                for j, text in enumerate(batch_texts)
            ]
            logger.info(f"⏳ Эмбеддинг батч {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1} ({len(batch_texts)} чанков)...")
            self.vectorstore.add_documents(documents)
            logger.info(f"✅ Батч {i//batch_size + 1} готов")
        self._save_index()
        logger.info(f"✅ Закончен эмбеддинг всех {len(texts)} чанков")
        log_call_flow(f"Successfully added {len(texts)} documents")

    def query(self, question: str, top_k: Optional[int] = None) -> Optional[str]:
        """Выполнить поиск и вернуть ответ (без метаданных, для совместимости)"""
        results = self.query_with_metadata(question, top_k)

        if not results:
            return None

        # Конкатенируем найденные фрагменты
        context = "\n\n".join([r.content for r in results])
        return context

    @trace
    def query_with_metadata(
        self,
        question: str,
        top_k: Optional[int] = None,
        score_threshold: float = 2.0,
        metadata_filter: Optional[dict] = None,
        expand_definitions: bool = True,
    ) -> list[ChunkResult]:
        log_call_flow(f"RAG query: '{question[:50]}...' top_k={top_k or settings.top_k}")

        if self.vectorstore is None:
            log_call_flow("Vector store is None, returning empty results")
            return []

        k = top_k or settings.top_k
        results = self.vectorstore.similarity_search_with_score(question, k=k * 2)

        chunk_results = []
        for doc, score in results:
            meta = doc.metadata or {}
            if metadata_filter:
                if not all(meta.get(k) == v for k, v in metadata_filter.items()):
                    continue
            if score > score_threshold:
                continue
            chunk_results.append(
                ChunkResult(
                    content=doc.page_content,
                    source=meta.get("source", meta.get("book_title", "unknown")),
                    page=meta.get("page", 0),
                    chunk_id=meta.get("chunk_id", "unknown"),
                    score=score,
                    metadata=meta,
                )
            )

        # score — это L2-расстояние из IndexFlatL2: меньше = релевантнее,
        # поэтому сортируем по возрастанию
        chunk_results.sort(key=lambda x: x.score)

        # ponytail: fixed 0.15 boost + Jaccard-like overlap. Switch to weighted BM25-style reranking if precision at top-1 matters.
        from src.rag.docx_parser import _extract_keywords
        query_keywords = set(_extract_keywords(question))
        if query_keywords:
            KEYWORD_BOOST = 0.15
            for r in chunk_results:
                chunk_kw = set((r.metadata or {}).get("keywords", []))
                overlap = query_keywords & chunk_kw
                if overlap:
                    overlap_score = len(overlap) / max(len(query_keywords), len(chunk_kw))
                    # буст уменьшает расстояние — чанк с пересечением ключевых слов поднимается выше
                    r.score -= KEYWORD_BOOST * overlap_score
            chunk_results.sort(key=lambda x: x.score)

        # expand definitions before dedup
        if expand_definitions and self.vectorstore:
            for r in chunk_results:
                def_ref_id = (r.metadata or {}).get("definition_ref_id")
                if def_ref_id:
                    for doc_id in self.vectorstore.index_to_docstore_id.values():
                        doc = self.vectorstore.docstore.search(doc_id)
                        if doc and doc.metadata.get("chunk_id") == def_ref_id:
                            def_content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
                            r.content = f"[Определение]\n{def_content}\n\n{r.content}"
                            break

        # ponytail: page metadata never populated, so (source, page) dedup collapses everything.
        # Dedup by chunk_id instead.
        seen = set()
        deduped = []
        for r in chunk_results:
            if expand_definitions and (r.metadata or {}).get("chunk_role") == "definition":
                continue
            if r.chunk_id not in seen:
                seen.add(r.chunk_id)
                deduped.append(r)

        log_call_flow(f"RAG query returned {len(deduped)} results (deduped from {len(chunk_results)})")
        return deduped[:k]

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
