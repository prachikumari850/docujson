import test from "node:test";
import assert from "node:assert/strict";
import { getValidatedMathOnlyOption, splitInlineVectorNotation } from "./inlineMath.js";

test("source vector and unit-vector combining marks become explicit KaTeX tokens", () => {
    assert.deepEqual(splitInlineVectorNotation("a⃗ + î"), [
        { type: "math", source: "a⃗", latex: String.raw`\vec{a}` },
        { type: "text", value: " + " },
        { type: "math", source: "î", latex: String.raw`\hat{i}` },
    ]);
});

test("vector notation embedded in bilingual source text retains surrounding text", () => {
    const parts = splitInlineVectorNotation("Resultant a⃗ तथा b⃗ का");
    assert.equal(parts.filter((part) => part.type === "math").length, 2);
    assert.equal(parts.filter((part) => part.type === "text").map((part) => part.value).join(""), "Resultant  तथा  का");
});

test("only a complete math-only option with a confirmed formula is eligible for KaTeX", () => {
    const evidence = [{ latex: String.raw`\cos^{-1}(\frac{3}{5})`, review_required: false }];
    assert.equal(getValidatedMathOnlyOption("cos−¹ ( 3/5", evidence), evidence[0].latex);
    assert.equal(getValidatedMathOnlyOption("always lies in the plane containing a⃗", evidence), null);
    assert.equal(getValidatedMathOnlyOption("cos−¹ ( 3/5", [{ ...evidence[0], review_required: true }]), null);
});
