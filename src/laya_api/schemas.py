from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

JsonValue = str | int | float | bool | None | list[Any] | dict[str, Any]
QuestionType = Literal["choice", "score", "noul"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: QuestionType
    instructions: str | dict[str, Any] | list[Any]
    criteria: dict[str, Any] | list[Any] | None = None

    @model_validator(mode="after")
    def check_criteria(self) -> Question:
        if self.type == "choice":
            if not isinstance(self.criteria, dict) or not self.criteria:
                raise ValueError("choice questions require criteria as a non-empty object of options")
            if len(self.criteria) > 255:
                raise ValueError("choice questions accept at most 255 options")
        elif self.type == "score":
            if not isinstance(self.criteria, list) or len(self.criteria) < 2:
                raise ValueError("score questions require criteria as an array of at least 2 levels")
            if len(self.criteria) > 10:
                raise ValueError("score questions accept at most 10 levels")
        elif self.type == "noul" and self.criteria is not None and not isinstance(self.criteria, dict):
            raise ValueError("noul criteria must be an object with optional true/false descriptions")
        return self


class SystemOneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str | dict[str, Any] | list[Any]
    questions: dict[str, Question]
    model: str = "laya-latest"

    @model_validator(mode="after")
    def check_questions(self) -> SystemOneRequest:
        if not self.questions:
            raise ValueError("questions must contain at least one question")
        if len(self.questions) > 256:
            raise ValueError("a request may contain at most 256 questions")
        return self


class NoulAnswer(BaseModel):
    type: Literal["noul"] = "noul"
    noul: float


class ChoiceAnswer(BaseModel):
    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float


class ScoreAnswer(BaseModel):
    type: Literal["score"] = "score"
    score: float
    legend: dict[str, str]
    probabilities: dict[str, float]
    confidence: float


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int = 0


class Routing(BaseModel):
    model: str
    repo: str | None = None
    reason: str | None = None
    workflow: str | None = None
    detection: dict[str, Any] | None = None


class SystemOneResponse(BaseModel):
    model: str
    answers: dict[str, Answer]
    usage: Usage
    routing: Routing | None = None


class ModelListItem(BaseModel):
    name: str
    description: str
    release_date: str


class ModelListResponse(BaseModel):
    models: list[ModelListItem]


class ErrorBody(BaseModel):
    error: str
    message: str


class ConsoleKeyCreate(BaseModel):
    name: str = Field(default="default", max_length=80)
