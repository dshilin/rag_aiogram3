from typing import Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document

from src.core.config import settings


class RAGService:
    """Сервис для работы с RAG (Retrieval-Augmented Generation)"""

    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        
        self.vectorstore = Chroma(
            persist_directory=settings.chroma_db_path,
            embedding_function=self.embeddings,
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
        )

    def add_documents(self, texts: list[str]):
        """Добавить документы в векторное хранилище"""
        documents = []
        for text in texts:
            chunks = self.text_splitter.split_text(text)
            for chunk in chunks:
                documents.append(Document(page_content=chunk))
        
        if documents:
            self.vectorstore.add_documents(documents)

    def query(self, question: str, top_k: Optional[int] = None) -> Optional[str]:
        """Выполнить поиск и вернуть ответ"""
        if top_k is None:
            top_k = settings.top_k
        
        results = self.vectorstore.similarity_search(question, k=top_k)
        
        if not results:
            return None
        
        # Конкатенируем найденные фрагменты
        context = "\n\n".join([doc.page_content for doc in results])
        return context

    def get_document_count(self) -> int:
        """Получить количество документов в хранилище"""
        try:
            return self.vectorstore._collection.count()
        except Exception:
            return 0

    def clear(self):
        """Очистить векторное хранилище"""
        self.vectorstore.delete_collection()
