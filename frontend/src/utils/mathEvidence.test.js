import test from "node:test";
import assert from "node:assert/strict";
import { groupParallelMathEvidence } from "./mathEvidence.js";

const evidence = (latex, bbox, atom) => ({
    latex,
    source_page: 3,
    source_bbox: bbox,
    atom_ids: [atom],
});

test("aligned bilingual copies render once while retaining both source occurrences", () => {
    const source = [
        evidence(String.raw`\frac{x^2}{2}`, [80, 100, 130, 120], "left-atom"),
        evidence(String.raw`\frac{x^2}{2}`, [350, 102, 400, 122], "right-atom"),
    ];

    const groups = groupParallelMathEvidence(source);
    assert.equal(groups.length, 1);
    assert.equal(groups[0].occurrences.length, 2);
    assert.deepEqual(groups[0].occurrences.map((item) => item.atom_ids[0]), ["left-atom", "right-atom"]);
});

test("same formula at another vertical position remains a separate expression", () => {
    const groups = groupParallelMathEvidence([
        evidence("x+1", [80, 100, 130, 120], "first"),
        evidence("x+1", [350, 140, 400, 160], "later-row"),
    ]);
    assert.equal(groups.length, 2);
});

test("same formula within one column remains a separate source occurrence", () => {
    const groups = groupParallelMathEvidence([
        evidence("x+1", [80, 100, 130, 120], "first"),
        evidence("x+1", [145, 100, 195, 120], "neighbor"),
    ]);
    assert.equal(groups.length, 2);
});

test("different formulas on an aligned row are never grouped", () => {
    const groups = groupParallelMathEvidence([
        evidence("x+1", [80, 100, 130, 120], "first"),
        evidence("x-1", [350, 100, 400, 120], "different"),
    ]);
    assert.equal(groups.length, 2);
});
