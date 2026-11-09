from typing import Any, Literal

from pydantic import BaseModel, Field


ConversionStatus = Literal[
    "queued",
    "processing",
    "completed",
    "failed",
]


class BilingualText(BaseModel):
    en: str | None = None
    hi: str | None = None


class Option(BaseModel):
    id: str
    text: str


class MediaAsset(BaseModel):
    asset_id: str
    filename: str
    type: str
    source_page: int | None = None
    content: str | None = None


class Question(BaseModel):
    question_id: str
    question_number: str | int | None = None
    question_type: str = "subjective"
    question: BilingualText
    options: list[Option] = Field(default_factory=list)
    correct_answer: str | None = None
    marks: float | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    media: list[MediaAsset] = Field(default_factory=list)
    review_required: bool = False


class Section(BaseModel):
    section_name: str
    questions: list[Question] = Field(default_factory=list)


class DocumentInfo(BaseModel):
    title: str
    total_questions: int
    total_pages: int | None = None
    source_filename: str
    source_format: str
    language: list[str] = Field(default_factory=list)


class DocumentResult(BaseModel):
    document: DocumentInfo
    sections: list[Section]


class ConversionResponse(BaseModel):
    conversion_id: str
    status: ConversionStatus
    progress: int = 0
    stage: str = ""
    error: str | None = None
    result: DocumentResult | None = None