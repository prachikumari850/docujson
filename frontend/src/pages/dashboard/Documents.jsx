
import { useEffect, useMemo, useState } from "react";
import {
    AlertCircle,
    CheckCircle2,
    Clock3,
    Download,
    Eye,
    FileText,
    LoaderCircle,
    RefreshCw,
    Search,
    Trash2,
    XCircle,
} from "lucide-react";

import DownloadActions from "../../components/DownloadActions";
import QuestionPreview from "../../components/QuestionPreview";
import {
    deleteConversion,
    downloadFile,
    getConversion,
    getDocuments,
    jsonUrl,
    zipUrl,
} from "../../services/converterApi";

const PAGE_SIZE = 10;
const MAX_LIST_SIZE = 100;

const STATUS_OPTIONS = [
    { value: "all", label: "All statuses" },
    { value: "completed", label: "Completed" },
    { value: "processing", label: "Processing" },
    { value: "queued", label: "Queued" },
    { value: "failed", label: "Failed" },
];

const STATUS_STYLES = {
    completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    processing: "bg-sky-50 text-sky-700 border-sky-200",
    queued: "bg-amber-50 text-amber-700 border-amber-200",
    failed: "bg-red-50 text-red-700 border-red-200",
};

function StatusBadge({ status }) {
    const styles =
        STATUS_STYLES[status] ??
        "bg-gray-100 text-gray-700 border-gray-200";

    const Icon =
        status === "completed"
            ? CheckCircle2
            : status === "failed"
                ? XCircle
                : status === "processing"
                    ? LoaderCircle
                    : Clock3;

    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold capitalize ${styles}`}
        >
            <Icon
                size={13}
                className={status === "processing" ? "animate-spin" : ""}
            />
            {status || "Unknown"}
        </span>
    );
}

function EmptyState({ searching }) {
    return (
        <div className="flex flex-col items-center px-5 py-14 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-lavender-light text-deep-purple">
                <FileText size={29} />
            </div>

            <h3 className="mt-5 text-lg font-bold text-navy">
                {searching ? "No matching documents" : "No documents yet"}
            </h3>

            <p className="mt-2 max-w-md text-sm leading-relaxed text-navy/55">
                {searching
                    ? "Try changing your search or status filter."
                    : "Documents uploaded through the Imports page will appear here."}
            </p>
        </div>
    );
}

export default function Documents() {
    const [documents, setDocuments] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [page, setPage] = useState(1);
    const [selectedDocument, setSelectedDocument] = useState(null);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [previewError, setPreviewError] = useState("");
    const [downloading, setDownloading] = useState(null);
    const [downloadError, setDownloadError] = useState("");
    const [deletingId, setDeletingId] = useState(null);
    const [actionError, setActionError] = useState("");

    async function loadDocuments(isRefresh = false) {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }

        setError("");

        try {
            const response = await getDocuments({
                limit: MAX_LIST_SIZE,
                offset: 0,
            });

            setDocuments(response.items ?? []);
            setTotal(response.total ?? 0);
        } catch (err) {
            setError(err.message || "Unable to load documents.");
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }

    useEffect(() => {
        loadDocuments();
    }, []);

    const filteredDocuments = useMemo(() => {
        const normalizedSearch = search.trim().toLowerCase();

        return documents.filter((document) => {
            const matchesSearch =
                !normalizedSearch ||
                (document.filename ?? "").toLowerCase().includes(normalizedSearch) ||
                (document.conversion_id ?? "").toLowerCase().includes(normalizedSearch);

            const matchesStatus =
                statusFilter === "all" ||
                document.status === statusFilter;

            return matchesSearch && matchesStatus;
        });
    }, [documents, search, statusFilter]);

    const totalPages = Math.max(
        1,
        Math.ceil(filteredDocuments.length / PAGE_SIZE)
    );

    const currentPage = Math.min(page, totalPages);

    const visibleDocuments = filteredDocuments.slice(
        (currentPage - 1) * PAGE_SIZE,
        currentPage * PAGE_SIZE
    );

    useEffect(() => {
        setPage(1);
    }, [search, statusFilter]);

    async function handleView(document) {
        setSelectedDocument(null);
        setPreviewError("");
        setPreviewLoading(true);
        setDownloadError("");
        setActionError("");

        try {
            const response = await getConversion(document.conversion_id);

            setSelectedDocument({
                ...document,
                result: response.result ?? null,
                status: response.status,
                progress: response.progress,
                stage: response.stage,
                error: response.error,
            });
        } catch (err) {
            setPreviewError(err.message || "Unable to load document details.");
        } finally {
            setPreviewLoading(false);
        }
    }

    async function handleDownload(kind) {
        if (!selectedDocument) return;

        setDownloading(kind);
        setDownloadError("");

        try {
            const isJson = kind === "json";

            await downloadFile(
                isJson
                    ? jsonUrl(selectedDocument.conversion_id)
                    : zipUrl(selectedDocument.conversion_id),
                isJson
                    ? "document.json"
                    : "document_with_media.zip"
            );
        } catch (err) {
            setDownloadError(err.message || "Download failed.");
        } finally {
            setDownloading(null);
        }
    }

    async function handleDelete(document) {
        const confirmed = window.confirm(
            `Delete "${document.filename || "this document"}"? This will permanently remove its conversion files and extracted media from local storage.`
        );

        if (!confirmed) return;

        setDeletingId(document.conversion_id);
        setActionError("");

        try {
            await deleteConversion(document.conversion_id);

            setDocuments((current) =>
                current.filter(
                    (item) => item.conversion_id !== document.conversion_id
                )
            );

            setTotal((current) => Math.max(0, current - 1));

            if (
                selectedDocument?.conversion_id === document.conversion_id
            ) {
                setSelectedDocument(null);
            }
        } catch (err) {
            setActionError(err.message || "Unable to delete document.");
        } finally {
            setDeletingId(null);
        }
    }

    return (
        <div className="space-y-6">
            <section className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-navy">
                        Document Library
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-relaxed text-navy/60">
                        Browse uploaded documents, track extraction progress,
                        preview extracted questions, and download results.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => loadDocuments(true)}
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
                        Total documents
                    </p>
                    <p className="mt-2 text-3xl font-bold text-navy">
                        {total}
                    </p>
                </div>

                <div className="rounded-2xl border border-lavender/70 bg-white p-5">
                    <p className="text-sm font-medium text-navy/55">
                        Completed
                    </p>
                    <p className="mt-2 text-3xl font-bold text-emerald-600">
                        {documents.filter((item) => item.status === "completed").length}
                    </p>
                </div>

                <div className="rounded-2xl border border-lavender/70 bg-white p-5">
                    <p className="text-sm font-medium text-navy/55">
                        In progress
                    </p>
                    <p className="mt-2 text-3xl font-bold text-sky-600">
                        {documents.filter((item) =>
                            ["queued", "processing"].includes(item.status)
                        ).length}
                    </p>
                </div>
            </section>

            <section className="overflow-hidden rounded-2xl border border-lavender/70 bg-white shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)]">
                <div className="flex flex-col gap-3 border-b border-lavender/70 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
                    <div>
                        <h3 className="font-bold text-navy">
                            All Documents
                        </h3>
                        <p className="mt-1 text-xs text-navy/50">
                            {filteredDocuments.length} matching records
                        </p>
                    </div>

                    <div className="flex flex-col gap-3 sm:flex-row">
                        <div className="relative">
                            <Search
                                size={17}
                                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-navy/40"
                            />
                            <input
                                type="search"
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search filename or ID"
                                className="w-full rounded-xl border border-lavender bg-white py-2.5 pl-10 pr-3 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple sm:w-64"
                            />
                        </div>

                        <select
                            value={statusFilter}
                            onChange={(event) => setStatusFilter(event.target.value)}
                            className="rounded-xl border border-lavender bg-white px-3 py-2.5 text-sm text-navy outline-none focus:border-deep-purple"
                        >
                            {STATUS_OPTIONS.map((option) => (
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
                            onClick={() => loadDocuments()}
                            className="font-semibold underline"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {actionError && (
                    <p className="mx-5 mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">
                        {actionError}
                    </p>
                )}

                {loading ? (
                    <div className="flex min-h-64 items-center justify-center gap-3 text-sm font-medium text-navy/55">
                        <LoaderCircle size={21} className="animate-spin" />
                        Loading documents...
                    </div>
                ) : visibleDocuments.length === 0 ? (
                    <EmptyState searching={Boolean(search || statusFilter !== "all")} />
                ) : (
                    <>
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[850px] text-left">
                                <thead className="bg-lavender-light/60 text-xs uppercase tracking-wide text-navy/55">
                                    <tr>
                                        <th className="px-5 py-4 font-semibold">Document</th>
                                        <th className="px-5 py-4 font-semibold">Format</th>
                                        <th className="px-5 py-4 font-semibold">Questions</th>
                                        <th className="px-5 py-4 font-semibold">Pages</th>
                                        <th className="px-5 py-4 font-semibold">Status</th>
                                        <th className="px-5 py-4 text-right font-semibold">Actions</th>
                                    </tr>
                                </thead>

                                <tbody className="divide-y divide-lavender/60">
                                    {visibleDocuments.map((document) => (
                                        <tr
                                            key={document.conversion_id}
                                            className="transition hover:bg-lavender-light/30"
                                        >
                                            <td className="max-w-[280px] px-5 py-4">
                                                <div className="flex items-center gap-3">
                                                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-pink-light text-brand-pink">
                                                        <FileText size={19} />
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="truncate text-sm font-semibold text-navy">
                                                            {document.filename || "Filename unavailable"}
                                                        </p>
                                                        <p className="mt-1 truncate text-xs text-navy/45">
                                                            {document.conversion_id}
                                                        </p>
                                                    </div>
                                                </div>
                                            </td>

                                            <td className="px-5 py-4 text-sm uppercase text-navy/65">
                                                {document.format || "—"}
                                            </td>

                                            <td className="px-5 py-4 text-sm text-navy/70">
                                                {document.total_questions ?? "—"}
                                            </td>

                                            <td className="px-5 py-4 text-sm text-navy/70">
                                                {document.total_pages ?? "—"}
                                            </td>

                                            <td className="px-5 py-4">
                                                <div className="space-y-1.5">
                                                    <StatusBadge status={document.status} />
                                                    {["queued", "processing"].includes(document.status) && (
                                                        <p className="text-xs text-navy/50">
                                                            {document.progress ?? 0}% · {document.stage || "Waiting"}
                                                        </p>
                                                    )}
                                                </div>
                                            </td>

                                            <td className="px-5 py-4">
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleView(document)}
                                                        title="View document"
                                                        className="rounded-lg border border-lavender p-2 text-deep-purple transition hover:bg-lavender-light"
                                                    >
                                                        <Eye size={16} />
                                                    </button>

                                                    {document.status === "completed" && (
                                                        <button
                                                            type="button"
                                                            onClick={() => downloadFile(
                                                                jsonUrl(document.conversion_id),
                                                                "document.json"
                                                            ).catch((err) => setActionError(err.message))}
                                                            title="Download JSON"
                                                            className="rounded-lg border border-lavender p-2 text-deep-purple transition hover:bg-lavender-light"
                                                        >
                                                            <Download size={16} />
                                                        </button>
                                                    )}

                                                    <button
                                                        type="button"
                                                        onClick={() => handleDelete(document)}
                                                        disabled={deletingId === document.conversion_id}
                                                        title="Delete document"
                                                        className="rounded-lg border border-red-100 p-2 text-red-600 transition hover:bg-red-50 disabled:opacity-50"
                                                    >
                                                        {deletingId === document.conversion_id ? (
                                                            <LoaderCircle size={16} className="animate-spin" />
                                                        ) : (
                                                            <Trash2 size={16} />
                                                        )}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-lavender/70 px-5 py-4">
                            <p className="text-xs text-navy/55">
                                Showing{" "}
                                {(currentPage - 1) * PAGE_SIZE + 1}–{" "}
                                {Math.min(currentPage * PAGE_SIZE, filteredDocuments.length)}{" "}
                                of {filteredDocuments.length}
                            </p>

                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    disabled={currentPage === 1}
                                    onClick={() => setPage((value) => value - 1)}
                                    className="rounded-lg border border-lavender px-3 py-2 text-xs font-semibold text-deep-purple disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                    Previous
                                </button>

                                <span className="px-2 text-xs font-semibold text-navy/65">
                                    {currentPage} / {totalPages}
                                </span>

                                <button
                                    type="button"
                                    disabled={currentPage === totalPages}
                                    onClick={() => setPage((value) => value + 1)}
                                    className="rounded-lg border border-lavender px-3 py-2 text-xs font-semibold text-deep-purple disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                    Next
                                </button>
                            </div>
                        </div>

                        {total > documents.length && (
                            <p className="border-t border-amber-200 bg-amber-50 px-5 py-3 text-xs text-amber-800">
                                Showing the latest {documents.length} of {total} records. Refine the listing with server-side filters when the library grows beyond this limit.
                            </p>
                        )}
                    </>
                )}
            </section>

            {(previewLoading || previewError || selectedDocument) && (
                <section className="scroll-mt-6 rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-7">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <h3 className="text-lg font-bold text-navy">
                                Document Details
                            </h3>
                            <p className="mt-1 text-sm text-navy/55">
                                {selectedDocument?.filename || "Loading document details"}
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={() => {
                                setSelectedDocument(null);
                                setPreviewError("");
                                setDownloadError("");
                            }}
                            className="rounded-lg border border-lavender px-3 py-2 text-xs font-semibold text-deep-purple hover:bg-lavender-light"
                        >
                            Close
                        </button>
                    </div>

                    {previewLoading && (
                        <div className="flex items-center justify-center gap-3 py-12 text-sm text-navy/55">
                            <LoaderCircle size={20} className="animate-spin" />
                            Loading document details...
                        </div>
                    )}

                    {previewError && (
                        <p className="mt-5 rounded-xl bg-red-50 p-4 text-sm text-red-700" role="alert">
                            {previewError}
                        </p>
                    )}

                    {selectedDocument && !previewLoading && (
                        <>
                            {selectedDocument.status === "completed" && selectedDocument.result ? (
                                <>
                                    <DownloadActions
                                        enabled
                                        downloading={downloading}
                                        error={downloadError}
                                        onDownload={handleDownload}
                                    />

                                    <QuestionPreview
                                        result={selectedDocument.result}
                                        conversionId={selectedDocument.conversion_id}
                                    />
                                </>
                            ) : selectedDocument.status === "failed" ? (
                                <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                                    <p className="font-semibold">Processing failed</p>
                                    <p className="mt-1">
                                        {selectedDocument.error || "The document could not be processed."}
                                    </p>
                                </div>
                            ) : (
                                <div className="mt-5 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-800">
                                    <p className="font-semibold">Document is still processing</p>
                                    <p className="mt-1">
                                        {selectedDocument.stage || "Waiting for processing"} · {selectedDocument.progress ?? 0}%
                                    </p>
                                    <p className="mt-2">
                                        Refresh the document list to check its latest status.
                                    </p>
                                </div>
                            )}
                        </>
                    )}
                </section>
            )}
        </div>
    );
}
