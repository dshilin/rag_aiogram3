"""Tests for MarkdownChunker"""

import pytest

from src.rag.md_chunker import MarkdownChunker


class TestHeadingDetection:
    def test_detect_h1_as_chapter(self):
        chunker = MarkdownChunker()
        result = chunker._detect_heading("# Шаг Первый")
        assert result == ("chapter", "Шаг Первый")

    def test_detect_h2_as_section(self):
        chunker = MarkdownChunker()
        result = chunker._detect_heading("## Бессилие")
        assert result == ("section", "Бессилие")

    def test_plain_text_not_heading(self):
        chunker = MarkdownChunker()
        assert chunker._detect_heading("Обычный текст") is None

    def test_classify_step_by_number(self):
        chunker = MarkdownChunker()
        assert chunker._classify_heading("Шаг 1") == ("step", 1)

    def test_classify_step_by_name(self):
        chunker = MarkdownChunker()
        assert chunker._classify_heading("Шаг Первый") == ("step", None)

    def test_classify_tradition(self):
        chunker = MarkdownChunker()
        assert chunker._classify_heading("Традиция 12") == ("tradition", 12)

    def test_classify_main_text(self):
        chunker = MarkdownChunker()
        assert chunker._classify_heading("Введение") == ("main_text", None)


class TestDefinitionDetection:
    def test_definition_in_quotes(self):
        chunker = MarkdownChunker()
        assert chunker._is_definition("«Мы признали, что бессильны.»")

    def test_plain_text_not_definition(self):
        chunker = MarkdownChunker()
        assert not chunker._is_definition("Обычный текст.")

    def test_no_end_quote_not_definition(self):
        chunker = MarkdownChunker()
        assert not chunker._is_definition("«Мы признали, что бессильны.")


class TestNAConcepts:
    def test_detect_matching_concepts(self):
        chunker = MarkdownChunker()
        result = chunker._detect_na_concepts(
            "Капитуляция и смирение — это принципы выздоровления."
        )
        assert "капитуляция" in result
        assert "смирение" in result
        assert "принципы" in result

    def test_no_concepts_in_plain_text(self):
        chunker = MarkdownChunker()
        assert chunker._detect_na_concepts("Обычный текст.") == []


class TestSplitIntoParagraphs:
    def test_simple_paragraphs(self):
        chunker = MarkdownChunker()
        text = "Первый параграф.\n\nВторой параграф."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 2

    def test_heading_not_removed(self):
        chunker = MarkdownChunker()
        text = "# Шаг Первый\n\nТекст шага."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 2
        assert result[0] == "# Шаг Первый"

    def test_empty_text(self):
        chunker = MarkdownChunker()
        assert chunker.split_into_paragraphs("") == []

    def test_whitespace_only_returns_empty(self):
        chunker = MarkdownChunker()
        assert chunker.split_into_paragraphs("   \n\n  ") == []


class TestEstimateTokens:
    def test_simple_text(self):
        assert MarkdownChunker._estimate_tokens("один два три") == 3


class TestChunkMd:
    def test_simple_document(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "«Мы признали, что бессильны.»\n\n"
            "Капитуляция — это ключ к выздоровлению.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) >= 2
        assert chunks[0].chunk_role == "definition"
        assert chunks[1].chunk_role == "body"

    def test_hierarchy_propagated(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "## Бессилие\n\n"
            "Текст раздела.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        assert chunks[0].chapter == "Шаг Первый"
        assert chunks[0].section == "Бессилие"
        assert chunks[0].element_type == "step"

    def test_definition_ref_id_propagated(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n"
            "«Мы признали.»\n\n"
            "Текст главы.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        def_chunk = [c for c in chunks if c.chunk_role == "definition"][0]
        body_chunk = [c for c in chunks if c.chunk_role == "body"][0]
        assert body_chunk.definition_ref_id == def_chunk.chunk_id

    def test_short_body_chunks_merged(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг\n\n"
            "«Мы признали.»\n\n"
            "Короткий текст.\n\n"
            "Еще короткий.\n\n"
            "Третий короткий.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        body_chunks = [c for c in chunks if c.chunk_role == "body"]
        assert len(body_chunks) < 3

    def test_long_body_chunk_split(self, tmp_path):
        long_text = "Предложение. " * 2000
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг\n\n" "«Мы признали.»\n\n" + long_text,
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        body_chunks = [c for c in chunks if c.chunk_role == "body"]
        assert len(body_chunks) > 1

    def test_na_concepts_detected_in_chunk(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг\n\n" "Капитуляция смирение выздоровление.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        assert "капитуляция" in chunks[0].na_concepts
        assert "смирение" in chunks[0].na_concepts

    def test_to_dict_includes_all_metadata(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Шаг Первый\n\nТекст.", encoding="utf-8")
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        d = chunks[0].to_dict()
        assert "chunk_id" in d["metadata"]
        assert "book_title" in d["metadata"]
        assert "chapter" in d["metadata"]
        assert "element_type" in d["metadata"]
        assert "chunk_role" in d["metadata"]
        assert "na_concepts" in d["metadata"]


class TestSaveChunks:
    def test_save_and_load(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Шаг Первый\n\n" "«Мы признали.»\n\n" "Текст.",
            encoding="utf-8",
        )
        out_dir = tmp_path / "chunks"
        chunker = MarkdownChunker()
        chunks, stats = chunker.chunk_md(md_file)
        chunker.save_chunks(chunks, out_dir)

        assert (out_dir / "index.json").exists()
        assert (out_dir / "chunk_0000.json").exists()

        import json

        idx = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
        assert idx["total_chunks"] == len(chunks)
        assert idx["source"] == "test"

        chunk0 = json.loads(
            (out_dir / "chunk_0000.json").read_text(encoding="utf-8")
        )
        assert chunk0["metadata"]["source"] == "test"
        assert chunk0["metadata"]["chunk_role"] == "definition"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
