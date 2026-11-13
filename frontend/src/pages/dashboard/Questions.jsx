
import { useCallback, useEffect, useMemo, useState } from "react";
import {
    AlertCircle,
    BookOpen,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock3,
    LoaderCircle,
    RefreshCw,
    Search,
    TriangleAlert,
    X,
} from "lucide-react";

import QuestionPreview from "../../components/QuestionPreview";
import { getQuestions } from "../../services/converterApi";

const PAGE_SIZE = 25;

const REVIEW_OPTIONS = [
    { value: "", label: "All questions" },
    { value: "true", label: "Needs review" },
    { value: "false", label: "No review required" },
];

function QuestionStatus({ required }) {
    return required ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
            <TriangleAlert size={13} />
            Needs review
        </span>
    ) : (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
            <CheckCircle2 size={13} />
            No review required
        </span>
    );
}

function EmptyState({ searching }) {
    return (
        <div className="flex flex-col items-center px-5 py-14 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-lavender-light text-deep-purple">
                <BookOpen size={29} />
            </div>

            <h3 className="mt-5 text-lg font-bold text-navy">
                {searching ? "No matching questions" : "No questions available"}
            </h3>

            <p className="mt-2 max-w-md text-sm leading-relaxed text-navy/55">
                {searching
                    ? "Try changing your search or filters."
                    : "Questions extracted from completed documents will appear here."}
            </p>
        </div>
    );
}

function QuestionCard({ item, onSelect, selected }) {
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

                <QuestionStatus required={item.review_required} />
            </div>

            <p className="mt-4 line-clamp-3 whitespace-pre-wrap text-sm font-medium leading-relaxed text-navy">
                {questionText}
            </p>

            {item.question?.hi && item.question?.en && (
                <p lang="hi" className="mt-2 line-clamp-2 text-sm text-navy/65">
                    {item.question.hi}
                </p>
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

export default function Questions() {
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState("");
    const [questionType, setQuestionType] = useState("");
    const [reviewRequired, setReviewRequired] = useState("");
    const [page, setPage] = useState(1);
    const [selectedQuestion, setSelectedQuestion] = useState(null);

    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const [debouncedSearch, setDebouncedSearch] = useState("");

    useEffect(() => {
        const timer = window.setTimeout(() => {
            setDebouncedSearch(search.trim());
        }, 300);

        return () => window.clearTimeout(timer);
    }, [search]);

    const loadQuestions = useCallback(async (signal, isRefresh = false) => {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }

        setError("");

        try {
            const response = await getQuestions({
                search: debouncedSearch,
                questionType,
                reviewRequired,
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
                        (item) => item.question_id === current.question_id
                    ) ?? null
                );
            });
        } catch (err) {
            if (err.name !== "AbortError") {
                setError(err.message || "Unable to load questions.");
            }
        } finally {
            if (!signal?.aborted) {
                setLoading(false);
                setRefreshing(false);
            }
        }
    }, [debouncedSearch, questionType, reviewRequired, page]);

    useEffect(() => {
        const controller = new AbortController();

        loadQuestions(controller.signal);

        return () => controller.abort();
    }, [loadQuestions]);

    useEffect(() => {
        setPage(1);
        setSelectedQuestion(null);
    }, [debouncedSearch, questionType, reviewRequired]);

    const questionTypes = useMemo(() => {
        return [...new Set(
            items
                .map((item) => item.question_type)
                .filter(Boolean)
        )].sort();
    }, [items]);

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const reviewCount = items.filter(
        (item) => item.review_required
    ).length;

    const selectedResult = useMemo(() => {
        if (!selectedQuestion) return null;

        return {
            document: {
                title: selectedQuestion.source_filename || "Question details",
            },
            sections: [
                {
                    section_name: selectedQuestion.section_name || "",
                    questions: [selectedQuestion],
                },
            ],
        };
    }, [selectedQuestion]);

    function handleFilterChange(setter, value) {
        setter(value);
        setPage(1);
        setSelectedQuestion(null);
    }

    return (
        <div className="space-y-6">
            <section className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-navy">
                        Questions Library
                    </h2>

                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-navy/60">
                        Browse extracted questions, inspect their source documents,
                        and identify questions that need manual review.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => {
                        const controller = new AbortController();
                        loadQuestions(controller.signal, true);
                    }}
                    disabled={loading || refreshing}
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
                        Matching questions
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
                        Needs review on this page
                    </p>
                    <p className="mt-2 text-3xl font-bold text-amber-600">
                        {reviewCount}
                    </p>
                </div>
            </section>

            <section className="overflow-hidden rounded-2xl border border-lavender/70 bg-white shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)]">
                <div className="border-b border-lavender/70 p-4 sm:p-5">
                    <div className="mb-4">
                        <h3 className="font-bold text-navy">
                            Extracted Questions
                        </h3>
                        <p className="mt-1 text-xs text-navy/50">
                            {total} matching records
                        </p>
                    </div>

                    <div className="grid gap-3 md:grid-cols-3">
                        <div className="relative">
                            <Search
                                size={17}
                                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-navy/40"
                            />

                            <input
                                type="search"
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search questions..."
                                className="w-full rounded-xl border border-lavender bg-white py-2.5 pl-10 pr-3 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple"
                            />
                        </div>

                        <select
                            value={questionType}
                            onChange={(event) =>
                                handleFilterChange(setQuestionType, event.target.value)
                            }
                            className="rounded-xl border border-lavender bg-white px-3 py-2.5 text-sm text-navy outline-none focus:border-deep-purple"
                        >
                            <option value="">All question types</option>
                            {questionTypes.map((type) => (
                                <option key={type} value={type}>
                                    {type}
                                </option>
                            ))}
                        </select>

                        <select
                            value={reviewRequired}
                            onChange={(event) =>
                                handleFilterChange(setReviewRequired, event.target.value)
                            }
                            className="rounded-xl border border-lavender bg-white px-3 py-2.5 text-sm text-navy outline-none focus:border-deep-purple"
                        >
                            {REVIEW_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>
                                    {option.label}
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
                            onClick={() => {
                                const controller = new AbortController();
                                loadQuestions(controller.signal);
                            }}
                            className="font-semibold underline"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {loading ? (
                    <div className="flex min-h-64 items-center justify-center gap-3 text-sm font-medium text-navy/55">
                        <LoaderCircle size={21} className="animate-spin" />
                        Loading questions...
                    </div>
                ) : items.length === 0 ? (
                    <EmptyState
                        searching={Boolean(
                            search || questionType || reviewRequired
                        )}
                    />
                ) : (
                    <>
                        <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-2">
                            {items.map((item, index) => (
                                <QuestionCard
                                    key={`${item.conversion_id}-${item.question_id ?? index}`}
                                    item={item}
                                    selected={
                                        selectedQuestion?.question_id === item.question_id &&
                                        selectedQuestion?.conversion_id === item.conversion_id
                                    }
                                    onSelect={setSelectedQuestion}
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
                                Question Details
                            </h3>
                            <p className="mt-1 text-sm text-navy/55">
                                {selectedQuestion.source_filename || "Source unavailable"}
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={() => setSelectedQuestion(null)}
                            className="rounded-lg border border-lavender p-2 text-deep-purple transition hover:bg-lavender-light"
                            aria-label="Close question details"
                        >
                            <X size={17} />
                        </button>
                    </div>

                    <QuestionPreview
                        result={selectedResult}
                        conversionId={selectedQuestion.conversion_id}
                    />
                </section>
            )}
        </div>
    );
}
