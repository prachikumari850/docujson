import test from "node:test";
import assert from "node:assert/strict";
import { splitMediaForPreview, buildQuestionContentLayout, pairQuestionMediaWithOptions, } from "./mediaPresentation.js";

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


test("keeps Hindi and English text in separate coordinate columns", () => {
    const question = {
        ordered_segments: [
            {
                text: "English question",
                source_page: 7,
                source_bbox: [304, 423, 554, 441],
                reading_column: "right",
            },
            {
                text: "Hindi question",
                source_page: 7,
                source_bbox: [40, 424, 289, 441],
                reading_column: "left",
            },
        ],
        media: [],
    };

    const layout = buildQuestionContentLayout(question);

    assert.equal(layout.left[0].text, "Hindi question");
    assert.equal(layout.right[0].text, "English question");
});

test("places SVG media in coordinate order with text", () => {
    const question = {
        ordered_segments: [
            {
                text: "Question text",
                source_page: 7,
                source_bbox: [304, 423, 554, 481],
                reading_column: "right",
            },
        ],
        media: [
            {
                filename: "diagram.svg",
                type: "image",
                source_page: 7,
                bbox: [403, 481, 484, 550],
            },
        ],
    };

    const layout = buildQuestionContentLayout(question);

    assert.deepEqual(
        layout.right.map((item) => item.type),
        ["text", "media"],
    );

    assert.equal(layout.right[1].media.filename, "diagram.svg");
});

test("returns null when positional text data is unavailable", () => {
    assert.equal(buildQuestionContentLayout({
        question: { en: "Question text" },
        media: [],
    }), null);
});

test("sorts content by page and vertical position", () => {
    const question = {
        ordered_segments: [
            {
                text: "Second line",
                source_page: 7,
                source_bbox: [304, 450, 554, 468],
                reading_column: "right",
            },
            {
                text: "First line",
                source_page: 7,
                source_bbox: [304, 423, 554, 441],
                reading_column: "right",
            },
        ],
        media: [],
    };

    const layout = buildQuestionContentLayout(question);

    assert.deepEqual(
        layout.right.map((item) => item.text),
        ["First line", "Second line"],
    );
});


test("pairs question-level option diagrams by visual row and left-to-right order", () => {
    const makeMedia = (filename, bbox) => ({
        filename,
        type: "image",
        source_page: 7,
        bbox,
    });

    const question = {
        options: [
            { id: "1", media: [] },
            { id: "2", media: [] },
            { id: "3", media: [] },
            { id: "4", media: [] },
        ],
        media: [
            makeMedia("main.svg", [403, 481, 484, 550]),
            makeMedia("option-1.svg", [353, 558, 424, 616]),
            makeMedia("option-2.svg", [464, 556, 524, 617]),
            makeMedia("option-3.svg", [353, 623, 430, 688]),
            makeMedia("option-4.svg", [464, 625, 535, 685]),
        ],
    };

    const result = pairQuestionMediaWithOptions(question);

    assert.equal(result.mainMedia.filename, "main.svg");
    assert.deepEqual(
        result.options.map((option) => option.media[0].filename),
        ["option-1.svg", "option-2.svg", "option-3.svg", "option-4.svg"],
    );
});

test("does not guess option pairing when media count is ambiguous", () => {
    const result = pairQuestionMediaWithOptions({
        options: [{ id: "1" }, { id: "2" }, { id: "3" }, { id: "4" }],
        media: [{ filename: "main.svg", bbox: [10, 10, 50, 50] }],
    });

    assert.equal(result, null);
});


test("joins text fragments sharing a visual baseline into one line", () => {
    const makeSegment = (text, x, baseline) => ({
        text,
        reading_column: "left",
        reading_baseline: baseline,
        source_page: 7,
        source_bbox: [x, baseline - 10, x + 40, baseline + 6],
    });

    const layout = buildQuestionContentLayout({
        ordered_segments: [
            makeSegment("तीन समतलीय सदिशों", 68, 75.38),
            makeSegment("तथा", 176, 75.38),
            makeSegment("C→", 198, 75.38),
            makeSegment("के परिमाण क्रमशः 4,", 210, 75.38),
            makeSegment("3 तथा 2 है।", 68, 92.17),
        ],
        media: [],
    });

    assert.equal(layout.left.length, 2);

    assert.equal(
        layout.left[0].text,
        "तीन समतलीय सदिशों तथा C→ के परिमाण क्रमशः 4,"
    );

    assert.equal(layout.left[1].text, "3 तथा 2 है।");
});

test("keeps text on different pages and baselines in separate lines", () => {
    const makeSegment = (text, page, baseline) => ({
        text,
        reading_column: "right",
        reading_baseline: baseline,
        source_page: page,
        source_bbox: [300, baseline - 10, 400, baseline + 6],
    });

    const layout = buildQuestionContentLayout({
        ordered_segments: [
            makeSegment("First line", 1, 100),
            makeSegment("Second line", 1, 120),
            makeSegment("Next page", 2, 100),
        ],
        media: [],
    });

    assert.equal(layout.right.length, 3);
    assert.deepEqual(
        layout.right.map((item) => item.text),
        ["First line", "Second line", "Next page"]
    );
});
