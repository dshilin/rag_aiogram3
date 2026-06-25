from collections import Counter

_RUSSIAN_STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "из", "им", "от", "о", "для", "или", "еще", "до", "это", "об",
    "ни", "их", "чем", "при", "был", "когда", "кто", "меня", "нет", "вот",
    "теперь", "если", "уже", "будет", "даже", "потом", "чтобы", "себя", "них",
    "него", "нее", "там", "тому", "ли", "ну", "всё", "все", "очень",
    "разве", "ведь", "опять", "другой", "пока", "над", "под", "без",
}

# ponytail: natasha model loads ~100MB, ~5s cold start.
# Replace with lightweight keyword extraction if index rebuild speed matters.
def _extract_keywords(text: str, top_n: int = 5) -> list[str]:
    from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, Segmenter

    emb = NewsEmbedding()
    pipeline = {
        "segmenter": Segmenter(),
        "morph_tagger": NewsMorphTagger(emb),
        "morph_vocab": MorphVocab(),
    }

    doc = Doc(text.lower())
    doc.segment(pipeline["segmenter"])
    doc.tag_morph(pipeline["morph_tagger"])

    lemmas = []
    for token in doc.tokens:
        if token.pos not in ("NOUN", "PROPN"):
            continue
        token.lemmatize(pipeline["morph_vocab"])
        lemma = token.lemma
        if len(lemma) <= 2 or lemma in _RUSSIAN_STOPWORDS or lemma.isdigit():
            continue
        lemmas.append(lemma)

    top = Counter(lemmas).most_common(top_n)
    return [w for w, _ in top]
