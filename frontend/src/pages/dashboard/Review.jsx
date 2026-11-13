
import { useCallback, useEffect, useMemo, useState } from "react";
import {
    AlertCircle,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock3,
    LoaderCircle,
    RefreshCw,
    Search,
    X,
    XCircle,
} from "lucide-react";

import QuestionPreview from "../../components/QuestionPreview";
import {
    getReviewQuestions,
    updateReviewDecision,
} from "../../services/converterApi";

const PAGE_SIZE = 25;

const DECISIONS = [
    { value: "pending", label: "Pending review" },
    { value: "approved", label: "Approved" },
    { value: "rejected", label: "Rejected" },
];

function DecisionBadge({ decision }) {
    const styles = {
        pending: "border-amber-200 bg-amber-50 text-amber-700",
        approved: "border-emerald-200 bg-emerald-50 text-emerald-700",
        rejected: "border-red-200 bg-red-50 text-red-700",
    };

    const labels = {
        pending: "Pending",
        approved: "Approved",
        rejected: "Rejected",
    };

    const icons = {
        pending: <Clock3 size={13} />,
        approved: <CheckCircle2 size={13} />,
        rejected: <XCircle size={13} />,
    };

    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${styles[decision] || styles.pending
                }`}
        >
            {icons[decision] || icons.pending}
            {labels[decision] || "Pending"}
        </span>
    );
}

function EmptyState({ search, decision }) {
    const messages = {
        pending: "All flagged questions have been reviewed.",
        approved: "No approved questions found.",
        rejected: "No rejected questions found.",
    };

    return (
        <div className="flex flex-col items-center px-5 py-16 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-lavender-light text-deep-purple">
                <CheckCircle2 size={29} />
            </div>

            <h3 className="mt-5 text-lg font-bold text-navy">
                {search ? "No matching questions" : "Nothing to review"}
            </h3>

            <p className="mt-2 max-w-md text-sm leading-relaxed text-navy/55">
                {search
                    ? "Try changing your search."
                    : messages[decision] || "No review records are available."}
            </p>
        </div>
    );
}

function ReviewCard({ item, selected, onSelect }) {
    const questionText =
        item.question?.en ||
        item.question?.hi ||
        "Question text unavailable";

    return (
        <button
            type="button"
            onClick={() => onSelect(item)}
            className={`w-full rounded-2xl border p-5 text-left transition ${selected
                ? "border-deep-purple bg-lavender-light/50 shadow-sm"
                : "border-lavender/70 bg-white hover:border-deep-purple/40 hover:bg-lavender-light/20"
                }`}
        >
            <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-pink-light px-3 py-1 text-xs font-semibold text-brand-pink">
                    Q{item.question_number ?? "?"}
                </span>

                {item.question_type && (
                    <span className="rounded-full bg-lavender px-3 py-1 text-xs font-semibold text-deep-purple">
                        {item.question_type}
                    </span>
                )}

                <DecisionBadge decision={item.review_decision || "pending"} />
            </div>

            <p className="mt-4 line-clamp-3 whitespace-pre-wrap text-sm font-medium leading-relaxed text-navy">
                {questionText}
            </p>

            {item.question?.hi && item.question?.en && (
                <p
                    lang="hi"
                    className="mt-2 line-clamp-2 text-sm text-navy/65"
                >
                    {item.question.hi}
                </p>
            )}

            {item.review_reasons?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                    {item.review_reasons.slice(0, 2).map((reason, index) => (
                        <span
                            key={`${index}-${reason}`}
                            className="rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-800"
                        >
                            {reason}
                        </span>
                    ))}
                    {item.review_reasons.length > 2 && (
                        <span className="rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-800">
                            +{item.review_reasons.length - 2} more
                        </span>
                    )}
                </div>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-lavender/60 pt-3 text-xs text-navy/50">
                <span className="max-w-[70%] truncate">
                    {item.source_filename || "Source unavailable"}
                </span>
                <span>{item.section_name || "Unassigned section"}</span>
            </div>
        </button>
    );
}

export default function Review() {
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const [decision, setDecision] = useState("pending");
    const [page, setPage] = useState(1);
    const [selectedQuestion, setSelectedQuestion] = useState(null);
    const [note, setNote] = useState("");

    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    useEffect(() => {
        const timer = window.setTimeout(() => {
            setDebouncedSearch(search.trim());
        }, 300);

        return () => window.clearTimeout(timer);
    }, [search]);

    const loadQuestions = useCallback(
        async (signal, isRefresh = false) => {
            if (isRefresh) {
                setRefreshing(true);
            } else {
                setLoading(true);
            }

            setError("");

            try {
                const response = await getReviewQuestions({
                    search: debouncedSearch,
                    decision,
                    limit: PAGE_SIZE,
                    offset: (page - 1) * PAGE_SIZE,
                    signal,
                });

                setItems(response.items ?? []);
                setTotal(response.total ?? 0);

                setSelectedQuestion((current) => {
                    if (!current) return null;

                    return (
                        response.items?.find(
                            (item) =>
                                item.question_id === current.question_id &&
                                item.conversion_id === current.conversion_id
                        ) ?? null
                    );
                });
            } catch (err) {
                if (err.name !== "AbortError") {
                    setError(err.message || "Unable to load review questions.");
                }
            } finally {
                if (!signal?.aborted) {
                    setLoading(false);
                    setRefreshing(false);
                }
            }
        },
        [debouncedSearch, decision, page]
    );

    useEffect(() => {
        const controller = new AbortController();

        loadQuestions(controller.signal);

        return () => controller.abort();
    }, [loadQuestions]);

    useEffect(() => {
        setPage(1);
        setSelectedQuestion(null);
        setNote("");
        setSuccess("");
    }, [debouncedSearch, decision]);

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const selectedResult = useMemo(() => {
        if (!selectedQuestion) return null;

        return {
            document: {
                title: selectedQuestion.source_filename || "Review question",
            },
            sections: [
                {
                    section_name: selectedQuestion.section_name || "",
                    questions: [selectedQuestion],
                },
            ],
        };
    }, [selectedQuestion]);

    function handleSelect(item) {
        setSelectedQuestion(item);
        setNote(item.review_note || "");
        setSuccess("");
    }

    async function handleDecision(nextDecision) {
        if (!selectedQuestion || saving) return;

        setSaving(true);
        setError("");
        setSuccess("");

        try {
            await updateReviewDecision(
                selectedQuestion.conversion_id,
                selectedQuestion.question_id,
                {
                    decision: nextDecision,
                    note,
                }
            );

            setSuccess(
                nextDecision === "approved"
                    ? "Question approved successfully."
                    : "Question rejected successfully."
            );

            setSelectedQuestion(null);
            setNote("");

            const controller = new AbortController();
            await loadQuestions(controller.signal, true);
        } catch (err) {
            setError(err.message || "Unable to save the review decision.");
        } finally {
            setSaving(false);
        }
    }

    function handleRefresh() {
        const controller = new AbortController();
        loadQuestions(controller.signal, true);
    }

    return (
        <div className="space-y-6">
            <section className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-navy">
                        Review Content
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-navy/60">
                        Inspect extracted questions, verify their content, and
                        record approval or rejection decisions.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={handleRefresh}
                    disabled={loading || refreshing || saving}
                    className="inline-flex items-center gap-2 rounded-xl border border-lavender bg-white px-4 py-2.5 text-sm font-semibold text-deep-purple transition hover:bg-lavender-light disabled:cursor-not-allowed disabled:opacity-60"
                >
                    <RefreshCw
                        size={16}
                        className={refreshing ? "animate-spin" : ""}
                    />
                    Refresh
                </button>
            </section>

            <section className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-2xl border border-lavender/70 bg-white p-5">
                    <p className="text-sm font-medium text-navy/55">
                        Matching records
                    </p>
                    <p className="mt-2 text-3xl font-bold text-navy">
                        {total}
                    </p>
                </div>

                <div className="rounded-2xl border border-lavender/70 bg-white p-5">
                    <p className="text-sm font-medium text-navy/55">
                        Loaded on this page
                    </p>
                    <p className="mt-2 text-3xl font-bold text-deep-purple">
                        {items.length}
                    </p>
                </div>

                <div className="rounded-2xl border border-lavender/70 bg-white p-5">
                    <p className="text-sm font-medium text-navy/55">
                        Current view
                    </p>
                    <p className="mt-2 text-lg font-bold text-navy">
                        {DECISIONS.find((item) => item.value === decision)?.label}
                    </p>
                </div>
            </section>

            <section className="overflow-hidden rounded-2xl border border-lavender/70 bg-white shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)]">
                <div className="border-b border-lavender/70 p-4 sm:p-5">
                    <div className="mb-4">
                        <h3 className="font-bold text-navy">
                            Review Queue
                        </h3>
                        <p className="mt-1 text-xs text-navy/50">
                            {total} matching review records
                        </p>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                        <div className="relative">
                            <Search
                                size={17}
                                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-navy/40"
                            />
                            <input
                                type="search"
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search questions or documents..."
                                className="w-full rounded-xl border border-lavender bg-white py-2.5 pl-10 pr-3 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple"
                            />
                        </div>

                        <select
                            value={decision}
                            onChange={(event) => setDecision(event.target.value)}
                            className="rounded-xl border border-lavender bg-white px-3 py-2.5 text-sm text-navy outline-none focus:border-deep-purple"
                        >
                            {DECISIONS.map((item) => (
                                <option key={item.value} value={item.value}>
                                    {item.label}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>

                {error && (
                    <div
                        className="m-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
                        role="alert"
                    >
                        <AlertCircle size={18} className="mt-0.5 shrink-0" />
                        <div className="flex-1">{error}</div>
                        <button
                            type="button"
                            onClick={handleRefresh}
                            className="font-semibold underline"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {success && (
                    <div
                        className="m-5 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700"
                        role="status"
                    >
                        <CheckCircle2 size={18} />
                        {success}
                    </div>
                )}

                {loading ? (
                    <div className="flex min-h-64 items-center justify-center gap-3 text-sm font-medium text-navy/55">
                        <LoaderCircle size={21} className="animate-spin" />
                        Loading review queue...
                    </div>
                ) : items.length === 0 ? (
                    <EmptyState
                        search={Boolean(search)}
                        decision={decision}
                    />
                ) : (
                    <>
                        <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-2">
                            {items.map((item, index) => (
                                <ReviewCard
                                    key={`${item.conversion_id}-${item.question_id ?? index}`}
                                    item={item}
                                    selected={
                                        selectedQuestion?.question_id === item.question_id &&
                                        selectedQuestion?.conversion_id === item.conversion_id
                                    }
                                    onSelect={handleSelect}
                                />
                            ))}
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-lavender/70 px-5 py-4">
                            <p className="text-xs text-navy/55">
                                Showing {(page - 1) * PAGE_SIZE + 1}–
                                {Math.min(page * PAGE_SIZE, total)} of {total}
                            </p>

                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    disabled={page === 1 || loading}
                                    onClick={() => setPage((value) => value - 1)}
                                    className="rounded-lg border border-lavender p-2 text-deep-purple disabled:cursor-not-allowed disabled:opacity-40"
                                    aria-label="Previous page"
                                >
                                    <ChevronLeft size={17} />
                                </button>

                                <span className="px-2 text-xs font-semibold text-navy/65">
                                    {page} / {totalPages}
                                </span>

                                <button
                                    type="button"
                                    disabled={page >= totalPages || loading}
                                    onClick={() => setPage((value) => value + 1)}
                                    className="rounded-lg border border-lavender p-2 text-deep-purple disabled:cursor-not-allowed disabled:opacity-40"
                                    aria-label="Next page"
                                >
                                    <ChevronRight size={17} />
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </section>

            {selectedQuestion && selectedResult && (
                <section className="rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-7">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <h3 className="text-lg font-bold text-navy">
                                Review Question
                            </h3>
                            <p className="mt-1 text-sm text-navy/55">
                                {selectedQuestion.source_filename || "Source unavailable"}
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={() => setSelectedQuestion(null)}
                            disabled={saving}
                            className="rounded-lg border border-lavender p-2 text-deep-purple transition hover:bg-lavender-light disabled:opacity-50"
                            aria-label="Close review details"
                        >
                            <X size={17} />
                        </button>
                    </div>

                    <div className="mt-5">
                        <QuestionPreview
                            result={selectedResult}
                            conversionId={selectedQuestion.conversion_id}
                        />
                    </div>

                    <div className="mt-6 rounded-2xl border border-lavender/70 bg-lavender-light/20 p-4 sm:p-5">
                        <label
                            htmlFor="review-note"
                            className="block text-sm font-semibold text-navy"
                        >
                            Reviewer note
                        </label>

                        <textarea
                            id="review-note"
                            rows={3}
                            maxLength={2000}
                            value={note}
                            onChange={(event) => setNote(event.target.value)}
                            placeholder="Add a note about this review decision (optional)..."
                            disabled={saving}
                            className="mt-2 w-full resize-y rounded-xl border border-lavender bg-white px-3 py-3 text-sm text-navy outline-none placeholder:text-navy/35 focus:border-deep-purple disabled:bg-slate-50"
                        />

                        <p className="mt-1 text-right text-xs text-navy/40">
                            {note.length}/2000
                        </p>

                        <div className="mt-4 flex flex-wrap justify-end gap-3">
                            <button
                                type="button"
                                onClick={() => handleDecision("rejected")}
                                disabled={saving}
                                className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-white px-5 py-2.5 text-sm font-semibold text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {saving ? (
                                    <LoaderCircle size={16} className="animate-spin" />
                                ) : (
                                    <XCircle size={16} />
                                )}
                                Reject
                            </button>

                            <button
                                type="button"
                                onClick={() => handleDecision("approved")}
                                disabled={saving}
                                className="inline-flex items-center gap-2 rounded-xl bg-deep-purple px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-navy disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {saving ? (
                                    <LoaderCircle size={16} className="animate-spin" />
                                ) : (
                                    <CheckCircle2 size={16} />
                                )}
                                Approve
                            </button>
                        </div>
                    </div>
                </section>
            )}
        </div>
    );
}
