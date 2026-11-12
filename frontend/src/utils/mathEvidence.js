function boxOf(evidence) {
    const box = evidence?.source_bbox;
    return Array.isArray(box) && box.length === 4 && box.every(Number.isFinite) ? box : null;
}

function sameParallelOccurrence(left, right) {
    if (!left?.latex || left.latex !== right?.latex || left.source_page !== right.source_page) return false;
    const a = boxOf(left);
    const b = boxOf(right);
    if (!a || !b) return false;
    const aY = (a[1] + a[3]) / 2;
    const bY = (b[1] + b[3]) / 2;
    const aX = (a[0] + a[2]) / 2;
    const bX = (b[0] + b[2]) / 2;
    return Math.abs(aY - bY) <= 8 && Math.abs(aX - bX) >= 100;
}

/**
 * Group a repeated formula only when source geometry shows aligned copies in
 * separate columns. Keep every underlying evidence object for provenance.
 */
export function groupParallelMathEvidence(evidence = []) {
    const groups = [];
    for (const item of evidence) {
        const group = groups.find((candidate) =>
            candidate.occurrences.some((occurrence) => sameParallelOccurrence(occurrence, item))
        );
        if (group) group.occurrences.push(item);
        else groups.push({ item, occurrences: [item] });
    }
    return groups;
}
