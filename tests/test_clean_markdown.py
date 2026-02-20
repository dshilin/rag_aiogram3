import sys
from pathlib import Path

# Ensure project root on path
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
