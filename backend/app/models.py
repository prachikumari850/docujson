from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ConversionStatus = Literal[
    "queued",
    "processing",
    "completed",
    "failed",
]


class BilingualText(BaseModel):
    en: str | None = None
    hi: str | None = None


class MathEvidence(BaseModel):
    original_text: str
    reconstructed_text: str | None = None
    normalized_text: str | None = None
    latex: str | None = None
    mathml: str | None = None
    source_page: int | None = None
    source_bbox: list[float] | None = None
    component_bboxes: list[list[float]] = Field(default_factory=list)
    extraction_method: str | None = None
    confidence: float | None = None
    review_required: bool = True
    review_reasons: list[str] = Field(default_factory=list)
    vision_candidate: str | None = None


class MediaAsset(BaseModel):
    asset_id: str
    filename: str
    type: str
    source_page: int | None = None
    bbox: list[float] | None = None
    pixel_width: int | None = None
    pixel_height: int | None = None
    extraction_method: str | None = None
    confidence: float | None = None
    review_reasons: list[str] = Field(default_factory=list)
    content: str | None = None


class Option(BaseModel):
    id: str
    text: str
    original_text: str | None = None
    media: list[MediaAsset] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    confidence: dict[str, float | None] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=list)
    math_evidence: list[MathEvidence] = Field(default_factory=list)
    vision_verification: dict[str, Any] | None = None


class Question(BaseModel):
    question_id: str
    question_number: str | int | None = None
    question_type: str = "subjective"
    question: BilingualText
    original_text: str | None = None
    reconstructed_text: BilingualText | None = None
    options: list[Option] = Field(default_factory=list)
    correct_answer: str | None = None
    marks: float | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    media: list[MediaAsset] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    extraction_confidence: float | None = None
    confidence: dict[str, float | None] = Field(default_factory=dict)
    math_evidence: list[MathEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def answer_references_known_option(self):
        option_ids = {option.id for option in self.options}
        if self.correct_answer and option_ids and self.correct_answer not in option_ids:
            self.review_required = True
            self.review_reasons.append("Correct answer does not match a recovered option label.")
        return self


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
    answer_key_provided: bool = False
    answer_key_extracted: int = 0
    answer_key_matched: int = 0
    vision_verification: dict[str, Any] = Field(default_factory=dict)


class DocumentResult(BaseModel):
    document: DocumentInfo
    sections: list[Section]
    extraction_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_question_ids(self):
        ids = [question.question_id for section in self.sections for question in section.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique across the document.")
        return self


class ConversionResponse(BaseModel):
    conversion_id: str
    status: ConversionStatus
    progress: int = 0
    stage: str = ""
    error: str | None = None
    result: DocumentResult | None = None
