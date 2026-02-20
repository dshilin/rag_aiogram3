import os
import pickle
from pathlib import Path
from typing import Optional

import faiss
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain_community.vectorstores import FAISS

from src.core.config import settings


class RAGService:
    """Сервис для работы с RAG (Retrieval-Augmented Generation)"""

    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        
        self.index_path = Path(settings.chroma_db_path) / "faiss_index"
        self.meta_path = Path(settings.chroma_db_path) / "index_meta.pkl"
        
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
        if self.vectorstore is None:
            self.vectorstore = FAISS.from_texts(
                [""],
                self.embeddings,
            )
            # Удаляем тестовый документ
            self.vectorstore.delete([0])

    def add_documents(self, texts: list[str]):
        """Добавить документы в векторное хранилище"""
        self._ensure_index()
        
        documents = []
        for text in texts:
            chunks = self.text_splitter.split_text(text)
            for chunk in chunks:
                documents.append(Document(page_content=chunk))
        
        if documents:
            self.vectorstore.add_documents(documents)
            self._save_index()

    def query(self, question: str, top_k: Optional[int] = None) -> Optional[str]:
        """Выполнить поиск и вернуть ответ"""
        if self.vectorstore is None:
            return None
        
        if top_k is None:
            top_k = settings.top_k
        
        results = self.vectorstore.similarity_search(question, k=top_k)
        
        if not results:
            return None
        
        # Конкатенируем найденные фрагменты
        context = "\n\n".join([doc.page_content for doc in results])
        return context

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
            os.remove(self.index_path)
        if self.meta_path.exists():
            os.remove(self.meta_path)
