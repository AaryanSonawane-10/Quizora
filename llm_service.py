"""Question generation with Gemini.

The first version parsed the raw reply with MCQSet.model_validate_json, which fails whenever
the model wraps its JSON in a ```json fence (common). This version extracts the JSON, keeps
every valid question even if one is malformed, drops duplicates, and retries once.
"""
import json
import re
from typing import List, Tuple

from pydantic import ValidationError

from errors import AppError
from schemas import MCQ

SYSTEM_PROMPT = """You write accurate multiple-choice questions for studying.

Rules:
- Use the evidence below as the only factual basis. Passages are labelled [NOTES] or [WEB].
  Notes are the primary source; web passages may fill gaps but must not be presented as the student's notes.
- Write exactly {n} distinct questions. If the evidence supports fewer, write fewer rather than inventing facts.
- Each question must be self-contained: never say "according to the text", "the passage" or "the notes".
- Cover different parts of the evidence. Mix recall, understanding and application questions.
- Each question has exactly four plausible, distinct options and exactly one correct answer.
  Wrong options should be believable mistakes, not jokes, and options should be similar in length.
- "correct_answer" must repeat one option exactly.
- "explanation" is one or two sentences saying why the answer is right, using the evidence.

Reply with JSON only, no commentary and no code fence, in this shape:
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
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("No JSON found in the model reply.")
    data, _ = json.JSONDecoder().raw_decode(text[min(starts):])
    return data


def parse_questions(raw_text: str) -> Tuple[List[MCQ], List[str]]:
    """Return (valid unique questions, validation error messages)."""
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
        key = re.sub(r"\W+", " ", mcq.question.casefold()).strip()
        if key in seen:
            continue
        seen.add(key)
        valid.append(mcq)
    return valid, errors


def _content_to_text(content) -> str:
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


def generate_mcqs(evidence: str, num_questions: int, api_key: str, model_name: str) -> List[MCQ]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        raise AppError(
            "missing_dependency",
            "The Gemini packages aren't installed. Run: pip install -r requirements.txt",
            500,
        )

    llm = ChatGoogleGenerativeAI(
        model=model_name, google_api_key=api_key, temperature=0.3, max_retries=2
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(n=num_questions)),
        HumanMessage(content="Retrieved evidence:\n\n" + evidence),
    ]

    for attempt in range(2):
        reply = _content_to_text(llm.invoke(messages).content)
        try:
            valid, _errors = parse_questions(reply)
        except (ValueError, json.JSONDecodeError):
            valid = []
        if valid:
            return valid[:num_questions]
        messages = messages + [
            HumanMessage(
                content="Your last reply could not be used. Reply again with only the JSON object described above."
            )
        ]
    raise AppError(
        "bad_model_output",
        "The model's reply didn't match the question format. Try again, or reduce the number of questions.",
        502,
    )


def classify_error(exc: Exception, model_name: str) -> AppError:
    """Turn provider exceptions into messages that say what to do next."""
    if isinstance(exc, AppError):
        return exc
    text = str(exc)
    low = text.lower()
    if "429" in text or "quota" in low or "resource_exhausted" in low or "rate limit" in low:
        return AppError("rate_limited", "The Gemini quota or rate limit was reached. Wait a minute and try again.", 429)
    if "api key" in low or "api_key" in low or "unauthorized" in low or "permission" in low or "401" in text or "403" in text:
        return AppError("auth_failed", "Gemini rejected the API key. Check GOOGLE_API_KEY in your .env file.", 401)
    if "404" in text or "not found" in low:
        return AppError(
            "model_not_found",
            f"The model “{model_name}” isn't available for this key. Set GEMINI_MODEL in .env to a model your account can use.",
            400,
        )
    if "timeout" in low or "timed out" in low or "connect" in low or "unavailable" in low:
        return AppError("network", "Couldn't reach Gemini. Check your internet connection and try again.", 503)
    return AppError("generation_failed", "Something went wrong while generating questions. Try again.", 500)
