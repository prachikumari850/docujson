"""IR tests. Geometry comes from the real physics_qp.pdf (Q9 stem, page 4)."""
import pytest
from pydantic import ValidationError

from app.ir import (Answer, Atom, BBox, Content, DocumentMeta, ExtractedDocument, MathExpression,
                    MathNode, MediaAsset, Option, Question, Segment, SourceRef, atom_id,
                    question_id, semantic_digest, validate_document)

FP = "abc123def456"


def ref(page, x0, y0, x1, y1, col="right"):
    return SourceRef(page=page, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), column=col)


def build_q9() -> ExtractedDocument:
    # measured from the PDF: arrow glyph (Type3) 8 pt above the letter "A"
    arrow_ref, letter_ref = ref(4, 345, 518, 355, 528), ref(4, 345, 526, 364, 538)
    a_arrow = Atom(id=atom_id(FP, 4, arrow_ref.bbox, "→"), kind="symbol", source=arrow_ref,
                   text="→", type3=True, note="arrow above letter")
    a_letter = Atom(id=atom_id(FP, 4, letter_ref.bbox, "A"), kind="text", source=letter_ref, text="A")
    o1_ref, o2_ref = ref(4, 333, 588, 410, 622), ref(4, 444, 588, 520, 622)
    o1a = Atom(id="o1", kind="text", source=o1_ref, text="cos")
    o2a = Atom(id="o2", kind="text", source=o2_ref, text="cos")
    crop = MediaAsset(id="m1", kind="math_crop", source=ref(4, 340, 515, 400, 540),
                      raster_file="media/q9_stem_math.png")
    expr = MathExpression(
        id="x1", status="confirmed", raw_text="A→", source=ref(4, 345, 518, 364, 538),
        atom_ids=[a_arrow.id, a_letter.id], crop_asset_id=crop.id,
        tree=MathNode(op="vec", children=[MathNode(op="var", value="A", atom_ids=[a_letter.id])],
                      atom_ids=[a_arrow.id]),
        latex=r"\vec{A}")
    q = Question(
        id=question_id(FP, 9, "Section A"), number=9, section="Section A",
        regions=[ref(4, 305, 480, 560, 660)],
        stem=Content(en=[Segment(kind="text", text="If", lang="en"),
                         Segment(kind="math", ref_id="x1"),
                         Segment(kind="text", text="and the magnitude", lang="en")]),
        options=[Option(id="q9-o1", label="1", source=o1_ref, atom_ids=["o1"],
                        content=Content(en=[Segment(kind="text", text="cos⁻¹(3/5)", lang="en")])),
                 Option(id="q9-o2", label="2", source=o2_ref, atom_ids=["o2"],
                        content=Content(en=[Segment(kind="text", text="cos⁻¹(4/5)", lang="en")]))],
        answer=Answer(value="1", provenance="answer_key_matched"),
        atom_ids=[a_arrow.id, a_letter.id, "o1", "o2"])
    return ExtractedDocument(
        meta=DocumentMeta(title="t", source_filename="physics_qp.pdf", source_sha256=FP,
                          total_pages=16, languages=["en", "hi"], answer_key_provided=True),
        atoms={a.id: a for a in (a_arrow, a_letter, o1a, o2a)},
        math={"x1": expr}, media={"m1": crop}, questions=[q])


def codes(doc):
    return {i.code for i in validate_document(doc) if i.level == "error"}


def test_real_geometry_is_valid_and_ids_are_stable():
    doc = build_q9()
    assert codes(doc) == set()
    assert build_q9().questions[0].id == doc.questions[0].id == f"{FP}-sectiona-q009"
    assert semantic_digest(doc.questions[0], doc)["stem_en"] == r"If \vec{A} and the magnitude"


def test_atom_cannot_belong_to_two_questions():
    doc = build_q9()
    q2 = doc.questions[0].model_copy(deep=True)
    q2.id, q2.number = "other", 10
    q2.regions = [ref(5, 305, 100, 560, 200)]
    for o in q2.options:
        o.id = "other-" + o.id
    doc.questions.append(q2)
    assert "atom_in_two_questions" in codes(doc)


def test_option_overlap_is_caught():
    doc = build_q9()
    doc.questions[0].options[1].source = ref(4, 340, 590, 415, 620)
    assert "options_overlap" in codes(doc)


def test_option_atoms_must_belong_to_the_question():
    doc = build_q9()
    doc.questions[0].options[0].atom_ids = ["o2", "stranger"]
    assert "option_atom_outside_question" in codes(doc)


def test_answer_must_be_an_existing_option():
    doc = build_q9()
    doc.questions[0].answer = Answer(value="7", provenance="answer_key_matched")
    assert "answer_not_an_option" in codes(doc)


def test_answer_provenance_is_honest():
    with pytest.raises(ValidationError):
        Answer(value="2", provenance="unavailable")
    with pytest.raises(ValidationError):
        Answer(value=None, provenance="answer_key_matched")


def test_uncertain_math_needs_crop_and_cannot_carry_latex():
    with pytest.raises(ValidationError):
        MathExpression(id="u", status="uncertain", raw_text="?", source=ref(4, 0, 0, 1, 1))
    with pytest.raises(ValidationError):
        MathExpression(id="u", status="uncertain", raw_text="?", source=ref(4, 0, 0, 1, 1),
                       crop_asset_id="m1", latex=r"\frac{a}{b}")


def test_dangling_reference_and_svg_rules():
    doc = build_q9()
    doc.questions[0].stem.en.append(Segment(kind="media", ref_id="nope"))
    assert "dangling_reference" in codes(doc)
    with pytest.raises(ValidationError):   # unverified vector claim
        MediaAsset(id="s", kind="figure", source=ref(4, 0, 0, 1, 1),
                   representation="svg_vector", svg_file="a.svg", raster_file="a.png")
    MediaAsset(id="s", kind="figure", source=ref(4, 0, 0, 1, 1),
               representation="svg_wrapper", svg_file="a.svg", raster_file="a.png")


def test_mcq_needs_two_options():
    doc = build_q9()
    doc.questions[0].options = doc.questions[0].options[:1]
    assert "not_an_mcq" in codes(doc)