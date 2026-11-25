"""Offline fill-in-the-blank generator.

Used only when DEMO_MODE=1. It lets you try the interface without an API key. These
questions are built with simple text rules, not by an AI model, and are much weaker than
Gemini's. The UI labels this mode clearly.
"""
import random
import re
from collections import Counter
from typing import List

from schemas import MCQ

_STOP = {
    "which", "their", "there", "these", "those", "about", "would", "should", "could", "because",
    "between", "through", "during", "before", "after", "other", "where", "while", "being",
    "using", "within", "without", "another", "however", "therefore", "although",
}


def _sentences(evidence: str) -> List[str]:
    lines = [ln for ln in evidence.splitlines() if ln.strip() and not ln.startswith("[")]
    text = " ".join(lines)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if 8 <= len(p.split()) <= 32]


def generate_demo_mcqs(evidence: str, num_questions: int) -> List[MCQ]:
    sentences = _sentences(evidence)
    freq = Counter(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{5,}", evidence))
    pool = [w for w, c in freq.items() if w not in _STOP]
    rng = random.Random(7)

    questions: List[MCQ] = []
    used_terms = set()
    for sentence in sentences:
        if len(questions) >= num_questions:
            break
        candidates = [
            w for w in re.findall(r"[A-Za-z][A-Za-z-]{5,}", sentence)
            if w.lower() not in _STOP and w.lower() not in used_terms
        ]
        if not candidates:
            continue
        # Prefer specific words (rare in the notes) that are long.
        target = sorted(candidates, key=lambda w: (freq[w.lower()], -len(w)))[0]
        distractors = [
            w for w in pool
            if w != target.lower() and w not in sentence.lower() and abs(len(w) - len(target)) <= 4
        ]
        rng.shuffle(distractors)
        distractors = distractors[:3]
        if len(distractors) < 3:
            continue
        if target[0].isupper():
            distractors = [d.capitalize() for d in distractors]
        blanked = re.sub(rf"\b{re.escape(target)}\b", "_____", sentence, count=1)
        try:
            questions.append(
                MCQ(
                    question=f"Which word completes this statement from the notes? {blanked}",
                    options=[target, *distractors],
                    correct_answer=target,
                    explanation=sentence,
                )
            )
        except ValueError:
            continue
        used_terms.add(target.lower())
    return questions
