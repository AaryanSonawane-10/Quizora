"""Corrective retrieval over the user's notes.

Changes from the first version:
- Passages are chosen with maximal marginal relevance (MMR), so the evidence is spread
  across the whole document instead of being the six passages that happen to match one
  generic query best.
- An optional focus topic steers retrieval; when it finds nothing, the loop retries with
  a broader query before it considers the web.
- The web fallback is triggered by real weakness (too little usable note text, or a focus
  topic the notes don't cover) and searches with the topic or the notes' own key terms,
  not with the generic instruction sentence.
"""
import re
from typing import Any, Dict, List, Tuple

DEFAULT_CHUNK_SIZE = 900
DEFAULT_OVERLAP = 140
MIN_STRONG_CHARS = 400
MIN_FOCUS_SCORE = 0.02


def split_into_chunks(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    """Character chunking that keeps overlap between adjacent passages."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Prefer a sentence/word boundary near the end of a chunk.
        if end < len(text):
            boundary = max(
                text.rfind(". ", start + chunk_size // 2, end),
                text.rfind("; ", start + chunk_size // 2, end),
                text.rfind(" ", start + chunk_size // 2, end),
            )
            if boundary > start:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def build_note_chunks(notes: str) -> List[str]:
    return split_into_chunks(notes)


def _norm(values):
    import numpy as np

    values = np.asarray(values, dtype=float)
    span = values.max() - values.min()
    if span <= 0:
        return np.zeros_like(values)
    return (values - values.min()) / span


def _even_sample(chunks: List[str], k: int) -> List[int]:
    """Fallback when TF-IDF can't build a vocabulary: take evenly spaced passages."""
    if len(chunks) <= k:
        return list(range(len(chunks)))
    step = len(chunks) / k
    return sorted({int(i * step) for i in range(k)})


def _select_chunks(
    chunks: List[str], query: str, k: int, char_budget: int, focused: bool
) -> Tuple[List[Tuple[int, str, float]], float]:
    """Pick up to k passages balancing relevance, coverage of the whole document and low redundancy.

    Returns ([(original_index, text, relevance)], best_relevance), in document order.
    """
    if not chunks:
        return [], 0.0
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        matrix = vectorizer.fit_transform(chunks + [query])
        X, q = matrix[:-1], matrix[-1]
        relevance = cosine_similarity(X, q).ravel()
        centrality = cosine_similarity(X, np.asarray(X.mean(axis=0))).ravel()
        pairwise = cosine_similarity(X)
    except ValueError:
        idx = _even_sample(chunks, k)
        return [(i, chunks[i], 0.0) for i in idx], 0.0

    w_rel = 0.65 if focused else 0.15
    base = w_rel * _norm(relevance) + (1 - w_rel) * _norm(centrality)

    lam = 0.7
    selected: List[int] = []
    candidates = list(range(len(chunks)))
    total = 0
    while candidates and len(selected) < k:
        best, best_val = None, float("-inf")
        for i in candidates:
            redundancy = max((pairwise[i][j] for j in selected), default=0.0)
            value = lam * base[i] - (1 - lam) * redundancy
            if value > best_val:
                best, best_val = i, value
        candidates.remove(best)
        if selected and total + len(chunks[best]) > char_budget:
            continue
        selected.append(best)
        total += len(chunks[best])

    selected.sort()
    best_relevance = float(relevance.max()) if len(relevance) else 0.0
    return [(i, chunks[i], float(relevance[i])) for i in selected], best_relevance


def _rank_chunks(query: str, chunks: List[str], top_k: int = 5) -> List[tuple]:
    """Plain TF-IDF ranking. Kept for backwards compatibility with the old app.py."""
    if not chunks:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(chunks + [query])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(chunks[i], float(score)) for i, score in ranked[:top_k] if score > 0]
    except ValueError:
        return []


def _top_terms(chunks: List[str], n: int = 6) -> List[str]:
    """The notes' own most characteristic words, used to build a sensible web query."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words="english", max_features=800)
        matrix = vectorizer.fit_transform(chunks)
        weights = matrix.sum(axis=0).A1
        terms = vectorizer.get_feature_names_out()
        order = weights.argsort()[::-1][:n]
        return [str(terms[i]) for i in order]
    except ValueError:
        return []


def _search_web(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Optional DuckDuckGo fallback. Only attempted when the notes are weak."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []
    results = []
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                title = str(item.get("title", "")).strip()
                body = str(item.get("body", "")).strip()
                href = str(item.get("href", item.get("url", ""))).strip()
                if body:
                    results.append({"title": title, "body": body, "url": href})
    except Exception:
        return []
    return results


def corrective_retrieve(
    notes: str,
    chunks: List[str],
    query: str,
    allow_web: bool = True,
    max_web_results: int = 3,
    topic: str = "",
    num_questions: int = 5,
    char_budget: int = 14000,
) -> Dict[str, Any]:
    """
    Corrective retrieval loop:
    1) select passages spread across the notes (steered by `topic` when given);
    2) if a focus topic matched nothing, retry with a broader query;
    3) judge whether the evidence is strong enough;
    4) if not, and the web is allowed, add web snippets as clearly labelled supplements.
    """
    topic = (topic or "").strip()
    focused = bool(topic)
    k = min(len(chunks), max(6, num_questions * 2))

    attempts = 1
    selection, best_rel = _select_chunks(chunks, topic if focused else query, k, char_budget, focused)

    if focused and best_rel < MIN_FOCUS_SCORE:
        attempts += 1
        selection, _ = _select_chunks(chunks, f"{topic} {query}", k, char_budget, focused=False)

    note_chars = sum(len(text) for _, text, _ in selection)
    topic_missing = focused and best_rel < MIN_FOCUS_SCORE
    strong_enough = bool(selection) and note_chars >= MIN_STRONG_CHARS and not topic_missing

    total = len(chunks)
    note_evidence = "\n\n".join(
        f"[NOTES | passage {i + 1} of {total}]\n{text}" for i, text, _ in selection
    )
    sources = ["Uploaded notes"] if note_evidence else []

    web_evidence = ""
    used_web = False
    if allow_web and not strong_enough:
        web_query = topic or " ".join(_top_terms(chunks)) or " ".join(query.split()[:12])
        web_results = _search_web(f"{web_query} explanation", max_results=max_web_results)
        attempts += 1
        if web_results:
            used_web = True
            snippets = []
            for result in web_results:
                snippets.append(f"[WEB | {result['title']} | {result['url']}]\n{result['body']}")
                if result["url"]:
                    sources.append(result["url"])
            web_evidence = "\n\n".join(snippets)

    evidence = "\n\n".join(part for part in [note_evidence, web_evidence] if part).strip()
    if not evidence and notes.strip():
        evidence = "\n\n".join(f"[NOTES | fallback passage]\n{x}" for x in chunks[:4])
        if evidence:
            sources = ["Uploaded notes (fallback passages)"]

    if strong_enough:
        message = "Passages were chosen from across your notes."
    elif used_web:
        message = (
            f"Your notes don't cover “{topic}” well, so web results were added."
            if topic_missing
            else "Your notes had little usable text, so web results were added."
        )
    elif topic_missing:
        message = f"Your notes don't seem to cover “{topic}”. Questions use the closest passages; review them carefully."
    else:
        message = "Your notes are short. Questions use all the text available; review them carefully."

    return {
        "evidence": evidence,
        "used_web": used_web,
        "attempts": attempts,
        "sources": list(dict.fromkeys(sources)),
        "message": message,
        "passages_used": len(selection),
        "passages_total": total,
    }
