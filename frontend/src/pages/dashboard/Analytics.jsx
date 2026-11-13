
import { useCallback, useEffect, useState } from "react";
import {
    AlertCircle,
    BookOpen,
    CheckCircle2,
    Clock3,
    FileText,
    RefreshCw,
    ShieldCheck,
    Upload,
    XCircle,
} from "lucide-react";

import { getAnalyticsOverview } from "../../services/converterApi";

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function percentage(value, total) {
    if (!total) return 0;
    return Math.round((value / total) * 100);
}

function StatusBadge({ status }) {
    const styles = {
        completed: "bg-emerald-50 text-emerald-700",
        processing: "bg-sky-50 text-sky-700",
        queued: "bg-amber-50 text-amber-700",
        failed: "bg-red-50 text-red-700",
    };

    return (
        <span
            className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold capitalize ${styles[status] || "bg-gray-100 text-gray-600"
                }`}
        >
            {status || "Unknown"}
        </span>
    );
}

function MetricCard({ title, value, description, icon: Icon, color }) {
    return (
        <div className="rounded-2xl border border-lavender/60 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-sm font-medium text-navy/55">
                        {title}
                    </p>

                    <h3 className="mt-3 text-3xl font-bold text-navy">
                        {formatNumber(value)}
                    </h3>

                    <p className="mt-2 text-xs text-navy/45">
                        {description}
                    </p>
                </div>

                <div
                    className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${color}`}
                >
                    <Icon size={21} />
                </div>
            </div>
        </div>
    );
}

function Panel({ title, description, children }) {
    return (
        <section className="rounded-2xl border border-lavender/60 bg-white p-5 shadow-sm sm:p-6">
            <div className="mb-5">
                <h3 className="text-base font-bold text-navy">
                    {title}
                </h3>

                {description && (
                    <p className="mt-1 text-xs text-navy/50">
                        {description}
                    </p>
                )}
            </div>

            {children}
        </section>
    );
}

function ProgressRow({ label, value, total, color = "bg-deep-purple" }) {
    const progress = percentage(value, total);

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-navy/75">
                    {label}
                </span>

                <span className="shrink-0 font-semibold text-navy">
                    {formatNumber(value)}
                    <span className="ml-2 text-xs font-normal text-navy/45">
                        {progress}%
                    </span>
                </span>
            </div>

            <div className="h-2 overflow-hidden rounded-full bg-lavender-light">
                <div
                    className={`h-full rounded-full transition-all ${color}`}
                    style={{ width: `${progress}%` }}
                />
            </div>
        </div>
    );
}

function DistributionRow({ label, value, total, color }) {
    const progress = percentage(value, total);

    return (
        <div className="flex items-center gap-3">
            <div className={`h-2.5 w-2.5 shrink-0 rounded-full ${color}`} />

            <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate capitalize text-navy/70">
                        {label.replaceAll("_", " ")}
                    </span>

                    <span className="font-semibold text-navy">
                        {formatNumber(value)}
                    </span>
                </div>

                <div className="mt-2 h-2 overflow-hidden rounded-full bg-lavender-light">
                    <div
                        className={`h-full rounded-full ${color}`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            </div>
        </div>
    );
}

function EmptyState() {
    return (
        <div className="py-10 text-center">
            <FileText className="mx-auto text-navy/25" size={35} />

            <p className="mt-3 text-sm font-semibold text-navy">
                No document activity available
            </p>

            <p className="mt-1 text-xs text-navy/50">
                Uploaded documents will appear here.
            </p>
        </div>
    );
}

export default function Analytics() {
    const [analytics, setAnalytics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const loadAnalytics = useCallback(async (signal, isRefresh = false) => {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }

        setError("");

        try {
            const response = await getAnalyticsOverview(signal);
            setAnalytics(response);
        } catch (err) {
            if (err.name !== "AbortError") {
                setError(err.message || "Unable to load analytics.");
            }
        } finally {
            if (!signal?.aborted) {
                setLoading(false);
                setRefreshing(false);
            }
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();

        loadAnalytics(controller.signal);

        return () => controller.abort();
    }, [loadAnalytics]);

    const handleRefresh = () => {
        loadAnalytics(undefined, true);
    };

    if (loading && !analytics) {
        return (
            <div className="flex min-h-[300px] items-center justify-center">
                <div className="h-9 w-9 animate-spin rounded-full border-4 border-lavender border-t-deep-purple" />
            </div>
        );
    }

    if (error && !analytics) {
        return (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-6">
                <div className="flex items-center gap-2 font-semibold text-red-700">
                    <AlertCircle size={19} />
                    Unable to load analytics
                </div>

                <p className="mt-2 text-sm text-red-600">{error}</p>

                <button
                    type="button"
                    onClick={handleRefresh}
                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
                >
                    <RefreshCw size={15} />
                    Try again
                </button>
            </div>
        );
    }

    if (!analytics) return null;

    const documents = analytics.documents || {};
    const documentStatus = documents.by_status || {};
    const questions = analytics.questions || {};
    const questionTypes = questions.by_type || {};
    const review = questions.review || {};
    const answerKeys = analytics.answer_keys || {};
    const answerKeyStatus = answerKeys.by_status || {};
    const answerKeyReview = answerKeys.review || {};
    const publishing = analytics.publishing || {};
    const recentDocuments = analytics.recent_documents || [];

    const documentStatuses = [
        { label: "Completed", value: documentStatus.completed, color: "bg-emerald-500" },
        { label: "Processing", value: documentStatus.processing, color: "bg-sky-500" },
        { label: "Queued", value: documentStatus.queued, color: "bg-amber-500" },
        { label: "Failed", value: documentStatus.failed, color: "bg-red-500" },
        { label: "Other", value: documentStatus.other, color: "bg-gray-400" },
    ];

    const answerStatuses = [
        { label: "Matched", value: answerKeyStatus.matched, color: "bg-emerald-500" },
        { label: "Unmatched", value: answerKeyStatus.unmatched, color: "bg-amber-500" },
        { label: "Ambiguous", value: answerKeyStatus.ambiguous, color: "bg-orange-500" },
        { label: "Duplicate", value: answerKeyStatus.duplicate, color: "bg-sky-500" },
        { label: "Conflicting", value: answerKeyStatus.conflicting, color: "bg-red-500" },
        { label: "Invalid", value: answerKeyStatus.invalid, color: "bg-gray-500" },
    ];

    const reviewStatuses = [
        { label: "Pending", value: review.pending, color: "bg-amber-500" },
        { label: "Approved", value: review.approved, color: "bg-emerald-500" },
        { label: "Rejected", value: review.rejected, color: "bg-red-500" },
    ];

    const answerReviewStatuses = [
        { label: "Pending", value: answerKeyReview.pending, color: "bg-amber-500" },
        { label: "Approved", value: answerKeyReview.approved, color: "bg-emerald-500" },
        { label: "Rejected", value: answerKeyReview.rejected, color: "bg-red-500" },
    ];

    return (
        <div className="space-y-6">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                <div>
                    <h2 className="text-xl font-bold text-navy sm:text-2xl">
                        Analytics Overview
                    </h2>

                    <p className="mt-1 text-sm text-navy/50">
                        Monitor document processing and content activity.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={handleRefresh}
                    disabled={refreshing}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-lavender px-4 py-2.5 text-sm font-semibold text-deep-purple transition hover:bg-lavender-light disabled:cursor-not-allowed disabled:opacity-60"
                >
                    <RefreshCw
                        size={16}
                        className={refreshing ? "animate-spin" : ""}
                    />
                    Refresh
                </button>
            </div>

            {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {error}
                </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                    title="Total Documents"
                    value={documents.total}
                    description={`${formatNumber(documentStatus.completed)} completed`}
                    icon={FileText}
                    color="bg-lavender-light text-deep-purple"
                />

                <MetricCard
                    title="Extracted Questions"
                    value={questions.total}
                    description={`${formatNumber(questionTypes.mcq)} MCQ questions`}
                    icon={BookOpen}
                    color="bg-sky-50 text-sky-700"
                />

                <MetricCard
                    title="Pending Reviews"
                    value={review.pending}
                    description="Questions awaiting review"
                    icon={Clock3}
                    color="bg-amber-50 text-amber-700"
                />

                <MetricCard
                    title="Answer Key Entries"
                    value={answerKeys.total}
                    description={`${formatNumber(answerKeyStatus.matched)} matched`}
                    icon={CheckCircle2}
                    color="bg-emerald-50 text-emerald-700"
                />
            </div>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
                <Panel
                    title="Document Processing"
                    description="Distribution of documents by processing status."
                >
                    <div className="space-y-5">
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                            {documentStatuses.slice(0, 4).map((item) => (
                                <div
                                    key={item.label}
                                    className="rounded-xl bg-lavender-light/60 p-3"
                                >
                                    <p className="text-xs text-navy/55">
                                        {item.label}
                                    </p>
                                    <p className="mt-1 text-xl font-bold text-navy">
                                        {formatNumber(item.value)}
                                    </p>
                                </div>
                            ))}
                        </div>

                        <div className="space-y-4">
                            {documentStatuses.map((item) => (
                                <ProgressRow
                                    key={item.label}
                                    {...item}
                                    total={documents.total}
                                />
                            ))}
                        </div>
                    </div>
                </Panel>

                <Panel
                    title="Question Distribution"
                    description="Extracted questions grouped by question type."
                >
                    <div className="space-y-5">
                        {Object.keys(questionTypes).length ? (
                            Object.entries(questionTypes).map(([type, count], index) => (
                                <DistributionRow
                                    key={type}
                                    label={type}
                                    value={count}
                                    total={questions.total}
                                    color={
                                        index % 2 === 0
                                            ? "bg-deep-purple"
                                            : "bg-brand-pink"
                                    }
                                />
                            ))
                        ) : (
                            <EmptyState />
                        )}
                    </div>
                </Panel>

                <Panel
                    title="Question Review"
                    description="Review decisions for questions flagged for review."
                >
                    <div className="space-y-5">
                        <div className="grid grid-cols-3 gap-3">
                            {reviewStatuses.map((item) => (
                                <div
                                    key={item.label}
                                    className="rounded-xl bg-lavender-light/60 p-3"
                                >
                                    <p className="text-xs text-navy/55">
                                        {item.label}
                                    </p>
                                    <p className="mt-1 text-xl font-bold text-navy">
                                        {formatNumber(item.value)}
                                    </p>
                                </div>
                            ))}
                        </div>

                        {reviewStatuses.map((item) => (
                            <ProgressRow
                                key={item.label}
                                {...item}
                                total={Object.values(review).reduce(
                                    (sum, value) => sum + Number(value || 0),
                                    0
                                )}
                            />
                        ))}
                    </div>
                </Panel>

                <Panel
                    title="Answer Key Analysis"
                    description="Matching status and reviewer decisions for answer-key entries."
                >
                    <div className="space-y-5">
                        <div className="grid grid-cols-2 gap-3">
                            <div className="rounded-xl bg-lavender-light/60 p-3">
                                <p className="text-xs text-navy/55">
                                    Total Entries
                                </p>
                                <p className="mt-1 text-xl font-bold text-navy">
                                    {formatNumber(answerKeys.total)}
                                </p>
                            </div>

                            <div className="rounded-xl bg-emerald-50 p-3">
                                <p className="text-xs text-emerald-700">
                                    Matched Entries
                                </p>
                                <p className="mt-1 text-xl font-bold text-emerald-800">
                                    {formatNumber(answerKeyStatus.matched)}
                                </p>
                            </div>
                        </div>

                        <div className="space-y-4">
                            {answerStatuses.map((item) => (
                                <ProgressRow
                                    key={item.label}
                                    {...item}
                                    total={answerKeys.total}
                                />
                            ))}
                        </div>

                        <div className="border-t border-lavender/60 pt-4">
                            <p className="mb-4 text-sm font-semibold text-navy">
                                Reviewer Decisions
                            </p>

                            {answerReviewStatuses.map((item) => (
                                <div key={item.label} className="mb-3">
                                    <ProgressRow
                                        {...item}
                                        total={Object.values(answerKeyReview).reduce(
                                            (sum, value) => sum + Number(value || 0),
                                            0
                                        )}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                </Panel>
            </div>

            <Panel
                title="Publishing Overview"
                description="Publication history and question totals across all published versions."
            >
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <MetricCard
                        title="Publication Versions"
                        value={publishing.versions}
                        description="Total versions created"
                        icon={Upload}
                        color="bg-lavender-light text-deep-purple"
                    />

                    <MetricCard
                        title="Published Questions"
                        value={publishing.published_questions}
                        description="Cumulative across versions"
                        icon={ShieldCheck}
                        color="bg-emerald-50 text-emerald-700"
                    />

                    <MetricCard
                        title="Excluded Questions"
                        value={publishing.excluded_questions}
                        description="Cumulative across versions"
                        icon={XCircle}
                        color="bg-red-50 text-red-700"
                    />
                </div>
            </Panel>

            <Panel
                title="Recent Documents"
                description="The latest 10 documents by modification time."
            >
                {recentDocuments.length === 0 ? (
                    <EmptyState />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full min-w-[650px] text-left">
                            <thead>
                                <tr className="border-b border-lavender/60 text-xs uppercase tracking-wide text-navy/45">
                                    <th className="px-3 py-3 font-semibold">
                                        Document
                                    </th>
                                    <th className="px-3 py-3 font-semibold">
                                        Format
                                    </th>
                                    <th className="px-3 py-3 font-semibold">
                                        Questions
                                    </th>
                                    <th className="px-3 py-3 font-semibold">
                                        Status
                                    </th>
                                </tr>
                            </thead>

                            <tbody>
                                {recentDocuments.map((document) => (
                                    <tr
                                        key={document.conversion_id}
                                        className="border-b border-lavender/40 last:border-0"
                                    >
                                        <td className="px-3 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-lavender-light text-deep-purple">
                                                    <FileText size={17} />
                                                </div>

                                                <span className="max-w-[280px] truncate text-sm font-semibold text-navy">
                                                    {document.filename}
                                                </span>
                                            </div>
                                        </td>

                                        <td className="px-3 py-4 text-sm uppercase text-navy/60">
                                            {document.format || "—"}
                                        </td>

                                        <td className="px-3 py-4 text-sm font-semibold text-navy">
                                            {formatNumber(document.total_questions)}
                                        </td>

                                        <td className="px-3 py-4">
                                            <StatusBadge status={document.status} />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}
