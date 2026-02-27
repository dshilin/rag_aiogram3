"""
Пример использования системы чанков с метаданными

Этот скрипт демонстрирует:
1. Загрузку чанков из директории
2. Поиск с метаданными
3. Форматирование ответа
"""

import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.rag import RAGService, search_and_format


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def example_basic_search():
    """Пример базового поиска"""
    print("\n" + "=" * 60)
    print("Пример 1: Базовый поиск с метаданными")
    print("=" * 60)

    rag = RAGService()

    # Проверяем количество документов
    count = rag.get_document_count()
    print(f"\nДокументов в хранилище: {count}")

    if count == 0:
        print("⚠️  Хранилище пустое. Сначала загрузите чанки:")
        print("   python -m src.rag.chunk_loader --chunks-dir data/documents/chunks")
        return

    # Поиск с метаданными
    query = "что такое Анонимные наркоманы?"
    print(f"\n🔍 Запрос: {query}")

    results = rag.query_with_metadata(query, top_k=3)

    if not results:
        print("❌ Ничего не найдено")
        return

    print(f"\n✅ Найдено результатов: {len(results)}\n")

    for i, result in enumerate(results, 1):
        print(f"{'─' * 60}")
        print(f"Результат #{i}")
        print(f"  📄 Источник: {result.source}")
        print(f"  📑 Страница: {result.page}")
        print(f"  🏷️  Chunk ID: {result.chunk_id}")
        print(f"  📊 Score: {result.score:.4f}")
        print(f"  📝 Текст: {result.content[:150]}...")
        print()


def example_formatted_response():
    """Пример форматированного ответа"""
    print("\n" + "=" * 60)
    print("Пример 2: Форматированный ответ для пользователя")
    print("=" * 60)

    rag = RAGService()
    query = "на сколько эффективны Анонимные наркоманы в лечении зависимости?"

    print(f"\n🔍 Запрос: {query}\n")

    response = search_and_format(query, rag, top_k=3)
    print(response)


def example_custom_processing():
    """Пример кастомной обработки результатов"""
    print("\n" + "=" * 60)
    print("Пример 3: Кастомная обработка результатов")
    print("=" * 60)

    rag = RAGService()
    query = "что такое бессилие?"

    results = rag.query_with_metadata(query, top_k=5, score_threshold=0.3)

    if not results:
        print("Ничего не найдено")
        return

    # Группируем по источникам
    by_source = {}
    for result in results:
        source = result.source
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(result)

    print(f"\nНайдено в {len(by_source)} источниках:\n")

    for source, source_results in by_source.items():
        print(f"📁 {source}:")
        for result in source_results:
            pages = sorted(set(r.page for r in source_results))
            print(f"   - Страницы: {', '.join(map(str, pages))}")
            print(f"   - Лучший score: {max(r.score for r in source_results):.4f}")
        print()


def example_context_generation():
    """Пример генерации контекста для LLM"""
    print("\n" + "=" * 60)
    print("Пример 4: Генерация контекста для LLM")
    print("=" * 60)

    rag = RAGService()
    query = "кто такой спонсор?"

    results = rag.query_with_metadata(query, top_k=3)

    if not results:
        print("Ничего не найдено")
        return

    # Формируем контекст для LLM
    context_parts = []
    context_parts.append("Используй следующий контекст из документов для ответа:\n")

    for i, result in enumerate(results, 1):
        context_parts.append(f"[Источник {i}]")
        context_parts.append(f"Документ: {result.source}")
        context_parts.append(f"Страница: {result.page}")
        context_parts.append(f"Текст:\n{result.content}\n")

    context = "\n".join(context_parts)

    print("Контекст для отправки в LLM:\n")
    print(context)
    print("\n" + "=" * 60)
    print("Теперь можно отправить запрос в LLM с этим контекстом")


def main():
    setup_logging()

    print("\n" + "📚 CHUNKING SYSTEM EXAMPLES ".center(60, "="))
    print()

    # Пример 1: Базовый поиск
    example_basic_search()

    # Пример 2: Форматированный ответ
    example_formatted_response()

    # Пример 3: Кастомная обработка
    example_custom_processing()

    # Пример 4: Генерация контекста
    example_context_generation()

    print("\n" + "=" * 60)
    print("✅ Все примеры выполнены")
    print("=" * 60)


if __name__ == "__main__":
    main()
