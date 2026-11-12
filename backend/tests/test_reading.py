"""Stage 3 reading order against the preserved SRG source (0-based page indexes).

Set DOCUJSON_PHYSICS_QP_PDF to override fixture discovery. Expected strings
were compared by eye with the printed paper."""
from collections import Counter

import pytest

from app.services.atoms import extract_page_atoms
from app.services.math_units import build_units
from app.services.reading import read_rows

@pytest.fixture(scope="module")
def doc(physics_qp_doc):
    return physics_qp_doc


def rows_of(doc, idx, column, y0, y1):
    atoms = extract_page_atoms(doc[idx], idx + 1, "fixture")
    return [r.plain() for r in read_rows(atoms, build_units(atoms)) if r.column == column and y0 <= r.baseline <= y1]


def test_q9_english_stem_keeps_inline_vectors_in_sentence_order(doc):
    rows = rows_of(doc, 3, "right", 530, 600)
    assert rows[1:] == [
        r"If $\vec{A}=\vec{B}+\vec{C}$ and the magnitude of $\vec{A},\vec{B}$ and",
        r"$\vec{C}$ are 5,4 and 3 units respectively, the angle",
        r"between $\vec{A}$ and $\vec{C}$ is:-"]


def test_q9_hindi_stem_matches_the_printed_line_order(doc):
    rows = rows_of(doc, 3, "left", 530, 600)
    assert rows[1].startswith(r"यदि $\vec{A}=\vec{B}+\vec{C}$ तथा $\vec{A},\vec{B}$ तथा $\vec{C}$ के परिमाण")
    assert rows[2] == r"क्रमशः 5,4 तथा 3 इकाई है $\vec{A}$ व $\vec{C}$ के मध्य कोण"


def test_q9_options_keep_function_names_and_tall_brackets(doc):
    rows = rows_of(doc, 3, "right", 600, 660)
    assert rows == [r"(1) $\cos^{-1}(\frac{3}{5})$ (2) $\cos^{-1}(\frac{4}{5})$",
                    r"(3) $\frac{\pi}{2}$ (4) $\sin^{-1}(\frac{3}{4})$"]


def test_q4_four_options_are_separate_and_complete(doc):
    assert rows_of(doc, 2, "right", 540, 680) == [
        r"(1) $\frac{2}{3}(x)^{3/2}-\frac{2}{5}(x)^{5/2}+c$",
        r"(2) $\frac{x^{2}}{2}-\frac{2}{5}(x)^{5/2}+c$",
        r"(3) $x-\frac{2}{3}(x)^{3/2}+c$",
        r"(4) $\frac{x^{2}}{2}-2x^{1/2}+c$"]


def test_q3_options_mix_fonts_inside_one_expression(doc):
    assert rows_of(doc, 2, "right", 440, 520) == [
        r"(1) $2t-e^{t}+\frac{1}{t}$ (2) $\frac{t^{3}}{3}-e^{t}+\frac{1}{t}$",
        r"(3) $t+e^{t}+\log t$ (4) None"]


def test_q5_radicals_in_options(doc):
    assert rows_of(doc, 2, "right", 730, 770) == [
        r"(1) $\sqrt{2}-1$ (2) $\sqrt{2}+1$", r"(3) $1-\sqrt{2}$ (4) $-\sqrt{2}-1$"]


def test_q11_unit_vector_hats(doc):
    assert rows_of(doc, 4, "right", 110, 230) == [
        r"(1) $\frac{1}{\sqrt{2}}\hat{i}+\frac{1}{2}\hat{j}$",
        r"(2) $\frac{1}{\sqrt{2}}\hat{i}+\frac{1}{2}\hat{j}+\frac{1}{2}\hat{k}$",
        r"(3) $\frac{1}{\sqrt{2}}\hat{i}+\frac{1}{2}\hat{j}+\frac{\sqrt{3}}{2}\hat{k}$",
        r"(4) $\frac{1}{\sqrt{2}}\hat{i}+\frac{\sqrt{3}}{2}\hat{j}+\frac{1}{2}\hat{k}$"]


def test_q12_q13_vectors_and_hats_in_stems_and_options(doc):
    rows = rows_of(doc, 4, "right", 255, 400)
    assert r"Component of vector $\vec{A}=2\hat{i}+\hat{j}+\hat{k}$ along" in rows
    assert r"$\vec{B}=\hat{i}-\hat{j}$ will be :-" in rows
    assert r"(1) $\frac{1}{2}(\hat{i}+\hat{j})$ (2) $\frac{1}{2}(\hat{i}-\hat{j})$" in rows
    assert r"If $(3\hat{a}+2\hat{b})$ and $(5\hat{a}-7\hat{b})$ are perpendicular to" in rows
    assert r"each other, find the angle between $\hat{a}$ and $\hat{b}$." in rows


def test_every_character_is_read_exactly_once_on_every_question_page(doc):
    for idx in range(1, 15):
        atoms = extract_page_atoms(doc[idx], idx + 1, "fixture")
        rows = read_rows(atoms, build_units(atoms))
        content = {a.id for a in atoms if a.kind in ("text", "symbol")}
        seen = Counter(i for r in rows for t in r.tokens for i in t.atom_ids if i in content)
        assert content == set(seen), f"page {idx}: {len(content - set(seen))} atoms lost"
        assert not [i for i, c in seen.items() if c > 1], f"page {idx}: atoms read twice"


def test_all_pages_build_ordered_segments_without_math_tree_recursion(doc):
    for idx in range(len(doc)):
        atoms = extract_page_atoms(doc[idx], idx + 1, "fixture-all-pages")
        rows = read_rows(atoms, build_units(atoms))
        assert all(row.page == idx + 1 for row in rows)
        for row in rows:
            for token in row.tokens:
                assert token.atom_ids, (idx + 1, token.text)
                assert set(token.atom_ids) <= {atom.id for atom in atoms}


def test_uncertain_math_never_carries_latex_and_always_says_why(doc):
    uncertain = 0
    for idx in range(1, 15):
        atoms = extract_page_atoms(doc[idx], idx + 1, "fixture")
        for r in read_rows(atoms, build_units(atoms)):
            for t in r.tokens:
                if t.kind == "math" and t.status != "confirmed":
                    uncertain += 1
                    assert t.latex is None and t.reasons
    assert uncertain <= 5      # measured: 2 on this paper, both reported with reasons
