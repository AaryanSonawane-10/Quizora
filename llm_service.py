
"""Question generation using Google's official Gemini SDK."""

import json
import re
from typing import List, Tuple

from google import genai
from pydantic import ValidationError

from errors import AppError
from schemas import MCQ


SYSTEM_PROMPT = """You write accurate multiple-choice questions for studying.

Rules:
- Use the evidence below as the only factual basis.
- Write exactly {n} distinct questions. If the evidence supports fewer,
  write fewer rather than inventing facts.
- Each question must be self-contained.
- Cover different parts of the evidence.
- Mix recall, understanding and application questions.
- Each question has exactly four plausible, distinct options.
- Exactly one answer must be correct.
- "correct_answer" must repeat one option exactly.
- "explanation" must explain why the answer is correct.

Reply with JSON only, without commentary or code fences, in this shape:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "..."}}]}}
"""


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)

    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    starts = [
        i for i in (text.find("{"), text.find("["))
        if i != -1
    ]

    if not starts:
        raise ValueError("No JSON found in the model reply.")

    data, _ = json.JSONDecoder().raw_decode(text[min(starts):])
    return data


def parse_questions(raw_text: str) -> Tuple[List[MCQ], List[str]]:
    """Return valid unique questions and validation errors."""

    data = _extract_json(raw_text)
    items = data.get("questions") if isinstance(data, dict) else data

    if not isinstance(items, list):
        raise ValueError("The reply has no list of questions.")

    valid: List[MCQ] = []
    errors: List[str] = []
    seen = set()

    for item in items:
        try:
            mcq = MCQ.model_validate(item)
        except ValidationError as exc:
            errors.append(str(exc))
            continue

        key = re.sub(
            r"\W+", " ", mcq.question.casefold()
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        valid.append(mcq)

    return valid, errors


def generate_mcqs(
    evidence: str,
    num_questions: int,
    api_key: str,
    model_name: str
) -> List[MCQ]:

    try:
        client = genai.Client(api_key=api_key)

    except Exception as exc:
        raise AppError(
            "generation_failed",
            "Could not initialize the Gemini client. Check the API configuration.",
            500,
        ) from exc

    # AI Studio may provide model names with a "models/" prefix.
    model = model_name.removeprefix("models/").strip()

    prompt = (
        SYSTEM_PROMPT.format(n=num_questions)
        + "\n\nRetrieved evidence:\n\n"
        + evidence
    )

    for attempt in range(2):
        if attempt == 1:
            prompt += (
                "\n\nYour previous reply could not be used. "
                "Try again and return only the required JSON object."
            )

        interaction = client.interactions.create(
            model=model,
            input=prompt,
            generation_config={
                "max_output_tokens": 4096,
                "thinking_level": "low",
            },
            store=False,
        )

        reply = interaction.output_text or ""

        try:
            valid, _errors = parse_questions(reply)
        except (ValueError, json.JSONDecodeError):
            valid = []

        if valid:
            return valid[:num_questions]

    raise AppError(
        "bad_model_output",
        "The model's reply didn't match the question format. "
        "Try again, or reduce the number of questions.",
        502,
    )


def classify_error(exc: Exception, model_name: str) -> AppError:
    """Convert Gemini errors into useful application messages."""

    if isinstance(exc, AppError):
        return exc

    text = str(exc)
    low = text.lower()

    if (
        "429" in text
        or "quota" in low
        or "resource_exhausted" in low
        or "rate limit" in low
    ):
        return AppError(
            "rate_limited",
            "The Gemini quota or rate limit was reached. Wait a minute and try again.",
            429,
        )

    if (
        "api key" in low
        or "api_key" in low
        or "unauthorized" in low
        or "permission" in low
        or "401" in text
        or "403" in text
    ):
        return AppError(
            "auth_failed",
            "Gemini rejected the API key. Check GOOGLE_API_KEY in Render.",
            401,
        )

    if "404" in text or "not found" in low:
        return AppError(
            "model_not_found",
            f"The model '{model_name}' isn't available for this key. "
            "Check GEMINI_MODEL in Render.",
            400,
        )

    if (
        "timeout" in low
        or "timed out" in low
        or "connect" in low
        or "unavailable" in low
    ):
        return AppError(
            "network",
            "Couldn't reach Gemini. Please try again.",
            503,
        )

    return AppError(
        "generation_failed",
        "Something went wrong while generating questions. Check the server logs.",
        500,
    )
