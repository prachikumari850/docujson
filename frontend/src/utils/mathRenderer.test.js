import test from "node:test";
import assert from "node:assert/strict";
import { renderValidatedLatex } from "./mathRenderer.js";

test("verified fraction and vector notation render with KaTeX MathML accessibility output", () => {
    const result = renderValidatedLatex(String.raw`\frac{\vec{A}\times\vec{B}}{\sqrt{2}}`, { reviewRequired: false });
    assert.equal(result.status, "rendered");
    assert.match(result.html, /class="katex"/);
    assert.match(result.html, /<math/);
    assert.match(result.html, /\bfrac\b|mfrac/);
});

test("unreviewed LaTeX remains source text and is not presented as verified math", () => {
    const result = renderValidatedLatex(String.raw`\frac{x}{y}`, { reviewRequired: true });
    assert.deepEqual(result, { status: "review_required", html: null, error: null });
});

test("invalid LaTeX is reported without throwing or injecting trusted commands", () => {
    const invalid = renderValidatedLatex(String.raw`\notARealCommand{x}`, { reviewRequired: false });
    assert.equal(invalid.status, "invalid");
    assert.equal(invalid.html, null);
    assert.ok(invalid.error);

    const untrusted = renderValidatedLatex(String.raw`\href{javascript:alert(1)}{x}`, { reviewRequired: false });
    assert.notEqual(untrusted.status, "review_required");
    assert.doesNotMatch(untrusted.html ?? "", /<a\b|href\s*=/i);
});
