import re
from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator

_LETTER_INDEX = {"a": 0, "b": 1, "c": 2, "d": 3}
_LETTER_PREFIX = re.compile(r"^\(?([A-Da-d])[\).:]\s+")


class MCQ(BaseModel):
    question: str = Field(min_length=8)
    options: List[str] = Field(min_length=4, max_length=4)
    correct_answer: str = Field(min_length=1)
    explanation: str = ""

    @field_validator("question", "correct_answer")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("explanation", mode="before")
    @classmethod
    def clean_explanation(cls, value) -> str:
        # Models sometimes return null for optional text.
        return "" if value is None else str(value).strip()

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: List[str]) -> List[str]:
        cleaned = [x.strip() for x in value]
        if any(not x for x in cleaned):
            raise ValueError("Options must not be empty.")
        # Models sometimes label options "A. ...", "B. ..." themselves.
        if all(_LETTER_PREFIX.match(x) for x in cleaned):
            cleaned = [_LETTER_PREFIX.sub("", x, count=1).strip() for x in cleaned]
        if len({x.casefold() for x in cleaned}) != 4:
            raise ValueError("Each MCQ must have four distinct options.")
        return cleaned

    @model_validator(mode="after")
    def correct_answer_must_be_option(self):
        """Accept small formatting differences, but always end up with an exact option."""
        if self.correct_answer in self.options:
            return self

        folded = {o.casefold().strip(): o for o in self.options}
        key = self.correct_answer.casefold().strip()
        if key in folded:
            self.correct_answer = folded[key]
            return self

        # "B" / "(b)" / "b)" -> second option
        letter_only = re.fullmatch(r"\(?([a-d])[\).:]?", key)
        if letter_only:
            self.correct_answer = self.options[_LETTER_INDEX[letter_only.group(1)]]
            return self

        # "B. Some option text"
        stripped = _LETTER_PREFIX.sub("", self.correct_answer, count=1).strip().casefold()
        if stripped in folded:
            self.correct_answer = folded[stripped]
            return self

        raise ValueError("correct_answer must match one option.")


class MCQSet(BaseModel):
    questions: List[MCQ] = Field(min_length=1, max_length=10)
