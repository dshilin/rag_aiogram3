"""
Тесты для системы чанков
"""

import pytest
from pathlib import Path
import json
import tempfile
import shutil

from scripts.chunk_documents import (
    chunk_markdown_document,
    extract_page_markers,
    ChunkMetadata,
    Chunk,
)


class TestPageMarkers:
    """Тесты для извлечения маркеров страниц"""

    def test_extract_comment_marker(self):
        """Извлечение маркера из комментария"""
        content = "<!-- Page 5 -->"
        markers = extract_page_markers(content)
        assert len(markers) == 1
        assert markers[0][0] == 5  # page number

    def test_extract_header_marker(self):
        """Извлечение маркера из заголовка"""
        content = "## [Страница 12](#doc-page-12)"
        markers = extract_page_markers(content)
        assert len(markers) == 1
        assert markers[0][0] == 12

    def test_extract_multiple_markers(self):
        """Извлечение нескольких маркеров"""
        content = """<!-- Page 1 -->
Текст страницы 1

<!-- Page 2 -->
Текст страницы 2

<!-- Page 3 -->
Текст страницы 3
"""
        markers = extract_page_markers(content)
        assert len(markers) == 3
        assert [m[0] for m in markers] == [1, 2, 3]

    def test_no_markers(self):
        """Документ без маркеров страниц"""
        content = "Просто текст без маркеров"
        markers = extract_page_markers(content)
        assert len(markers) == 0


class TestChunkMetadata:
    """Тесты для метаданных чанка"""

    def test_metadata_creation(self):
        """Создание метаданных"""
        meta = ChunkMetadata(
            chunk_id="abc123",
            source="test_doc",
            page=5,
            chunk_index=2,
            start_char=100,
            end_char=600,
            total_chunks=10,
        )
        assert meta.chunk_id == "abc123"
        assert meta.source == "test_doc"
        assert meta.page == 5

    def test_metadata_to_dict(self):
        """Конвертация в словарь"""
        meta = ChunkMetadata(
            chunk_id="abc123",
            source="test_doc",
            page=5,
            chunk_index=2,
            start_char=100,
            end_char=600,
            total_chunks=10,
        )
        d = meta.to_dict()
        assert d["chunk_id"] == "abc123"
        assert d["source"] == "test_doc"
        assert d["page"] == 5

    def test_metadata_json(self):
        """Конвертация в JSON"""
        meta = ChunkMetadata(
            chunk_id="abc123",
            source="test_doc",
            page=5,
            chunk_index=2,
            start_char=100,
            end_char=600,
            total_chunks=10,
        )
        json_str = meta.to_json()
        parsed = json.loads(json_str)
        assert parsed["chunk_id"] == "abc123"


class TestChunkDocument:
    """Тесты для разделения документа на чанки"""

    def test_chunk_simple_text(self):
        """Разделение простого текста"""
        content = "A" * 1000
        chunks = chunk_markdown_document(content, "test.md", chunk_size=500, overlap=50)
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_with_pages(self):
        """Разделение документа со страницами"""
        content = """<!-- Page 1 -->
""" + "A" * 600 + """

<!-- Page 2 -->
""" + "B" * 600

        chunks = chunk_markdown_document(content, "test.md", chunk_size=500, overlap=50)
        assert len(chunks) > 0

        # Проверяем что есть чанки с разными страницами
        pages = set(c.metadata.page for c in chunks)
        assert 1 in pages
        assert 2 in pages

    def test_chunk_metadata(self):
        """Проверка метаданных чанков"""
        content = "<!-- Page 5 -->\n" + "A" * 600
        chunks = chunk_markdown_document(content, "test_doc.md", chunk_size=500, overlap=50)

        assert len(chunks) > 0
        chunk = chunks[0]

        assert "test_doc" in chunk.metadata.source
        assert chunk.metadata.page == 5
        assert chunk.metadata.chunk_index == 0
        assert len(chunk.content) > 0

    def test_chunk_overlap(self):
        """Проверка перекрытия чанков"""
        content = "A" * 1000
        chunk_size = 500
        overlap = 100

        chunks = chunk_markdown_document(
            content, "test.md", chunk_size=chunk_size, overlap=overlap
        )

        if len(chunks) > 1:
            # Проверяем что чанки перекрываются
            for i in range(1, len(chunks)):
                prev_end = chunks[i - 1].metadata.end_char
                curr_start = chunks[i].metadata.start_char
                # Перекрытие должно быть >= 0
                assert prev_end >= curr_start - overlap


class TestChunkSaving:
    """Тесты для сохранения чанков"""

    @pytest.fixture
    def temp_dir(self):
        """Создать временную директорию"""
        dirpath = tempfile.mkdtemp()
        yield Path(dirpath)
        shutil.rmtree(dirpath)

    def test_chunk_to_dict(self):
        """Конвертация чанка в словарь"""
        chunk = Chunk(
            content="Test content",
            metadata=ChunkMetadata(
                chunk_id="test123",
                source="test.md",
                page=1,
                chunk_index=0,
                start_char=0,
                end_char=12,
                total_chunks=1,
            ),
        )
        d = chunk.to_dict()
        assert d["content"] == "Test content"
        assert d["metadata"]["chunk_id"] == "test123"

    def test_chunk_to_json(self):
        """Конвертация чанка в JSON"""
        chunk = Chunk(
            content="Test content",
            metadata=ChunkMetadata(
                chunk_id="test123",
                source="test.md",
                page=1,
                chunk_index=0,
                start_char=0,
                end_char=12,
                total_chunks=1,
            ),
        )
        json_str = chunk.to_json()
        parsed = json.loads(json_str)
        assert parsed["content"] == "Test content"
        assert parsed["metadata"]["source"] == "test.md"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
