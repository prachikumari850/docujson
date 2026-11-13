
import { useCallback, useEffect, useState } from "react";
import {
    AlertCircle,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock3,
    FileText,
    LoaderCircle,
    RefreshCw,
    Search,
    XCircle,
} from "lucide-react";

import {
    getAnswerKeys,
    updateAnswerKeyDecision,
} from "../../services/converterApi";

const PAGE_SIZE = 25;

const STATUSES = [
    { value: "all", label: "All extraction statuses" },
    { value: "matched", label: "Matched" },
    { value: "unmatched", label: "Unmatched" },
    { value: "ambiguous", label: "Ambiguous" },
    { value: "duplicate", label: "Duplicate" },
    { value: "conflicting", label: "Conflicting" },
    { value: "invalid", label: "Invalid" },
];

const DECISIONS = [
    { value: "all", label: "All decisions" },
    { value: "pending", label: "Pending review" },
    { value: "approved", label: "Approved" },
    { value: "rejected", label: "Rejected" },
];

function ExtractionBadge({ status }) {
    const styles = {
        matched: "border-emerald-200 bg-emerald-50 text-emerald-700",
        unmatched: "border-amber-200 bg-amber-50 text-amber-700",
        ambiguous: "border-orange-200 bg-orange-50 text-orange-700",
        duplicate: "border-purple-200 bg-purple-50 text-purple-700",
        conflicting: "border-red-200 bg-red-50 text-red-700",
        invalid: "border-red-200 bg-red-50 text-red-700",
    };

    return (
        <span
            className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold capitalize ${styles[status] || "border-slate-200 bg-slate-50 text-slate-600"
                }`}
        >
            {status || "Unknown"}
        </span>
    );
}

function DecisionBadge({ decision }) {
    const styles = {
        pending: "border-amber-200 bg-amber-50 text-amber-700",
        approved: "border-emerald-200 bg-emerald-50 text-emerald-700",
        rejected: "border-red-200 bg-red-50 text-red-700",
    };

    const icons = {
        pending: <Clock3 size={13} />,
        approved: <CheckCircle2 size={13} />,
        rejected: <XCircle size={13} />,
    };

    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold capitalize ${styles[decision] || styles.pending
                }`}
        >
            {icons[decision] || icons.pending}
            {decision || "pending"}
        </span>
    );
}

function EmptyState({ search, status, decision }) {
    return (
        <div className="flex flex-col items-center px-5 py-16 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-lavender-light text-deep-purple">
                <FileText size={29} />
            </div>

            <h3 className="mt-5 text-lg font-bold text-navy">
                No answer-key entries found
            </h3>

            <p className="mt-2 max-w-md text-sm leading-relaxed text-navy/55">
                {search || status !== "all" || decision !== "all"
                    ? "Try changing your search or filters."
                    : "Answer keys will appear here after a document import is completed."}
            </p>
        </div>
    );
}

function SummaryCard({ label, value, color = "text-navy" }) {
    return (
        <div className="rounded-2xl border border-lavender/70 bg-white p-5">
            <p className="text-sm font-medium text-navy/55">{label}</p>
            <p className={`mt-2 text-3xl font-bold ${color}`}>{value}</p>
        </div>
    );
}

export default function AnswerKeys() {
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);

    const [search, setSearch] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const [status, setStatus] = useState("all");
    const [decision, setDecision] = useState("all");
    const [page, setPage] = useState(1);

    const [selectedEntry, setSelectedEntry] = useState(null);
    const [correctedAnswer, setCorrectedAnswer] = useState("");
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

    const loadEntries = useCallback(
        async (signal, isRefresh = false) => {
            if (isRefresh) {
                setRefreshing(true);
            } else {
                setLoading(true);
            }

            setError("");

            try {
                const response = await getAnswerKeys({
                    search: debouncedSearch,
                    status,
                    decision,
                    limit: PAGE_SIZE,
                    offset: (page - 1) * PAGE_SIZE,
                    signal,
                });

                setItems(response.items ?? []);
                setTotal(response.total ?? 0);

                setSelectedEntry((current) => {
                    if (!current) return null;

                    return (
                        response.items?.find(
                            (item) =>
                                item.entry_id === current.entry_id &&
                                item.conversion_id === current.conversion_id
                        ) ?? null
                    );
                });
            } catch (err) {
                if (err.name !== "AbortError") {
                    setError(
                        err.message || "Unable to load answer-key entries."
                    );
                }
            } finally {
                if (!signal?.aborted) {
                    setLoading(false);
                    setRefreshing(false);
                }
            }
        },
        [debouncedSearch, status, decision, page]
    );

    useEffect(() => {
        const controller = new AbortController();

        loadEntries(controller.signal);

        return () => controller.abort();
    }, [loadEntries]);

    useEffect(() => {
        setPage(1);
        setSelectedEntry(null);
        setCorrectedAnswer("");
        setNote("");
        setSuccess("");
    }, [debouncedSearch, status, decision]);

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const matchedCount = items.filter(
        (item) => item.status === "matched"
    ).length;

    const pendingCount = items.filter(
        (item) => (item.review_decision || "pending") === "pending"
    ).length;

    function handleSelect(item) {
        setSelectedEntry(item);
        setCorrectedAnswer(item.corrected_answer || "");
        setNote(item.review_note || "");
        setSuccess("");
    }

    async function handleDecision(nextDecision) {
        if (!selectedEntry || saving) return;

        setSaving(true);
        setError("");
        setSuccess("");

        try {
            await updateAnswerKeyDecision(
                selectedEntry.conversion_id,
                selectedEntry.entry_id,
                {
                    decision: nextDecision,
                    correctedAnswer:
                        nextDecision === "approved" ? correctedAnswer : "",
                    note,
                }
            );

            setSuccess(
                nextDecision === "approved"
                    ? "Answer-key entry approved successfully."
                    : "Answer-key entry rejected successfully."
            );

            setSelectedEntry(null);
            setCorrectedAnswer("");
            setNote("");

            const controller = new AbortController();
            await loadEntries(controller.signal, true);
        } catch (err) {
            setError(
                err.message || "Unable to save the answer-key decision."
            );
        } finally {
            setSaving(false);
        }
    }

    function handleRefresh() {
        const controller = new AbortController();
        loadEntries(controller.signal, true);
    }

    return (
        <div className="space-y-6">
            <section className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-navy">
                        Answer Keys
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-navy/60">
                        Inspect extracted answer keys, verify question
                        mappings, and record reviewer decisions.
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
                <SummaryCard
                    label="Matching entries"
                    value={total}
                />

                <SummaryCard
                    label="Matched on this page"
                    value={matchedCount}
                    color="text-emerald-700"
                />

                <SummaryCard
                    label="Pending on this page"
                    value={pendingCount}
                    color="text-amber-700"
                />
            </section>

            <section className="overflow-hidden rounded-2xl border border-lavender/70 bg-white shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)]">
                <div className="border-b border-lavender/70 p-4 sm:p-5">
                    <div className="mb-4">
                        <h3 className="font-bold text-navy">
                            Imported Answer-Key Entries
                        </h3>
                        <p className="mt-1 text-xs text-navy/50">
                            {total} matching entries
                        </p>
                    </div>

                    <div className="grid gap-3 md:grid-cols-3">
                        <div className="relative md:col-span-1">
                            <Search
                                size={17}
                                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-navy/40"
                            />
                            <input
                                type="search"
                                value={search}
                                onChange={(event) =>
                                    setSearch(event.target.value)
                                }
                                placeholder="Search answer keys..."
                                className="w-full rounded-xl border border-lavender bg-white py-2.5 pl-10 pr-3 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple"
                            />
                        </div>

                        <select
                            value={status}
                            onChange={(event) => setStatus(event.target.value)}
                            className="rounded-xl border border-lavender bg-white px-3 py-2.5 text-sm text-navy outline-none focus:border-deep-purple"
                        >
                            {STATUSES.map((item) => (
                                <option key={item.value} value={item.value}>
                                    {item.label}
                                </option>
                            ))}
                        </select>

                        <select
                            value={decision}
                            onChange={(event) =>
                                setDecision(event.target.value)
                            }
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
                        Loading answer keys...
                    </div>
                ) : items.length === 0 ? (
                    <EmptyState
                        search={Boolean(debouncedSearch)}
                        status={status}
                        decision={decision}
                    />
                ) : (
                    <>
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[850px] text-left">
                                <thead className="bg-lavender-light/50">
                                    <tr className="text-xs font-semibold uppercase tracking-wide text-navy/55">
                                        <th className="px-5 py-4">Question</th>
                                        <th className="px-5 py-4">Extracted answer</th>
                                        <th className="px-5 py-4">Extraction status</th>
                                        <th className="px-5 py-4">Review decision</th>
                                        <th className="px-5 py-4">Source</th>
                                        <th className="px-5 py-4">Action</th>
                                    </tr>
                                </thead>

                                <tbody className="divide-y divide-lavender/60">
                                    {items.map((item) => {
                                        const selected =
                                            selectedEntry?.entry_id === item.entry_id &&
                                            selectedEntry?.conversion_id === item.conversion_id;

                                        return (
                                            <tr
                                                key={`${item.conversion_id}-${item.entry_id}`}
                                                className={`transition ${selected
                                                        ? "bg-lavender-light/50"
                                                        : "hover:bg-lavender-light/20"
                                                    }`}
                                            >
                                                <td className="px-5 py-4">
                                                    <span className="font-semibold text-navy">
                                                        Q{item.question_number ?? "—"}
                                                    </span>
                                                </td>

                                                <td className="px-5 py-4">
                                                    <span className="font-semibold text-navy">
                                                        {item.answer || "—"}
                                                    </span>

                                                    {item.corrected_answer && (
                                                        <p className="mt-1 text-xs text-deep-purple">
                                                            Corrected: {item.corrected_answer}
                                                        </p>
                                                    )}
                                                </td>

                                                <td className="px-5 py-4">
                                                    <ExtractionBadge status={item.status} />
                                                </td>

                                                <td className="px-5 py-4">
                                                    <DecisionBadge
                                                        decision={item.review_decision || "pending"}
                                                    />
                                                </td>

                                                <td className="max-w-[200px] px-5 py-4">
                                                    <p
                                                        className="truncate text-sm text-navy/65"
                                                        title={item.source_filename}
                                                    >
                                                        {item.source_filename || "Unknown"}
                                                    </p>
                                                    <p className="mt-1 text-xs text-navy/40">
                                                        Page {item.page ?? "—"}
                                                    </p>
                                                </td>

                                                <td className="px-5 py-4">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleSelect(item)}
                                                        className="rounded-lg border border-lavender px-3 py-2 text-xs font-semibold text-deep-purple transition hover:bg-lavender-light"
                                                    >
                                                        Inspect
                                                    </button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
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

            {selectedEntry && (
                <section className="rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-7">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <h3 className="text-lg font-bold text-navy">
                                Inspect Answer-Key Entry
                            </h3>
                            <p className="mt-1 text-sm text-navy/55">
                                {selectedEntry.source_filename || "Source unavailable"}
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={() => setSelectedEntry(null)}
                            disabled={saving}
                            className="rounded-lg border border-lavender px-3 py-2 text-xs font-semibold text-deep-purple hover:bg-lavender-light disabled:opacity-50"
                        >
                            Close
                        </button>
                    </div>

                    <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        <div className="rounded-xl bg-lavender-light/50 p-4">
                            <p className="text-xs text-navy/50">Question number</p>
                            <p className="mt-1 font-bold text-navy">
                                {selectedEntry.question_number ?? "—"}
                            </p>
                        </div>

                        <div className="rounded-xl bg-lavender-light/50 p-4">
                            <p className="text-xs text-navy/50">Extracted answer</p>
                            <p className="mt-1 font-bold text-navy">
                                {selectedEntry.answer || "—"}
                            </p>
                        </div>

                        <div className="rounded-xl bg-lavender-light/50 p-4">
                            <p className="text-xs text-navy/50">Source page</p>
                            <p className="mt-1 font-bold text-navy">
                                {selectedEntry.page ?? "—"}
                            </p>
                        </div>

                        <div className="rounded-xl bg-lavender-light/50 p-4">
                            <p className="text-xs text-navy/50">Source format</p>
                            <p className="mt-1 font-bold capitalize text-navy">
                                {selectedEntry.source_format || "—"}
                            </p>
                        </div>
                    </div>

                    <div className="mt-5 flex flex-wrap items-center gap-3">
                        <div>
                            <p className="mb-2 text-xs font-semibold text-navy/55">
                                Extraction status
                            </p>
                            <ExtractionBadge status={selectedEntry.status} />
                        </div>

                        <div>
                            <p className="mb-2 text-xs font-semibold text-navy/55">
                                Review decision
                            </p>
                            <DecisionBadge
                                decision={selectedEntry.review_decision || "pending"}
                            />
                        </div>
                    </div>

                    {selectedEntry.matched_question_id && (
                        <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                            <p className="text-sm font-semibold text-emerald-800">
                                Matched question
                            </p>
                            <p className="mt-1 break-all text-xs text-emerald-700">
                                {selectedEntry.matched_question_id}
                            </p>
                        </div>
                    )}

                    {selectedEntry.candidate_question_ids?.length > 0 && (
                        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
                            <p className="text-sm font-semibold text-amber-800">
                                Candidate question matches
                            </p>
                            <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-amber-800">
                                {selectedEntry.candidate_question_ids.map((id) => (
                                    <li key={id} className="break-all">{id}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {selectedEntry.warnings?.length > 0 && (
                        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
                            <p className="text-sm font-semibold text-amber-800">
                                Extraction warnings
                            </p>
                            <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-amber-800">
                                {selectedEntry.warnings.map((warning, index) => (
                                    <li key={`${index}-${warning}`}>{warning}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="mt-6 rounded-2xl border border-lavender/70 bg-lavender-light/20 p-4 sm:p-5">
                        <h4 className="text-sm font-bold text-navy">
                            Reviewer decision
                        </h4>

                        <p className="mt-1 text-xs leading-relaxed text-navy/55">
                            The extracted answer remains unchanged. An approved
                            correction is stored separately for later publishing.
                        </p>

                        <label
                            htmlFor="corrected-answer"
                            className="mt-5 block text-sm font-semibold text-navy"
                        >
                            Corrected answer
                            <span className="ml-2 font-normal text-navy/45">
                                (optional)
                            </span>
                        </label>

                        <input
                            id="corrected-answer"
                            type="text"
                            maxLength={50}
                            value={correctedAnswer}
                            onChange={(event) =>
                                setCorrectedAnswer(event.target.value)
                            }
                            placeholder="Enter the verified answer..."
                            disabled={saving}
                            className="mt-2 w-full rounded-xl border border-lavender bg-white px-3 py-3 text-sm text-navy outline-none placeholder:text-navy/35 focus:border-deep-purple disabled:bg-slate-50"
                        />

                        <label
                            htmlFor="answer-key-note"
                            className="mt-5 block text-sm font-semibold text-navy"
                        >
                            Reviewer note
                        </label>

                        <textarea
                            id="answer-key-note"
                            rows={3}
                            maxLength={2000}
                            value={note}
                            onChange={(event) => setNote(event.target.value)}
                            placeholder="Add a note about this answer-key decision..."
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
