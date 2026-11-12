import test from "node:test";
import assert from "node:assert/strict";
import { splitMediaForPreview } from "./mediaPresentation.js";

test("keeps a source crop as answer content when option text is missing", () => {
    const crop = { filename: "option.png", type: "option_crop" };
    assert.deepEqual(splitMediaForPreview([crop], false), { content: [crop], evidence: [] });
});

test("moves a crop to expandable evidence when the answer is already text", () => {
    const crop = { filename: "option.png", type: "option_crop" };
    const diagram = { filename: "diagram.png", type: "diagram" };
    assert.deepEqual(splitMediaForPreview([crop, diagram], true), {
        content: [diagram],
        evidence: [crop],
    });
});

test("never presents diagnostic pages or math source crops as answer content", () => {
    const evidence = [
        { filename: "page.png", type: "diagnostic_page" },
        { filename: "formula.png", type: "math_evidence_source" },
    ];
    assert.deepEqual(splitMediaForPreview(evidence, false), { content: [], evidence });
});
