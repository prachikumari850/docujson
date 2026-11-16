import { useMemo, useState } from "react";
import { TriangleAlert } from "lucide-react";
import MediaPreview from "./MediaPreview";
import MathEvidencePreview from "./MathEvidencePreview";
import {
    splitMediaForPreview,
    buildQuestionContentLayout,
    pairQuestionMediaWithOptions,
} from "../utils/mediaPresentation";
import { getValidatedMathOnlyOption, splitInlineVectorNotation } from "../utils/inlineMath";
import { renderValidatedLatex } from "../utils/mathRenderer";

const PAGE_SIZE = 25;
const RAW_JSON_LIMIT = 30000;

function flattenQuestions(sections) {
    return (sections ?? []).flatMap((section) =>
        (section.questions ?? []).map((question) => ({ sectionName: section.section_name, question }))
    );
}

function Badge({ children, tone = "bg-lavender text-deep-purple" }) {
    return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>{children}</span>;
}

function QuestionText({ text }) {
    if (!text) return null;
    const renderText = (value, lang) => (
        <span lang={lang}>
            {splitInlineVectorNotation(value).map((part, index) => {
                if (part.type === "text") return <span key={`${lang}-${index}`}>{part.value}</span>;
                const rendered = renderValidatedLatex(part.latex, { reviewRequired: false });
                return rendered.status === "rendered"
                    ? <span key={`${lang}-${index}`} className="align-baseline" dangerouslySetInnerHTML={{ __html: rendered.html }} />
                    : <span key={`${lang}-${index}`}>{part.source}</span>;
            })}
        </span>
    );
    return (
        <>
            {text.en && <p className="whitespace-pre-wrap text-base font-medium text-navy">{renderText(text.en, "en")}</p>}
            {text.hi && (
                <p lang="hi" className="mt-1 whitespace-pre-wrap text-base text-navy/85">
                    {renderText(text.hi, "hi")}
                </p>
            )}
        </>
    );
}


function needsSpaceBetween(previous, current) {
    const left = String(previous?.text ?? "").trim();
    const right = String(current?.text ?? "").trim();

    if (!left || !right) return false;

    if (/^[,.;:!?%)\]}।]/u.test(right)) return false;
    if (/[(\[{]$/u.test(left)) return false;

    return true;
}


function SegmentText({ item, mathEvidence = [] }) {
    const segments = item.sources?.length
        ? item.sources
        : item.source
            ? [item.source]
            : [];

    if (!segments.length) return null;

    return (
        <span className="whitespace-pre-wrap text-base text-navy">
            {segments.map((segment, index) => {
                const previous = segments[index - 1];
                const lang = getSegmentLanguage(segment);

                return (
                    <span key={`${lang}-${index}`}>
                        {index > 0 && needsSpaceBetween(previous, segment) && " "}
                        {segment.kind === "math" &&
                            segment.status === "confirmed" &&
                            segment.review_reasons?.length === 0 &&
                            typeof segment.latex === "string" ? (
                            (() => {
                                const rendered = renderValidatedLatex(
                                    segment.latex,
                                    { reviewRequired: false }
                                );

                                return rendered.status === "rendered" ? (
                                    <span
                                        lang={lang}
                                        className="inline-block align-baseline"
                                        dangerouslySetInnerHTML={{
                                            __html: rendered.html,
                                        }}
                                    />
                                ) : (
                                    segment.text
                                );
                            })()
                        ) : (
                            <span lang={lang}>
                                {splitInlineVectorNotation(segment.text).map(
                                    (part, partIndex) => {
                                        if (part.type === "text") {
                                            return (
                                                <span key={partIndex}>
                                                    {part.value}
                                                </span>
                                            );
                                        }

                                        const rendered = renderValidatedLatex(
                                            part.latex,
                                            { reviewRequired: false }
                                        );

                                        return rendered.status === "rendered" ? (
                                            <span
                                                key={partIndex}
                                                className="align-baseline"
                                                dangerouslySetInnerHTML={{
                                                    __html: rendered.html,
                                                }}
                                            />
                                        ) : (
                                            <span key={partIndex}>
                                                {part.source}
                                            </span>
                                        );
                                    }
                                )}
                            </span>
                        )}
                    </span>
                );
            })}
        </span>
    );
}


function getSegmentLanguage(segment) {
    if (segment.language || segment.lang) {
        return segment.language || segment.lang;
    }

    // Detect Devanagari text rather than assuming a particular column language.
    return /[\u0900-\u097F]/.test(segment.text ?? "") ? "hi" : "en";
}

function QuestionContent({ question, conversionId, pairedMedia }) {
    const contentQuestion = pairedMedia
        ? { ...question, media: [pairedMedia.mainMedia] }
        : question;

    const layout = buildQuestionContentLayout(contentQuestion);

    if (!layout) {
        return (
            <>
                <QuestionText text={question.question} />
                <MediaPreview
                    media={pairedMedia ? [pairedMedia.mainMedia] : question.media}
                    conversionId={conversionId}
                    inline
                />
            </>
        );
    }

    const renderColumn = (items) =>
        items.map((item, index) => (
            <div key={`${item.type}-${item.page}-${index}`} className="min-w-0">
                {item.type === "text" ? (
                    <SegmentText
                        item={item}
                        mathEvidence={question.math_evidence}
                    />
                ) : (
                    <MediaPreview
                        media={[item.media]}
                        conversionId={conversionId}
                        inline
                    />
                )}
            </div>
        ));

    return (
        <div className="mt-2 grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-2">
            <div className="min-w-0 space-y-2">
                {renderColumn(layout.left)}
            </div>

            <div className="min-w-0 space-y-2">
                {renderColumn(layout.right)}
            </div>

            {layout.full.length > 0 && (
                <div className="col-span-full min-w-0 space-y-2">
                    {renderColumn(layout.full)}
                </div>
            )}
        </div>
    );
}


function OptionList({ options, correctAnswer, conversionId }) {
    if (!options?.length) return null;
    const visibleOptions = [...options]
        .sort((left, right) => String(left.id).localeCompare(String(right.id), undefined, { numeric: true }));
    return (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {visibleOptions.map((option, index) => {
                const correct = correctAnswer !== null && correctAnswer !== undefined && String(correctAnswer) === String(option.id);
                const hasText = Boolean(option.text?.trim());
                const media = splitMediaForPreview(option.media, hasText);
                const validatedMath = getValidatedMathOnlyOption(option.text, option.math_evidence);
                const renderedMath = validatedMath
                    ? renderValidatedLatex(validatedMath, { reviewRequired: false })
                    : null;
                return (
                    <li
                        key={option.id ?? index}
                        className={`flex gap-3 rounded-xl border px-3 py-2 text-sm ${correct ? "border-emerald-300 bg-emerald-50" : "border-lavender bg-white"
                            }`}
                    >
                        <span className="font-bold text-deep-purple">{/^\d+$/.test(String(option.id)) ? `(${option.id})` : `${option.id}.`}</span>
                        <div className="min-w-0 flex-1 whitespace-pre-wrap break-words text-navy">
                            {renderedMath?.status === "rendered" ? (
                                <>
                                    <span className="inline-block max-w-full overflow-x-auto overflow-y-hidden align-middle" aria-label={`Validated option ${option.id} formula`} dangerouslySetInnerHTML={{ __html: renderedMath.html }} />
                                    <details className="mt-2 text-xs text-navy/70">
                                        <summary className="cursor-pointer font-semibold">Original extracted formula text</summary>
                                        <p className="mt-1 whitespace-pre-wrap">{option.text}</p>
                                    </details>
                                </>
                            ) : (
                                <>
                                    {hasText ? splitInlineVectorNotation(option.text.trim()).map((part, partIndex) => {
                                        if (part.type === "text") return <span key={`${option.id}-text-${partIndex}`}>{part.value}</span>;
                                        const vector = renderValidatedLatex(part.latex, { reviewRequired: false });
                                        return vector.status === "rendered"
                                            ? <span key={`${option.id}-math-${partIndex}`} dangerouslySetInnerHTML={{ __html: vector.html }} />
                                            : <span key={`${option.id}-raw-${partIndex}`}>{part.source}</span>;
                                    }) : (!media.content.length && <span className="italic text-amber-800">Text could not be recovered; review the source.</span>)}
                                </>
                            )}
                            <MathEvidencePreview evidence={option.math_evidence} conversionId={conversionId} inline={!hasText} suppressExpression={renderedMath?.status === "rendered"} />
                            {option.vision_verification?.candidate_transcription && (
                                <span className="mt-2 block rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                                    <strong>Unverified local vision candidate:</strong> {option.vision_verification.candidate_transcription}
                                </span>
                            )}
                            {media.content.length > 0 && (
                                <MediaPreview
                                    media={media.content}
                                    conversionId={conversionId}
                                    inline
                                />
                            )}
                            {media.evidence.length > 0 && (
                                <details className="mt-3 rounded-lg border border-lavender/70 bg-lavender-light/30 p-2 text-xs text-navy/80">
                                    <summary className="cursor-pointer font-semibold">Source crops and media evidence ({media.evidence.length})</summary>
                                    <MediaPreview media={media.evidence} conversionId={conversionId} />
                                </details>
                            )}
                        </div>
                    </li>
                );
            })}
        </ul>
    );
}


function QuestionCard({ question, conversionId }) {
    const hasAnswer =
        question.correct_answer !== null &&
        question.correct_answer !== undefined;

    const pairedMedia = pairQuestionMediaWithOptions(question);

    return (
        <article className="rounded-2xl border border-lavender bg-white p-5 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone="bg-pink-light text-brand-pink">
                    Q{question.question_number ?? "?"}
                </Badge>

                {question.question_type && (
                    <Badge>{question.question_type}</Badge>
                )}

                {question.marks !== null && question.marks !== undefined && (
                    <Badge tone="bg-sky-soft text-sky-700">
                        {question.marks} marks
                    </Badge>
                )}

                {question.source?.page && (
                    <Badge tone="bg-orange-100 text-orange-700">
                        Page {question.source.page}
                    </Badge>
                )}

                {question.review_required && (
                    <Badge tone="bg-amber-100 text-amber-700">
                        <span className="inline-flex items-center gap-1">
                            <TriangleAlert size={12} />
                            Needs review
                        </span>
                    </Badge>
                )}
            </div>

            <QuestionContent
                question={question}
                conversionId={conversionId}
                pairedMedia={pairedMedia}
            />

            <MathEvidencePreview
                evidence={question.math_evidence}
                conversionId={conversionId}
                inline={
                    !question.question?.en?.trim() &&
                    !question.question?.hi?.trim()
                }
            />

            <OptionList
                options={pairedMedia?.options ?? question.options}
                correctAnswer={question.correct_answer}
                conversionId={conversionId}
            />

            {question.review_required &&
                question.review_reasons?.length > 0 && (
                    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                        <p className="font-semibold">Review needed</p>
                        <ul className="mt-1 list-inside list-disc">
                            {question.review_reasons.map((reason, index) => (
                                <li key={`${index}-${reason}`}>{reason}</li>
                            ))}
                        </ul>
                    </div>
                )}

            <p className="mt-3 text-sm text-navy/70">
                {hasAnswer ? (
                    <>
                        <span className="font-semibold text-navy">
                            Answer:
                        </span>{" "}
                        {String(question.correct_answer)}
                    </>
                ) : (
                    "Answer not found in the document."
                )}
            </p>

            {!buildQuestionContentLayout(
                pairedMedia
                    ? { ...question, media: [pairedMedia.mainMedia] }
                    : question
            ) && (
                    <MediaPreview
                        media={[]}
                        conversionId={conversionId}
                    />
                )}
        </article>
    );
}


function QuestionList({ items, conversionId }) {
    const [visible, setVisible] = useState(PAGE_SIZE);
    const shown = items.slice(0, visible);

    return (
        <div className="space-y-4">
            {shown.map(({ sectionName, question }, index) => (
                <div key={question.question_id ?? index}>
                    {sectionName && sectionName !== shown[index - 1]?.sectionName && (
                        <h3 className="mb-3 mt-2 text-lg font-bold text-deep-purple">{sectionName}</h3>
                    )}
                    <QuestionCard question={question} conversionId={conversionId} />
                </div>
            ))}
            {visible < items.length && (
                <button
                    type="button"
                    onClick={() => setVisible((count) => count + PAGE_SIZE)}
                    className="mx-auto block rounded-full border border-lavender bg-white px-6 py-2 text-sm font-semibold text-deep-purple hover:bg-lavender-light"
                >
                    Show more ({items.length - visible} remaining)
                </button>
            )}
        </div>
    );
}

function RawJson({ result }) {
    const text = useMemo(() => JSON.stringify(result, null, 2), [result]);
    const truncated = text.length > RAW_JSON_LIMIT;

    return (
        <div>
            <pre className="max-h-[32rem] overflow-auto rounded-2xl bg-navy p-5 text-xs leading-relaxed text-lavender">
                {truncated ? text.slice(0, RAW_JSON_LIMIT) : text}
            </pre>
            {truncated && <p className="mt-2 text-xs text-navy/60">Preview truncated. Download the JSON for the full output.</p>}
        </div>
    );
}

export default function QuestionPreview({ result, conversionId }) {
    const [tab, setTab] = useState("questions");
    const items = useMemo(() => flattenQuestions(result?.sections), [result]);
    const reviewCount = items.filter(({ question }) => question.review_required).length;

    return (
        <section id="examples" className="mx-auto mt-14 w-full max-w-4xl">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-2xl font-bold text-navy sm:text-3xl">Conversion Preview</h2>
                {result && (
                    <div className="flex gap-2 rounded-full bg-white p-1 shadow-sm ring-1 ring-lavender">
                        {["questions", "json"].map((name) => (
                            <button
                                key={name}
                                type="button"
                                onClick={() => setTab(name)}
                                className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${tab === name ? "bg-linear-to-r from-brand-orange to-brand-pink text-white" : "text-navy"
                                    }`}
                            >
                                {name === "questions" ? "Questions" : "Raw JSON"}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {!result ? (
                <p className="rounded-2xl bg-white/70 p-8 text-center text-navy/70 ring-1 ring-white">
                    Your extracted questions, options, answers and diagrams will appear here after conversion.
                </p>
            ) : (
                <>
                    <div className="mb-4 flex flex-wrap gap-2">
                        <Badge>{result.document?.title || "Untitled document"}</Badge>
                        <Badge tone="bg-pink-light text-brand-pink">{items.length} questions</Badge>
                        {reviewCount > 0 && <Badge tone="bg-amber-100 text-amber-700">{reviewCount} need review</Badge>}
                    </div>
                    {tab === "questions" ? <QuestionList items={items} conversionId={conversionId} /> : <RawJson result={result} />}
                </>
            )}
        </section>
    );
}
