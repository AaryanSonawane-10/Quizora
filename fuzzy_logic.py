"""Explainable fuzzy assessment of a generated MCQ.

Changes from the first version:
- Difficulty now uses a real rule base over three inputs (question length, reasoning cues,
  option similarity) and is defuzzified to a 0-100 score. Before, option similarity was
  documented as an input but never used, and a tie between zero memberships silently
  returned "Easy".
- Quality also checks that the *correct answer* is supported by the evidence, and matching
  ignores plural/suffix differences and filler words such as "which" and "following".
"""
import re
from typing import Dict, List

_STOP = {
    "which", "following", "what", "that", "this", "with", "from", "their", "there", "about",
    "according", "these", "those", "would", "should", "could", "into", "does", "have", "been",
    "were", "when", "where", "also", "than", "then", "best", "most", "following", "statement",
    "true", "false", "correct", "describes", "described", "primary", "main",
}

_COMPLEXITY_TERMS = {
    "compare", "analyze", "analyse", "evaluate", "infer", "relationship", "consequence",
    "differentiate", "calculate", "justify", "interpret", "mechanism", "application",
    "scenario", "why", "how", "implication", "contrast", "predict", "explain",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _triangular(x: float, a: float, b: float, c: float) -> float:
    """Triangular fuzzy membership function."""
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if x < b:
        return (x - a) / (b - a) if b != a else 1.0
    return (c - x) / (c - b) if c != b else 1.0


def _trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    if x < a or x > d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if a <= x < b:
        return (x - a) / (b - a) if b != a else 1.0
    return (d - x) / (d - c) if d != c else 1.0


def _words(text: str) -> set:
    return set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9-]*\b", text.lower()))


def _stems(words) -> set:
    """Crude stemming (first 6 letters) so 'enzymes' matches 'enzyme'."""
    return {w[:6] for w in words if len(w) > 3 and w not in _STOP}


def _low(x: float) -> float:
    return _trapezoid(x, 0.0, 0.0, 0.2, 0.45)


def _mid(x: float) -> float:
    return _triangular(x, 0.25, 0.5, 0.75)


def _high(x: float) -> float:
    return _trapezoid(x, 0.55, 0.8, 1.0, 1.0)


def assess_mcq(question: str, options: List[str], correct_answer: str, evidence: str) -> Dict:
    """
    Rules (min = AND, max = OR), with inputs length (L), reasoning cues (C), option similarity (S):
      Easy   : (L low AND C low)  OR  (C low AND S low)
      Medium : C mid  OR  (L mid AND C low)  OR  (L high AND C low)  OR  (S high AND C low)
      Hard   : (C high AND L not low)  OR  (C mid AND L high)  OR  (C mid AND S high)  OR  0.7*C high
    Difficulty is the centroid of the Easy/Medium/Hard memberships (20 / 50 / 80).
    """
    q_words = _words(question)
    evidence_stems = _stems(_words(evidence))

    q_stems = _stems(q_words)
    coverage = _clamp(len(q_stems & evidence_stems) / max(1, len(q_stems)))

    answer_stems = _stems(_words(correct_answer))
    answer_support = _clamp(len(answer_stems & evidence_stems) / len(answer_stems)) if answer_stems else 0.5

    # --- inputs for difficulty ---
    length_signal = _clamp(len(question.split()) / 28.0)
    concept_signal = _clamp(len(q_words & _COMPLEXITY_TERMS) / 3.0)

    option_words = [_words(x) for x in options]
    overlaps = []
    for i in range(len(option_words)):
        for j in range(i + 1, len(option_words)):
            union = option_words[i] | option_words[j]
            if union:
                overlaps.append(len(option_words[i] & option_words[j]) / len(union))
    option_similarity = sum(overlaps) / max(1, len(overlaps))
    similarity_signal = _clamp(option_similarity / 0.4)
    diversity = _clamp(1.0 - option_similarity)

    L_low, L_mid, L_high = _low(length_signal), _mid(length_signal), _high(length_signal)
    C_low, C_mid, C_high = _low(concept_signal), _mid(concept_signal), _high(concept_signal)
    S_low, S_high = _low(similarity_signal), _high(similarity_signal)

    easy_mu = max(min(L_low, C_low), min(C_low, S_low))
    medium_mu = max(C_mid, min(L_mid, C_low), min(L_high, C_low), min(S_high, C_low))
    hard_mu = max(
        min(C_high, max(L_mid, L_high)),
        min(C_mid, L_high),
        min(C_mid, S_high),
        0.7 * C_high,
    )

    memberships = {"Easy": easy_mu, "Medium": medium_mu, "Hard": hard_mu}
    total_mu = easy_mu + medium_mu + hard_mu
    difficulty_score = (
        round((20 * easy_mu + 50 * medium_mu + 80 * hard_mu) / total_mu) if total_mu > 0 else 50
    )
    difficulty = "Easy" if difficulty_score < 37 else "Hard" if difficulty_score >= 63 else "Medium"

    # --- quality ---
    answer_valid = float(correct_answer in options)
    option_lengths = [len(x.split()) for x in options]
    length_balance = 1.0 - _clamp(
        (max(option_lengths) - min(option_lengths)) / max(1, max(option_lengths))
    )

    quality_raw = (
        0.40 * coverage
        + 0.20 * answer_support
        + 0.20 * diversity
        + 0.10 * length_balance
        + 0.10 * answer_valid
    )
    quality_score = round(100 * _clamp(quality_raw))

    flags = []
    if coverage < 0.20:
        flags.append("The question uses few terms found in the evidence")
    if answer_support < 0.25 and answer_stems:
        flags.append("The correct answer isn't clearly supported by the evidence")
    if diversity < 0.35:
        flags.append("Options may be too similar")
    if not answer_valid:
        flags.append("Correct answer is not one of the options")
    if length_balance < 0.35:
        flags.append("Option lengths are very uneven, which can hint at the answer")
    if quality_score < 55:
        flags.append("Low overall quality score")

    return {
        "difficulty": difficulty,
        "difficulty_score": difficulty_score,
        "difficulty_memberships": {k: round(float(v), 3) for k, v in memberships.items()},
        "quality_score": quality_score,
        "evidence_coverage": round(100 * coverage),
        "answer_support": round(100 * answer_support),
        "flags": flags,
        "method_note": "Explainable fuzzy heuristics; not a factuality guarantee.",
    }
