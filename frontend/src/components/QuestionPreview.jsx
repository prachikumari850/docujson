import { useMemo, useState } from "react";
import { TriangleAlert } from "lucide-react";
import MediaPreview from "./MediaPreview";

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
    return (
        <>
            {text.en && <p className="whitespace-pre-wrap text-base font-medium text-navy">{text.en}</p>}
            {text.hi && (
                <p lang="hi" className="mt-1 whitespace-pre-wrap text-base text-navy/85">
                    {text.hi}
                </p>
            )}
        </>
    );
}

function OptionList({ options, correctAnswer }) {
    if (!options?.length) return null;
    return (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {options.map((option, index) => {
                const correct = correctAnswer !== null && correctAnswer !== undefined && String(correctAnswer) === String(option.id);
                return (
                    <li
                        key={option.id ?? index}
                        className={`flex gap-3 rounded-xl border px-3 py-2 text-sm ${correct ? "border-emerald-300 bg-emerald-50" : "border-lavender bg-white"
                            }`}
                    >
                        <span className="font-bold text-deep-purple">{String.fromCharCode(65 + index)}.</span>
                        <span className="whitespace-pre-wrap text-navy">{option.text}</span>
                    </li>
                );
            })}
        </ul>
    );
}

function QuestionCard({ question, conversionId }) {
    const hasAnswer = question.correct_answer !== null && question.correct_answer !== undefined;

    return (
        <article className="rounded-2xl border border-lavender bg-white p-5 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone="bg-pink-light text-brand-pink">Q{question.question_number ?? "?"}</Badge>
                {question.question_type && <Badge>{question.question_type}</Badge>}
                {question.marks !== null && question.marks !== undefined && <Badge tone="bg-sky-soft text-sky-700">{question.marks} marks</Badge>}
                {question.source?.page && <Badge tone="bg-orange-100 text-orange-700">Page {question.source.page}</Badge>}
                {question.review_required && (
                    <Badge tone="bg-amber-100 text-amber-700">
                        <span className="inline-flex items-center gap-1">
                            <TriangleAlert size={12} /> Needs review
                        </span>
                    </Badge>
                )}
            </div>
            <QuestionText text={question.question} />
            <OptionList options={question.options} correctAnswer={question.correct_answer} />
            <p className="mt-3 text-sm text-navy/70">
                {hasAnswer ? (
                    <>
                        <span className="font-semibold text-navy">Answer:</span> {String(question.correct_answer)}
                    </>
                ) : (
                    "Answer not found in the document."
                )}
            </p>
            <MediaPreview media={question.media} conversionId={conversionId} />
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