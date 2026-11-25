import random
import time
from typing import Any, Dict

from demo_mode import generate_demo_mcqs
from errors import AppError
from fuzzy_logic import assess_mcq
from llm_service import classify_error, generate_mcqs
from rag_engine import build_note_chunks, corrective_retrieve

MAX_INPUT_CHARS = 50_000
MIN_NOTES_CHARS = 80
DEFAULT_QUERY = (
    "Create exam-style multiple-choice questions covering the main concepts, definitions, "
    "relationships, and examples in these notes."
)


def generate_quiz(
    notes: str,
    *,
    num_questions: int = 5,
    allow_web: bool = True,
    max_web_results: int = 3,
    topic: str = "",
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    demo: bool = False,
) -> Dict[str, Any]:
    started = time.time()

    truncated = len(notes) > MAX_INPUT_CHARS
    notes = notes[:MAX_INPUT_CHARS]
    if len(notes.strip()) < MIN_NOTES_CHARS:
        raise AppError("too_short", "There isn't enough text to write good questions. Add more notes.", 422)

    chunks = build_note_chunks(notes)
    retrieval = corrective_retrieve(
        notes=notes,
        chunks=chunks,
        query=DEFAULT_QUERY,
        allow_web=allow_web,
        max_web_results=max_web_results,
        topic=topic,
        num_questions=num_questions,
    )
    evidence = retrieval["evidence"]
    if not evidence.strip():
        raise AppError("no_evidence", "No usable passages were found. Try longer or clearer notes.", 422)

    if demo:
        mcqs = generate_demo_mcqs(evidence, num_questions)
    else:
        if not api_key:
            raise AppError(
                "missing_api_key",
                "Add GOOGLE_API_KEY to your .env file, then restart the server.",
                400,
            )
        try:
            mcqs = generate_mcqs(evidence, num_questions, api_key, model_name)
        except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
            raise classify_error(exc, model_name)

    if not mcqs:
        raise AppError(
            "no_questions",
            "No questions could be written from this text. Try longer notes or a different topic.",
            422,
        )

    questions = []
    for i, mcq in enumerate(mcqs, start=1):
        q = mcq.model_dump()
        # Models tend to put the right answer in the same slot; shuffle so position gives nothing away.
        random.shuffle(q["options"])
        q["id"] = i
        q["fuzzy"] = assess_mcq(
            question=q["question"],
            options=q["options"],
            correct_answer=q["correct_answer"],
            evidence=evidence,
        )
        questions.append(q)

    return {
        "questions": questions,
        "meta": {
            "note_chunks": len(chunks),
            "passages_used": retrieval["passages_used"],
            "used_web": retrieval["used_web"],
            "attempts": retrieval["attempts"],
            "sources": retrieval["sources"],
            "retrieval_note": retrieval["message"],
            "notes_chars": len(notes),
            "truncated": truncated,
            "max_input_chars": MAX_INPUT_CHARS,
            "topic": topic,
            "demo": demo,
            "seconds": round(time.time() - started, 1),
        },
    }
