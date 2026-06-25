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
        result = chunker._detect_na_concepts("Капитуляция и смирение — это принципы выздоровления.")
        assert "капитуляция" in result
        assert "смирение" in result
        assert "принципы" in result

    def test_no_concepts_in_plain_text(self):
        chunker = MarkdownChunker()
        assert chunker._detect_na_concepts("Обычный текст.") == []


class TestSplitIntoParagraphs:
    def test_short_text_returns_empty(self):
        chunker = MarkdownChunker(min_paragraph_length=10)
        result = chunker.split_into_paragraphs("short")
        assert result == []

    def test_entire_block_as_one_paragraph(self):
        chunker = MarkdownChunker(min_paragraph_length=10)
        text = "First sentence. Second sentence. Third sentence."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 1
        assert result[0] == "First sentence. Second sentence. Third sentence."

    def test_empty_text_returns_empty(self):
        chunker = MarkdownChunker()
        assert chunker.split_into_paragraphs("") == []

    def test_whitespace_only_returns_empty(self):
        chunker = MarkdownChunker()
        assert chunker.split_into_paragraphs("   \n\n  ") == []

    def test_multiple_blocks_become_multiple_paragraphs(self):
        chunker = MarkdownChunker(min_paragraph_length=10)
        text = "First paragraph here.\n\nSecond paragraph here too."
        result = chunker.split_into_paragraphs(text)
        assert len(result) == 2
        assert result[0] == "First paragraph here."
        assert result[1] == "Second paragraph here too."


class TestCrossPageMerge:
    def test_cross_page_paragraph_merged(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "This paragraph starts on page 1 and continues\n"
            "<!-- Page 2 -->\n"
            "onto page 2 right here.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(cross_page_merge=True, merge_short_paragraphs=False)
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 1
        assert "starts on page 1" in chunks[0].content
        assert "onto page 2" in chunks[0].content
        assert chunks[0].page == 1
        assert stats.cross_page_paragraphs == 1

    def test_cross_page_merge_disabled(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "This paragraph starts on page 1\n"
            "<!-- Page 2 -->\n"
            "This paragraph is on page 2.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(cross_page_merge=False, merge_short_paragraphs=False)
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 2
        assert stats.cross_page_paragraphs == 0

    def test_cross_page_paragraph_ends_with_period(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "This paragraph ends properly on page 1.\n"
            "<!-- Page 2 -->\n"
            "New paragraph on page 2.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(cross_page_merge=True, merge_short_paragraphs=False)
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 2
        assert chunks[0].page == 1
        assert chunks[1].page == 2
        assert stats.cross_page_paragraphs == 0

    def test_cross_page_paragraph_flush_at_end(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "Paragraph that does not end with punctuation",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(cross_page_merge=True, merge_short_paragraphs=False)
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 1
        assert "Paragraph that does not end with punctuation" in chunks[0].content
        assert chunks[0].page == 1


class TestMergeShortParagraphs:
    def test_short_paragraph_merged(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "This is a long first paragraph that goes on and on.\n"
            "\n"
            "Short para.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(
            merge_short_paragraphs=True, merge_threshold=50, cross_page_merge=False
        )
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 1
        assert "long first paragraph" in chunks[0].content
        assert "Short para" in chunks[0].content

    def test_merge_short_paragraphs_disabled(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "This is a long first paragraph that goes on and on.\n"
            "\n"
            "Short para.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(
            merge_short_paragraphs=False, merge_threshold=50, cross_page_merge=False
        )
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 2
        assert "long first paragraph" in chunks[0].content
        assert "Short para" in chunks[1].content

    def test_long_paragraph_not_merged(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "First paragraph content here.\n"
            "\n"
            "Second paragraph is long enough not to be merged.\n"
            "Far longer than the threshold indeed.",
            encoding="utf-8",
        )
        chunker = MarkdownChunker(
            merge_short_paragraphs=True, merge_threshold=50, cross_page_merge=False
        )
        chunks, stats = chunker.chunk_md(md_file)
        assert len(chunks) == 2


class TestSaveChunks:
    def test_save_chunks_with_metadata(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "<!-- Page 1 -->\n"
            "This is the first paragraph.\n"
            "\n"
            "<!-- Page 2 -->\n"
            "This paragraph continues\n"
            "<!-- Page 3 -->\n"
            "to page 3 here.\n"
            "\n"
            "Short.",
            encoding="utf-8",
        )
        out_dir = tmp_path / "chunks"
        chunker = MarkdownChunker(
            cross_page_merge=True,
            merge_short_paragraphs=True,
            merge_threshold=50,
        )
        chunks, stats = chunker.chunk_md(md_file)
        chunker.save_chunks(chunks, out_dir)

        assert (out_dir / "index.json").exists()
        assert (out_dir / "chunk_0000.json").exists()

        import json
        idx = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
        assert idx["total_chunks"] == len(chunks)
        assert idx["source"] == "test"

        chunk0 = json.loads((out_dir / "chunk_0000.json").read_text(encoding="utf-8"))
        assert chunk0["metadata"]["source"] == "test"
        assert chunk0["metadata"]["page"] == 1
        assert stats.cross_page_paragraphs == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
