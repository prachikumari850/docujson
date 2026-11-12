const EVIDENCE_ONLY_TYPES = new Set(["math_evidence_source", "diagnostic_page"]);

/**
 * Separate user-facing content media from source crops. Option crops are
 * content only when the option has no recovered text; otherwise they remain
 * available from the collapsed evidence disclosure.
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
