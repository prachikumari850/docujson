import { renderValidatedLatex } from "./mathRenderer.js";

const VECTOR_MARKS = new Map([
    ["\u20d7", "vec"],
    ["\u0302", "hat"],
]);

/**
 * Convert only explicit Unicode combining vector/unit-vector marks from the
 * source text into KaTeX candidates. The base symbol and mark are both kept
 * in `source`; no missing notation is inferred.
 */
export function splitInlineVectorNotation(source = "") {
    const text = String(source);
    const parts = [];
    let plainStart = 0;
    let index = 0;

    while (index < text.length) {
        const mark = text[index + 1];
        const accent = VECTOR_MARKS.get(mark);
        const base = text[index];
        if (accent && /[\p{L}\p{N}]/u.test(base)) {
            if (plainStart < index) {
                parts.push({ type: "text", value: text.slice(plainStart, index) });
            }
            parts.push({
                type: "math",
                source: text.slice(index, index + 2),
                latex: `\\${accent}{${base}}`,
            });
            index += 2;
            plainStart = index;
        } else {
            index += 1;
        }
    }

    if (plainStart < text.length) {
        parts.push({ type: "text", value: text.slice(plainStart) });
    }
    return parts.length ? parts : [{ type: "text", value: text }];
}

/**
 * Return a validated display expression only for a math-only option. This
 * prevents replacing ordinary prose with a partial formula candidate.
 */
export function getValidatedMathOnlyOption(text, evidence = []) {
    const source = String(text ?? "").trim();
    if (!source || source.length > 48) return null;

    const hasMathSyntax = /[0-9πθαλβγ√∫=+−\-×÷/^()|]/u.test(source);
    const hasProseWords = /\b(?:always|never|lies|plane|containing|can|cannot|zero|and|the|is|are|of|with)\b/i.test(source);
    if (!hasMathSyntax || hasProseWords) return null;

    const valid = (evidence ?? []).filter((item) =>
        item?.review_required === false &&
        typeof item.latex === "string" &&
        renderValidatedLatex(item.latex, { reviewRequired: false }).status === "rendered"
    );
    const uniqueLatex = [...new Set(valid.map((item) => item.latex))];
    if (uniqueLatex.length !== 1) return null;

    return uniqueLatex[0];
}
