import { useMemo } from "react";
import { TriangleAlert } from "lucide-react";
import "katex/dist/katex.min.css";
import { renderValidatedLatex } from "../utils/mathRenderer";
import { groupParallelMathEvidence } from "../utils/mathEvidence";
import MediaPreview from "./MediaPreview";

function MathEvidenceItem({ item, occurrences, index, conversionId, suppressExpression }) {
    const rendered = useMemo(
        () => renderValidatedLatex(item.latex, { reviewRequired: item.review_required, displayMode: item.display_mode }),
        [item.latex, item.review_required, item.display_mode]
    );
    const source = item.original_text || item.reconstructed_text || item.normalized_text || item.latex;

    return (
        <li className="rounded-lg border border-lavender bg-white/80 p-3 text-sm">
            {!suppressExpression && rendered.status === "rendered" ? (
                <div className="overflow-x-auto py-1" aria-label={`Validated mathematical expression ${index + 1}`}>
                    <div dangerouslySetInnerHTML={{ __html: rendered.html }} />
                </div>
            ) : !suppressExpression ? (
                <p className="flex items-start gap-2 text-amber-900">
                    <TriangleAlert size={15} className="mt-0.5 shrink-0" />
                    <span>
                        {rendered.status === "invalid"
                            ? "Formula rendering failed; source evidence is preserved."
                            : "Formula is not verified for formatted rendering; inspect the source evidence."}
                        {item.latex && <code className="mt-1 block break-all">{item.latex}</code>}
                    </span>
                </p>
            ) : null}
            {(source || item.source_page || item.review_reasons?.length > 0 || rendered.error || occurrences.length > 1 || item.source_crop_filename) && (
                <details className="mt-2 text-xs text-navy/70">
                    <summary className="cursor-pointer font-semibold">Math source and validation</summary>
                    {source && <p className="mt-1 whitespace-pre-wrap break-words">Source text: {source}</p>}
                    {item.source_page && <p>Page {item.source_page}{item.source_bbox ? ` · ${item.source_bbox.map((value) => Number(value).toFixed(1)).join(", ")}` : ""}</p>}
                    {occurrences.length > 1 && (
                        <ul className="mt-2 space-y-1 border-l-2 border-lavender pl-3">
                            {occurrences.map((occurrence, occurrenceIndex) => (
                                <li key={`${occurrence.atom_ids?.[0] ?? occurrenceIndex}-${occurrence.source_bbox?.join(",")}`}>
                                    Source occurrence {occurrenceIndex + 1}: page {occurrence.source_page ?? "unknown"}
                                    {occurrence.source_bbox ? ` · ${occurrence.source_bbox.map((value) => Number(value).toFixed(1)).join(", ")}` : ""}
                                    {occurrence.atom_ids?.length > 0 && <span> · atoms {occurrence.atom_ids.join(", ")}</span>}
                                </li>
                            ))}
                        </ul>
                    )}
                    {item.review_reasons?.length > 0 && (
                        <ul className="mt-1 list-inside list-disc text-amber-800">
                            {item.review_reasons.map((reason, reasonIndex) => <li key={`${reasonIndex}-${reason}`}>{reason}</li>)}
                        </ul>
                    )}
                    {rendered.error && <p className="mt-1 text-amber-800">{rendered.error}</p>}
                    {item.source_crop_filename && (
                        <div className="mt-2">
                            <p className="font-semibold">Original source region</p>
                            <MediaPreview
                                media={[{ filename: item.source_crop_filename, type: "math_evidence_source", source_page: item.source_page }]}
                                conversionId={conversionId}
                            />
                        </div>
                    )}
                </details>
            )}
        </li>
    );
}

export default function MathEvidencePreview({ evidence, conversionId, inline = false, suppressExpression = false }) {
    if (!evidence?.length) return null;

    const items = (
        <ul className="mt-3 space-y-2" aria-label="Mathematical source evidence">
            {groupParallelMathEvidence(evidence).map(({ item, occurrences }, index) => (
                <MathEvidenceItem
                    key={`${item.source_page ?? "page"}-${item.atom_ids?.[0] ?? index}`}
                    item={item}
                    occurrences={occurrences}
                    index={index}
                    conversionId={conversionId}
                    suppressExpression={suppressExpression}
                />
            ))}
        </ul>
    );
    if (inline) return items;
    return (
        <details className="mt-3 rounded-lg border border-lavender/70 bg-lavender-light/30 p-2">
            <summary className="cursor-pointer text-xs font-semibold text-deep-purple">
                Mathematical evidence ({groupParallelMathEvidence(evidence).length})
            </summary>
            {items}
        </details>
    );
}
