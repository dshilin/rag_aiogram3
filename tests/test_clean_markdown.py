import sys
from pathlib import Path

# Добавляем корень проекта в path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.clean_markdown import clean_markdown_content


def test_glue_one_word_line_with_previous():
    """Если строка состоит из одного слова, она должна склеиться с предыдущей строкой."""
    src = """
Это начало предложения
Нести
весть
Дальше текст.
"""
    out = clean_markdown_content(src)
    # ожидаем, что 'Нести' и 'весть' объединятся в 'Нести весть'
    assert "Нести весть" in out
    assert "Это начало предложения" in out


def test_removes_converted_document_header():
    src = "# Конвертированный документ\n\nNormal text"
    out = clean_markdown_content(src)
    assert "# Конвертированный документ" not in out
    assert "Normal text" in out


def test_removes_page_number_line():
    src = "## Страница 5\n\nNormal text"
    out = clean_markdown_content(src)
    assert "Страница 5" not in out
    assert "Normal text" in out


def test_removes_empty_page_marker():
    src = "*[Страница пуста или содержит только изображения]*\n\nNormal text"
    out = clean_markdown_content(src)
    assert "Страница пуста" not in out
    assert "Normal text" in out


def test_removes_copyright_line():
    src = "© 2024 Some Company\n\nNormal text"
    out = clean_markdown_content(src)
    assert "©" not in out
    assert "Normal text" in out


def test_removes_colophon_after_separator():
    src = "Normal text\n\n***\n\nColophon text here"
    out = clean_markdown_content(src)
    assert "Normal text" in out
    assert "Colophon text here" not in out


def test_removes_colophon_after_dash_separator():
    src = "Normal text\n\n---\n\nColophon text"
    out = clean_markdown_content(src)
    assert "Normal text" in out
    assert "Colophon text" not in out


def test_leaves_normal_text_unchanged():
    src = "## Заголовок\n\nОбычный параграф текста.\n\n- список"
    out = clean_markdown_content(src)
    assert "## Заголовок" in out
    assert "Обычный параграф текста." in out


def test_preserves_page_markers():
    src = "text\n<!-- Page 5 -->\ntext"
    out = clean_markdown_content(src)
    assert "<!-- Page 5 -->" in out


def test_do_not_glue_on_toc_line():
    """Не склеивать заголовок с предыдущей строкой, если предыдущая — оглавление (много точек + номер)."""
    src = """
Нести весть ...................................................................194

<!-- Page 6 -->

Нести
весть
Они вместе употребляли и вместе обрели чистоту.
"""
    out = clean_markdown_content(src)
    # В этом случае 'Нести' и 'весть' должны образовать заголовок, но не быть присоединены к TOC-строке.
    assert "Нести весть ...................................................................194" in out
    # И заголовок должен остаться отдельной строкой (после маркера страницы)
    assert "<!-- Page 6 -->" in out
    assert "Нести весть" in out
