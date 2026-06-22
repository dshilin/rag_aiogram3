import hashlib
from pathlib import Path

from docx import Document as DocxDocument

import pytest

from src.rag.docx_parser import DocxParser, DocxChunk


def _make_docx(paragraphs: list[tuple], tmp_path: Path) -> Path:
    """Create a .docx for testing. Each tuple: (text, style) where style is 'h1'..'h4' or None for body."""
    doc = DocxDocument()
    for text, style in paragraphs:
        if style and style.startswith("h"):
            doc.add_heading(text, level=int(style[1]))
        else:
            doc.add_paragraph(text)
    path = tmp_path / "test.docx"
    doc.save(str(path))
    return path


@pytest.fixture
def parser():
    return DocxParser()


class TestHierarchy:
    def test_h1_detected_as_book_title(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст АН", "h1"),
            ("Текст абзаца.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert len(chunks) == 1
        assert chunks[0].metadata["book_title"] == "Базовый текст АН"

    def test_h2_h3_h4_nesting(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст", "h1"),
            ("КНИГА ПЕРВАЯ. Шаги", "h2"),
            ("Шаг Первый", "h3"),
            ("Бессилие и неуправляемость", "h4"),
            ("Текст про бессилие.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert len(chunks) == 1
        m = chunks[0].metadata
        assert m["book_title"] == "Базовый текст"
        assert m["part"] == "КНИГА ПЕРВАЯ. Шаги"
        assert m["chapter"] == "Шаг Первый"
        assert m["section"] == "Бессилие и неуправляемость"

    def test_plain_text_heading_heuristic(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст", "h1"),
            ("Шаг Первый", None),
            ("Текст абзаца.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert len(chunks) == 1
        assert chunks[0].metadata["chapter"] == "Шаг Первый"


class TestStepDefinition:
    def test_first_paragraph_in_quotes_is_definition(self, parser, tmp_path):
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Текст главы.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert chunks[0].metadata["chunk_role"] == "definition"
        assert chunks[1].metadata["chunk_role"] == "body"

    def test_definition_ref_id_propagated(self, parser, tmp_path):
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Текст главы.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        def_chunk = [c for c in chunks if c.metadata["chunk_role"] == "definition"][0]
        body_chunk = [c for c in chunks if c.metadata["chunk_role"] == "body"][0]
        assert body_chunk.metadata["definition_ref_id"] == def_chunk.chunk_id

    def test_citation_label_format(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст АН", "h1"),
            ("Шаг Первый", "h3"),
            ("Бессилие и неуправляемость", "h4"),
            ("Текст раздела.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert chunks[0].metadata["citation_label"] == (
            "«Базовый текст АН», Глава «Шаг Первый», Раздел «Бессилие и неуправляемость»"
        )


class TestChunking:
    def test_short_paragraphs_merged(self, parser, tmp_path):
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали, что бессильны.»", None),
            ("Короткий текст.", None),
            ("Еще короткий.", None),
            ("Третий короткий.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        body_chunks = [c for c in chunks if c.metadata["chunk_role"] == "body"]
        assert len(body_chunks) < 3  # merged

    def test_long_paragraph_split(self, parser, tmp_path):
        long_text = "Предложение. " * 2000
        path = _make_docx([
            ("Шаг Первый", "h3"),
            ("«Мы признали.»", None),
            (long_text, None),
        ], tmp_path)
        chunks = parser.parse(path)
        body_chunks = [c for c in chunks if c.metadata["chunk_role"] == "body"]
        assert len(body_chunks) > 1  # split

    def test_na_concepts_detected(self, parser, tmp_path):
        path = _make_docx([
            ("Базовый текст АН", "h1"),
            ("Капитуляция смирение выздоровление.", None),
        ], tmp_path)
        chunks = parser.parse(path)
        assert "капитуляция" in chunks[0].metadata["na_concepts"]
        assert "смирение" in chunks[0].metadata["na_concepts"]
        assert "выздоровление" in chunks[0].metadata["na_concepts"]
