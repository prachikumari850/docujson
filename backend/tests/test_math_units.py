"""Atoms and math units checked against the preserved SRG Physics source.

Set DOCUJSON_PHYSICS_QP_PDF to override fixture discovery. Page numbers below
are 0-based PyMuPDF indexes."""
import pytest

from app.services.atoms import extract_page_atoms
from app.services.math_units import build_clusters, build_units

import fitz

@pytest.fixture(scope="module")
def doc(physics_qp_doc):
    return physics_qp_doc


def analyse(doc, idx):
    atoms = extract_page_atoms(doc[idx], idx + 1, "fixture")
    return atoms, {a.id: a for a in atoms}, build_units(atoms)


def text_of(amap, ids):
    return "".join(amap[i].text or "" for i in ids)


def test_q3_q4_q5_page_has_eighteen_fractions_and_ten_radicals(doc):
    atoms, amap, units = analyse(doc, 2)
    fr = [u for u in units if u.kind == "frac"]
    rad = [u for u in units if u.kind == "radical"]
    assert len(fr) == 18 and all(u.status == "confirmed" for u in fr)    # 9 per column, counted on the page
    assert len(rad) == 10 and all(u.status == "confirmed" for u in rad)
    assert all(u.parts["numerator"] and u.parts["denominator"] for u in fr)


def test_q4_option_one_fraction_is_2_over_3_and_stays_inside_its_own_rows(doc):
    atoms, amap, units = analyse(doc, 2)
    first = [u for u in units if u.kind == "frac" and text_of(amap, u.parts["numerator"]) == "2"
             and text_of(amap, u.parts["denominator"]) == "3" and u.bbox.x0 > 300 and 540 < u.bbox.y0 < 560]
    assert len(first) == 1
    b = first[0].bbox
    assert 543 <= b.y0 <= 545 and 569 <= b.y1 <= 571          # option 1: 543-570, option 2 starts at 574
    right = [u for u in units if u.kind == "frac" and u.bbox.x0 > 300 and u.bbox.y0 > 500]
    for i, a in enumerate(right):                              # no fraction touches another one
        for c in right[i + 1:]:
            assert a.bbox.overlap_ratio(c.bbox) <= 0.02


def test_pi_over_4_integral_limit_is_not_called_a_script(doc):
    atoms, amap, units = analyse(doc, 2)
    assert not [u for u in units if u.kind == "script" and text_of(amap, u.parts["base"]) == "π"]


def test_exponents_are_superscripts(doc):
    atoms, amap, units = analyse(doc, 2)
    sup = {text_of(amap, u.parts["superscript"]) for u in units
           if u.kind == "script" and u.status == "confirmed" and "superscript" in u.parts and u.bbox.x0 > 300}
    assert {"3/2", "5/2", "2"} <= sup


def test_q9_stem_vector_arrows_bind_a_b_c_a_b_c_a_c(doc):
    atoms, amap, units = analyse(doc, 3)
    vecs = [u for u in units if u.kind == "vec" and u.bbox.x0 > 300
            and 520 < amap[u.parts["arrow"][0]].origin[1] < 580]
    vecs.sort(key=lambda u: (round(amap[u.parts["base"][0]].origin[1]), amap[u.parts["base"][0]].origin[0]))
    assert [text_of(amap, u.parts["base"]) for u in vecs] == list("ABCABCAC")
    assert all(u.status == "confirmed" for u in vecs)


def test_every_vector_arrow_in_the_paper_is_bound_to_a_letter_at_its_own_x(doc):
    n = derived = 0
    for idx in range(1, 15):
        atoms, amap, units = analyse(doc, idx)
        for u in units:
            if u.kind != "vec":
                continue
            assert u.status == "confirmed", (idx, u.reasons)
            arrow, head = amap[u.parts["arrow"][0]], amap[u.parts["base"][0]]
            assert abs(arrow.origin[0] - head.origin[0]) <= 1.5
            n += 1
            derived += arrow.geometry == "derived"
    assert n >= 100 and derived > 0     # font 1621 arrows have wrong PDF boxes and must be rebuilt


def test_zero_width_devanagari_marks_never_become_geometry(doc):
    for idx in (3, 4):
        atoms, amap, units = analyse(doc, idx)
        for u in units:
            for a in u.atom_ids:
                if amap[a].kind == "text":
                    assert amap[a].source.bbox.x1 - amap[a].source.bbox.x0 >= 0.3


def test_table_borders_on_the_column_table_page_are_not_fractions(doc):
    atoms, amap, units = analyse(doc, 10)
    assert not [u for u in units if u.kind == "frac" and u.status == "uncertain"]


def test_clusters_partition_the_atoms(doc):
    atoms, amap, units = analyse(doc, 4)
    clusters = build_clusters(units)
    seen = set()
    for c in clusters:
        assert not (seen & set(c.atom_ids))
        seen |= set(c.atom_ids)
    assert sum(len(c.unit_ids) for c in clusters) == len(units)


def test_synthetic_nested_fraction_pdf_keeps_each_bar_and_its_own_layers(tmp_path):
    """Nested layout not present in the paper: (1/2)/(3/4), built as a PDF."""
    source = tmp_path / "nested-fractions.pdf"
    document = fitz.open()
    page = document.new_page(width=220, height=150)
    # Numerator 1/2, outer bar, denominator 3/4. Each horizontal rule is
    # explicit source drawing geometry; no expected text is synthesized by OCR.
    page.insert_text((104, 61), "1", fontsize=8)
    page.draw_line((99, 64), (108, 64), width=0.7)
    page.insert_text((104, 74), "2", fontsize=8)
    page.draw_line((94, 82), (113, 82), width=0.7)
    page.insert_text((104, 95), "3", fontsize=8)
    page.draw_line((99, 98), (108, 98), width=0.7)
    page.insert_text((104, 108), "4", fontsize=8)
    document.save(source)
    document.close()

    with fitz.open(source) as pdf:
        atoms = extract_page_atoms(pdf[0], 1, "synthetic-nested-fraction")
    atom_map = {atom.id: atom for atom in atoms}
    fractions = [unit for unit in build_units(atoms) if unit.kind == "frac"]
    assert len(fractions) == 3
    assert all(unit.status == "confirmed" for unit in fractions)
    layers = {
        (round(unit.bbox.y0), round(unit.bbox.y1),
         "".join(atom_map[item].text for item in unit.parts["numerator"]),
         "".join(atom_map[item].text for item in unit.parts["denominator"]))
        for unit in fractions
    }
    assert len(layers) == 3
    assert {entry[2:] for entry in layers} == {("1", "2"), ("3", "4"), ("2", "3")}
