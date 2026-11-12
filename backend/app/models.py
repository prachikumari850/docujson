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
    atom_ids: list[str] = Field(default_factory=list)
    math_unit_ids: list[str] = Field(default_factory=list)
    source_crop_filename: str | None = None
    source_crop_path: str | None = None
    confidence: float | None = None
    review_required: bool = True
    review_reasons: list[str] = Field(default_factory=list)
    vision_candidate: str | None = None


class MediaAsset(BaseModel):
    asset_id: str
    filename: str
    type: str
    representation: Literal["raster", "svg_wrapper", "svg_vector"] = "raster"
    svg_filename: str | None = None
    original_filename: str | None = None
    relative_path: str | None = None
    svg_relative_path: str | None = None
    mime_type: str | None = None
    svg_mime_type: str | None = None
    media_format: Literal["svg_vector", "raster_original", "svg_raster_wrapper"] | None = None
    svg_generation_status: Literal["not_attempted", "source_reconstructed", "raster_wrapper", "fallback_unreliable"] | None = None
    svg_genuine_vector: bool = False
    svg_vector_metadata: dict[str, Any] | None = None
    svg_fallback_reason: str | None = None
    source_content_type: str | None = None
    source_page: int | None = None
    bbox: list[float] | None = None
    pixel_width: int | None = None
    pixel_height: int | None = None
    extraction_method: str | None = None
    confidence: float | None = None
    review_reasons: list[str] = Field(default_factory=list)
    content: str | None = None

    @model_validator(mode="after")
    def representation_has_asset(self):
        if self.representation == "svg_wrapper" and not self.svg_filename:
            raise ValueError("SVG wrapper representation needs svg_filename")
        if self.representation == "svg_vector" and (not self.svg_filename or not self.svg_genuine_vector):
            raise ValueError("Genuine SVG vector representation requires an SVG file and vector metadata flag")
        if self.representation == "svg_vector" and self.media_format not in (None, "svg_vector"):
            raise ValueError("A genuine SVG vector asset must use the svg_vector media format")
        if self.media_format == "svg_raster_wrapper" and self.svg_genuine_vector:
            raise ValueError("A raster wrapper cannot be identified as genuine vector artwork")
        return self


class Option(BaseModel):
    id: str
    stable_id: str | None = None
    text: str
    original_text: str | None = None
    bilingual_text: BilingualText = Field(default_factory=BilingualText)
    media: list[MediaAsset] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    confidence: dict[str, float | None] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=list)
    math_evidence: list[MathEvidence] = Field(default_factory=list)
    vision_verification: dict[str, Any] | None = None


class Question(BaseModel):
    question_id: str
    stable_id: str | None = None
    section: str | None = None
    ordered_segments: list[dict[str, Any]] = Field(default_factory=list)
    question_number: str | int | None = None
    question_type: str = "subjective"
    classification_status: Literal["confirmed_mcq", "unresolved", "excluded_non_mcq"] = "unresolved"
    classification_reasons: list[str] = Field(default_factory=list)
    classification_evidence: list[str] = Field(default_factory=list)
    question: BilingualText
    original_text: str | None = None
    reconstructed_text: BilingualText | None = None
    options: list[Option] = Field(default_factory=list)
    correct_answer: str | None = None
    answer_provenance: Literal["source_marked", "answer_key_matched", "answer_key_uncertain", "unavailable"] = "unavailable"
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
    document_id: str | None = None
    source_sha256: str | None = None
    schema_version: str = "2.1"
    extraction_date: str | None = None
    total_questions: int
    total_pages: int | None = None
    source_filename: str
    source_format: str
    language: list[str] = Field(default_factory=list)
    answer_key_provided: bool = False
    answer_key_extracted: int = 0
    answer_key_matched: int = 0
    question_classification: dict[str, int] = Field(default_factory=dict)
    math_extraction: dict[str, Any] = Field(default_factory=dict)
    vision_verification: dict[str, Any] = Field(default_factory=dict)
    extraction_summary: dict[str, Any] = Field(default_factory=dict)


class DocumentResult(BaseModel):
    document: DocumentInfo
    sections: list[Section]
    extraction_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_question_ids(self):
        ids = [question.question_id for section in self.sections for question in section.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique across the document.")
        stable_ids = [question.stable_id for section in self.sections for question in section.questions if question.stable_id]
        if len(stable_ids) != len(set(stable_ids)):
            raise ValueError("Stable question IDs must be unique across the document.")
        stable_option_ids: list[str] = []
        for section in self.sections:
            for question in section.questions:
                option_ids = [option.id for option in question.options]
                if len(option_ids) != len(set(option_ids)):
                    raise ValueError(f"Option IDs must be unique within question {question.question_id}.")
                stable_option_ids.extend(option.stable_id for option in question.options if option.stable_id)
        if len(stable_option_ids) != len(set(stable_option_ids)):
            raise ValueError("Stable option IDs must be unique across the document.")
        return self


class ConversionResponse(BaseModel):
    conversion_id: str
    status: ConversionStatus
    progress: int = 0
    stage: str = ""
    error: str | None = None
    result: DocumentResult | None = None
