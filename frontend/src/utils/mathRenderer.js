import katex from "katex";

/** Render only source-validated LaTeX. Invalid/unverified input remains visible as text. */
export function renderValidatedLatex(latex, { reviewRequired = true, displayMode = false } = {}) {
    if (typeof latex !== "string" || !latex.trim()) {
        return { status: "missing", html: null, error: null };
    }
    if (reviewRequired !== false) {
        return { status: "review_required", html: null, error: null };
    }

    try {
        return {
            status: "rendered",
            html: katex.renderToString(latex, {
                displayMode,
                output: "htmlAndMathml",
                throwOnError: true,
                trust: false,
                maxSize: 50,
                maxExpand: 1000,
            }),
            error: null,
        };
    } catch (error) {
        return { status: "invalid", html: null, error: error.message };
    }
}
