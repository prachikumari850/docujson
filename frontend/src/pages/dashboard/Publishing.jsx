
import { useCallback, useEffect, useState } from "react";
import {
    AlertCircle,
    BookOpen,
    CheckCircle2,
    Clock,
    FileText,
    Loader2,
    RefreshCw,
    Upload,
    XCircle,
} from "lucide-react";

import {
    createPublication,
    getDocuments,
    getPublication,
    getPublications,
} from "../../services/converterApi";

const PAGE_SIZE = 100;

function formatDate(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "—";

    return date.toLocaleString();
}

function StatusBadge({ status }) {
    const styles = {
        completed: "bg-green-100 text-green-700",
        processing: "bg-blue-100 text-blue-700",
        failed: "bg-red-100 text-red-700",
    };

    return (
        <span
            className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${styles[status] || "bg-gray-100 text-gray-600"
                }`}
        >
            {status || "Unknown"}
        </span>
    );
}

export default function Publishing() {
    const [documents, setDocuments] = useState([]);
    const [selectedConversionId, setSelectedConversionId] = useState("");
    const [publications, setPublications] = useState([]);
    const [selectedPublication, setSelectedPublication] = useState(null);

    const [loadingDocuments, setLoadingDocuments] = useState(true);
    const [loadingPublications, setLoadingPublications] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [loadingVersion, setLoadingVersion] = useState(false);

    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    const selectedDocument = documents.find(
        (document) => document.conversion_id === selectedConversionId
    );

    const loadDocuments = useCallback(async (signal) => {
        setLoadingDocuments(true);
        setError("");

        try {
            const response = await getDocuments({
                limit: PAGE_SIZE,
                offset: 0,
                signal,
            });

            const items = (response.items || []).filter(
                (document) => document.status === "completed"
            );

            setDocuments(items);

            setSelectedConversionId((current) => {
                if (current && items.some((item) => item.conversion_id === current)) {
                    return current;
                }

                return items[0]?.conversion_id || "";
            });
        } catch (err) {
            if (err.name !== "AbortError") {
                setError(err.message || "Unable to load completed documents.");
            }
        } finally {
            if (!signal?.aborted) {
                setLoadingDocuments(false);
            }
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        loadDocuments(controller.signal);

        return () => controller.abort();
    }, [loadDocuments]);

    const loadPublications = useCallback(async (conversionId, signal) => {
        if (!conversionId) {
            setPublications([]);
            setSelectedPublication(null);
            return;
        }

        setLoadingPublications(true);
        setError("");

        try {
            const response = await getPublications(conversionId, signal);
            const items = response.items || [];

            setPublications(items);

            if (items.length > 0) {
                const latest = items[0];
                const publication = await getPublication(
                    conversionId,
                    latest.version,
                    signal
                );

                setSelectedPublication(publication);
            } else {
                setSelectedPublication(null);
            }
        } catch (err) {
            if (err.name !== "AbortError") {
                setError(err.message || "Unable to load publication history.");
                setPublications([]);
                setSelectedPublication(null);
            }
        } finally {
            if (!signal?.aborted) {
                setLoadingPublications(false);
            }
        }
    }, []);

    useEffect(() => {
        if (!selectedConversionId) {
            setPublications([]);
            setSelectedPublication(null);
            return;
        }

        const controller = new AbortController();
        loadPublications(selectedConversionId, controller.signal);

        return () => controller.abort();
    }, [selectedConversionId, loadPublications]);

    const handlePublish = async () => {
        if (!selectedConversionId || publishing) return;

        setPublishing(true);
        setError("");
        setSuccess("");

        try {
            const publication = await createPublication(selectedConversionId);

            setSelectedPublication(publication);
            setSuccess(
                `Publication version ${publication.version} created successfully.`
            );

            const response = await getPublications(selectedConversionId);
            setPublications(response.items || []);
        } catch (err) {
            setError(err.message || "Unable to publish this document.");
        } finally {
            setPublishing(false);
        }
    };

    const handleSelectVersion = async (version) => {
        if (!selectedConversionId) return;

        setLoadingVersion(true);
        setError("");

        try {
            const publication = await getPublication(
                selectedConversionId,
                version
            );

            setSelectedPublication(publication);
        } catch (err) {
            setError(err.message || "Unable to load this publication version.");
        } finally {
            setLoadingVersion(false);
        }
    };

    const handleRefresh = () => {
        const controller = new AbortController();
        loadDocuments(controller.signal);
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                <div>
                    <h1 className="text-2xl font-bold text-navy">Publishing</h1>
                    <p className="mt-1 text-sm text-gray-500">
                        Publish approved questions and manage immutable publication versions.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={handleRefresh}
                    disabled={loadingDocuments}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                    <RefreshCw
                        size={16}
                        className={loadingDocuments ? "animate-spin" : ""}
                    />
                    Refresh
                </button>
            </div>

            {error && (
                <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                    <AlertCircle size={18} className="mt-0.5 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {success && (
                <div className="flex items-start gap-3 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-700">
                    <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
                    <span>{success}</span>
                </div>
            )}

            <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                    <FileText size={19} className="text-deep-purple" />
                    <h2 className="font-semibold text-navy">Select source document</h2>
                </div>

                {loadingDocuments ? (
                    <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
                        <Loader2 size={17} className="animate-spin" />
                        Loading completed documents...
                    </div>
                ) : documents.length === 0 ? (
                    <p className="rounded-xl bg-gray-50 p-4 text-sm text-gray-500">
                        No completed documents are available for publishing.
                    </p>
                ) : (
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
                        <div className="min-w-0 flex-1">
                            <label
                                htmlFor="publishing-document"
                                className="mb-2 block text-sm font-medium text-gray-700"
                            >
                                Completed document
                            </label>

                            <select
                                id="publishing-document"
                                value={selectedConversionId}
                                onChange={(event) => {
                                    setSelectedConversionId(event.target.value);
                                    setSuccess("");
                                }}
                                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 outline-none focus:border-deep-purple focus:ring-2 focus:ring-deep-purple/10"
                            >
                                {documents.map((document) => (
                                    <option
                                        key={document.conversion_id}
                                        value={document.conversion_id}
                                    >
                                        {document.filename || document.conversion_id}
                                    </option>
                                ))}
                            </select>

                            {selectedDocument && (
                                <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-gray-500">
                                    <StatusBadge status={selectedDocument.status} />
                                    <span>
                                        {selectedDocument.total_questions ?? 0} extracted questions
                                    </span>
                                    <span>
                                        {selectedDocument.format?.toUpperCase() || "Unknown format"}
                                    </span>
                                </div>
                            )}
                        </div>

                        <button
                            type="button"
                            onClick={handlePublish}
                            disabled={!selectedConversionId || publishing}
                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-pink px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            {publishing ? (
                                <Loader2 size={17} className="animate-spin" />
                            ) : (
                                <Upload size={17} />
                            )}
                            {publishing ? "Publishing..." : "Create publication"}
                        </button>
                    </div>
                )}

                <p className="mt-4 text-xs text-gray-500">
                    Publishing applies the backend approval rules. Questions that do not
                    meet those rules are excluded from the publication snapshot.
                </p>
            </section>

            <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                        <Clock size={19} className="text-deep-purple" />
                        <h2 className="font-semibold text-navy">Publication history</h2>
                    </div>

                    <span className="rounded-full bg-lavender-light px-3 py-1 text-xs font-semibold text-deep-purple">
                        {publications.length} versions
                    </span>
                </div>

                {!selectedConversionId ? (
                    <p className="text-sm text-gray-500">
                        Select a completed document to view its publication history.
                    </p>
                ) : loadingPublications ? (
                    <div className="flex items-center gap-2 py-5 text-sm text-gray-500">
                        <Loader2 size={17} className="animate-spin" />
                        Loading publication history...
                    </div>
                ) : publications.length === 0 ? (
                    <p className="rounded-xl bg-gray-50 p-4 text-sm text-gray-500">
                        No publication versions exist for this document yet.
                    </p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full min-w-[600px] text-left text-sm">
                            <thead>
                                <tr className="border-b border-gray-100 text-xs uppercase tracking-wide text-gray-500">
                                    <th className="px-3 py-3 font-semibold">Version</th>
                                    <th className="px-3 py-3 font-semibold">Published at</th>
                                    <th className="px-3 py-3 font-semibold">Questions</th>
                                    <th className="px-3 py-3 font-semibold">Excluded</th>
                                    <th className="px-3 py-3 font-semibold">Action</th>
                                </tr>
                            </thead>

                            <tbody>
                                {publications.map((publication) => (
                                    <tr
                                        key={publication.publication_id || publication.version}
                                        className="border-b border-gray-50 last:border-0"
                                    >
                                        <td className="px-3 py-4 font-semibold text-navy">
                                            v{publication.version}
                                        </td>
                                        <td className="px-3 py-4 text-gray-600">
                                            {formatDate(publication.published_at)}
                                        </td>
                                        <td className="px-3 py-4 text-gray-600">
                                            {publication.total_questions ?? 0}
                                        </td>
                                        <td className="px-3 py-4 text-gray-600">
                                            {publication.excluded_questions ?? "—"}
                                        </td>
                                        <td className="px-3 py-4">
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    handleSelectVersion(publication.version)
                                                }
                                                className="font-semibold text-deep-purple hover:underline"
                                            >
                                                View snapshot
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                        <BookOpen size={19} className="text-deep-purple" />
                        <h2 className="font-semibold text-navy">Published snapshot</h2>
                    </div>

                    {selectedPublication && (
                        <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                            Version {selectedPublication.version}
                        </span>
                    )}
                </div>

                {loadingVersion ? (
                    <div className="flex items-center gap-2 py-5 text-sm text-gray-500">
                        <Loader2 size={17} className="animate-spin" />
                        Loading publication...
                    </div>
                ) : !selectedPublication ? (
                    <p className="rounded-xl bg-gray-50 p-4 text-sm text-gray-500">
                        Select a publication version to inspect its published questions.
                    </p>
                ) : (
                    <div className="space-y-5">
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                            <div className="rounded-xl bg-gray-50 p-4">
                                <p className="text-xs text-gray-500">Published questions</p>
                                <p className="mt-1 text-2xl font-bold text-navy">
                                    {selectedPublication.total_questions ?? 0}
                                </p>
                            </div>

                            <div className="rounded-xl bg-gray-50 p-4">
                                <p className="text-xs text-gray-500">Excluded questions</p>
                                <p className="mt-1 text-2xl font-bold text-navy">
                                    {Array.isArray(selectedPublication.excluded_questions)
                                        ? selectedPublication.excluded_questions.length
                                        : Number(selectedPublication.excluded_questions ?? 0)}
                                </p>
                            </div>

                            <div className="rounded-xl bg-gray-50 p-4">
                                <p className="text-xs text-gray-500">Published at</p>
                                <p className="mt-2 text-sm font-semibold text-navy">
                                    {formatDate(selectedPublication.published_at)}
                                </p>
                            </div>
                        </div>

                        {Array.isArray(selectedPublication.excluded_questions) &&
                            selectedPublication.excluded_questions.length > 0 && (
                                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                                    <h3 className="mb-3 text-sm font-semibold text-amber-800">
                                        Excluded questions ({selectedPublication.excluded_questions.length})
                                    </h3>

                                    <div className="space-y-2">
                                        {selectedPublication.excluded_questions.map((item) => (
                                            <div
                                                key={item.question_id}
                                                className="flex flex-col gap-1 text-sm sm:flex-row sm:justify-between"
                                            >
                                                <span className="font-medium text-gray-800">
                                                    Question {item.question_id}
                                                </span>
                                                <span className="text-amber-800">{item.reason}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                        {selectedPublication.questions?.length ? (
                            <div className="space-y-3">
                                {selectedPublication.questions.map((question, index) => (
                                    <article
                                        key={question.question_id || question.stable_id || index}
                                        className="rounded-xl border border-gray-100 p-4"
                                    >
                                        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                                            <div>
                                                <p className="text-sm font-semibold text-navy">
                                                    Question {question.question_number || index + 1}
                                                </p>
                                                <p className="mt-1 text-xs text-gray-500">
                                                    {question.section_name || question.section || "General section"}
                                                </p>
                                            </div>

                                            <span className="rounded-full bg-green-50 px-3 py-1 text-xs font-semibold text-green-700">
                                                Published
                                            </span>
                                        </div>

                                        <p className="whitespace-pre-wrap text-sm leading-6 text-gray-700">
                                            {question.question_en ||
                                                question.original_text ||
                                                question.reconstructed_text ||
                                                "Question text unavailable"}
                                        </p>

                                        {question.options?.length > 0 && (
                                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                                {question.options.map((option, optionIndex) => {
                                                    const optionId = String(option.id ?? optionIndex + 1);
                                                    const isCorrect =
                                                        String(question.correct_answer) === optionId;

                                                    return (
                                                        <div
                                                            key={option.id ?? optionIndex}
                                                            className={`rounded-lg border px-3 py-2 text-sm ${isCorrect
                                                                ? "border-green-200 bg-green-50 text-green-800"
                                                                : "border-gray-100 bg-gray-50 text-gray-700"
                                                                }`}
                                                        >
                                                            <span className="mr-2 font-semibold">
                                                                {option.id ?? optionIndex + 1}.
                                                            </span>
                                                            {option.text_en || option.text || "—"}
                                                            {isCorrect && (
                                                                <CheckCircle2
                                                                    size={15}
                                                                    className="ml-2 inline"
                                                                />
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}

                                        {question.question_hi && (
                                            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-gray-600">
                                                {question.question_hi}
                                            </p>
                                        )}
                                    </article>
                                ))}
                            </div>
                        ) : (
                            <div className="flex items-center gap-2 rounded-xl bg-gray-50 p-4 text-sm text-gray-500">
                                <XCircle size={17} />
                                This publication contains no questions.
                            </div>
                        )}
                    </div>
                )}
            </section>
        </div>
    );
}
