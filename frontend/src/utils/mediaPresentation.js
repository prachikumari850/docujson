
const EVIDENCE_ONLY_TYPES = new Set(["math_evidence_source", "diagnostic_page"]);

/**
 * Separate user-facing content media from source crops.
 */
export function splitMediaForPreview(media = [], hasReadableText = false) {
    const content = [];
    const evidence = [];

    for (const item of media ?? []) {
        if (EVIDENCE_ONLY_TYPES.has(item?.type)) {
            evidence.push(item);
        } else if (item?.type === "option_crop" && hasReadableText) {
            evidence.push(item);
        } else {
            content.push(item);
        }
    }

    return { content, evidence };
}

function getPosition(item) {
    const bbox = item?.source_bbox ?? item?.bbox;

    if (!Array.isArray(bbox) || bbox.length < 4) {
        return null;
    }

    const [x0, y0, x1, y1] = bbox.map(Number);

    if (![x0, y0, x1, y1].every(Number.isFinite)) {
        return null;
    }

    return {
        x: x0,
        y: y0,
        right: x1,
        bottom: y1,
        centerX: (x0 + x1) / 2,
        centerY: (y0 + y1) / 2,
    };
}

function getPage(item) {
    return Number(item?.source_page ?? item?.page ?? 0);
}

function getColumn(item, position) {
    if (item?.reading_column) {
        return item.reading_column;
    }

    if (item?.column) {
        return item.column;
    }

    // Media without a text-column label is assigned by its horizontal
    // position. The caller can use "full" for assets spanning both columns.
    if (position) {
        return position.centerX < 297.5 ? "left" : "right";
    }

    return "full";
}



function getTextLanguage(segment) {
    const explicitLanguage = segment?.language || segment?.lang;

    if (explicitLanguage) {
        const normalized = explicitLanguage.toLowerCase();

        if (normalized.startsWith("hi")) return "hi";
        if (normalized.startsWith("en")) return "en";

        return null;
    }

    const text = segment?.text ?? "";

    if (/[\u0900-\u097F]/u.test(text)) return "hi";

    // Ignore isolated Latin variables such as C, x, A→ and B⃗.
    if (/[A-Za-z]{2,}/u.test(text)) return "en";

    return null;
}



function getBaseline(item, position) {
    const baseline = Number(item?.reading_baseline);

    return Number.isFinite(baseline)
        ? baseline
        : position.centerY;
}

function joinTextFragments(fragments) {
    return fragments
        .map((fragment) => String(fragment.text ?? "").trim())
        .filter(Boolean)
        .reduce((result, current) => {
            if (!result) return current;

            // Avoid inserting spaces before common punctuation.
            if (/^[,.;:!?%)\]}।]/u.test(current)) {
                return result + current;
            }

            // Avoid inserting spaces after opening brackets.
            if (/[(\[{]$/u.test(result)) {
                return result + current;
            }

            return `${result} ${current}`;
        }, "");
}


export function buildQuestionContentLayout(question) {
    const segments = question?.ordered_segments;

    if (!Array.isArray(segments) || segments.length === 0) {
        return null;
    }

    const columns = {
        left: [],
        right: [],
        full: [],
    };

    const textGroups = {
        left: [],
        right: [],
        full: [],
    };

    // First collect positioned text segments.
    for (const segment of segments) {
        const position = getPosition(segment);

        if (!position || !segment?.text?.trim()) {
            continue;
        }

        const column = getColumn(segment, position);
        const columnName = column in columns ? column : "full";


        textGroups[columnName].push({
            type: "text",
            page: getPage(segment),
            position,
            baseline: getBaseline(segment, position),
            language: getTextLanguage(segment),
            source: segment,
            text: segment.text,
        });

    }

    // Reconstruct individual text lines using page and baseline.
    for (const [columnName, fragments] of Object.entries(textGroups)) {
        fragments.sort(
            (a, b) =>
                a.page - b.page ||
                a.baseline - b.baseline ||
                a.position.x - b.position.x
        );

        const lines = [];

        for (const fragment of fragments) {

            let matchingLine = lines.find(
                (line) =>
                    line.page === fragment.page &&
                    (
                        !line.language ||
                        !fragment.language ||
                        line.language === fragment.language
                    ) &&
                    Math.abs(line.baseline - fragment.baseline) <= 3.5
            );


            if (!matchingLine) {
                matchingLine = {
                    type: "text",
                    page: fragment.page,
                    baseline: fragment.baseline,
                    language: fragment.language,
                    position: { ...fragment.position },
                    fragments: [],
                    sources: [],
                };

                lines.push(matchingLine);
            }

            if (!matchingLine.language && fragment.language) {
                matchingLine.language = fragment.language;
            }

            matchingLine.fragments.push(fragment);

            matchingLine.position.x = Math.min(
                matchingLine.position.x,
                fragment.position.x
            );

            matchingLine.position.y = Math.min(
                matchingLine.position.y,
                fragment.position.y
            );

            matchingLine.position.right = Math.max(
                matchingLine.position.right,
                fragment.position.right
            );

            matchingLine.position.bottom = Math.max(
                matchingLine.position.bottom,
                fragment.position.bottom
            );

            matchingLine.sources.push(fragment.source);
        }

        for (const line of lines) {
            line.fragments.sort(
                (a, b) => a.position.x - b.position.x
            );

            line.text = joinTextFragments(line.fragments);

            line.source = line.sources[0];

            line.position.centerX =
                (line.position.x + line.position.right) / 2;

            line.position.centerY =
                (line.position.y + line.position.bottom) / 2;

            delete line.fragments;
            delete line.baseline;
        }

        columns[columnName].push(...lines);
    }

    // Add question-level media without changing their original objects.
    for (const media of question?.media ?? []) {
        if (EVIDENCE_ONLY_TYPES.has(media?.type)) {
            continue;
        }

        const position = getPosition(media);

        if (!position) {
            continue;
        }

        const column = getColumn(media, position);
        const columnName = column in columns ? column : "full";

        columns[columnName].push({
            type: "media",
            page: getPage(media),
            position,
            source: media,
            media,
        });
    }

    // Sort reconstructed lines and diagrams into visual reading order.
    for (const items of Object.values(columns)) {
        items.sort(
            (a, b) =>
                a.page - b.page ||
                a.position.y - b.position.y ||
                a.position.x - b.position.x
        );
    }

    const hasContent = Object.values(columns).some(
        (items) => items.length > 0
    );

    return hasContent ? columns : null;
}

export function pairQuestionMediaWithOptions(question) {
    const options = [...(question?.options ?? [])].sort((a, b) =>
        String(a.id).localeCompare(String(b.id), undefined, { numeric: true })
    );

    const media = (question?.media ?? []).filter(
        (item) =>
            !EVIDENCE_ONLY_TYPES.has(item?.type) &&
            item?.type !== "option_crop"
    );

    if (options.length < 2 || media.length !== options.length + 1) {
        return null;
    }

    const positioned = media.map((item) => ({
        item,
        position: getPosition(item),
        page: getPage(item),
    }));

    if (positioned.some(({ position }) => !position)) {
        return null;
    }

    const pages = new Set(positioned.map(({ page }) => page));
    if (pages.size !== 1) {
        return null;
    }

    positioned.sort((a, b) => a.position.centerY - b.position.centerY);

    const rows = [];

    for (const entry of positioned) {
        const matchingRow = rows.find((row) =>
            row.some((existing) => {
                const overlap = Math.max(
                    0,
                    Math.min(entry.position.bottom, existing.position.bottom) -
                    Math.max(entry.position.y, existing.position.y)
                );
                const smallerHeight = Math.min(
                    entry.position.bottom - entry.position.y,
                    existing.position.bottom - existing.position.y
                );

                return smallerHeight > 0 && overlap / smallerHeight >= 0.5;
            })
        );

        if (matchingRow) {
            matchingRow.push(entry);
        } else {
            rows.push([entry]);
        }
    }

    rows.sort((a, b) => {
        const averageY = (row) =>
            row.reduce((sum, entry) => sum + entry.position.centerY, 0) / row.length;
        return averageY(a) - averageY(b);
    });

    rows.forEach((row) =>
        row.sort((a, b) => a.position.x - b.position.x)
    );

    const orderedMedia = rows.flat();

    if (orderedMedia.length !== options.length + 1) {
        return null;
    }

    return {
        mainMedia: orderedMedia[0].item,
        options: options.map((option, index) => ({
            ...option,
            media: [
                orderedMedia[index + 1].item,
            ],
        })),
    };
}
