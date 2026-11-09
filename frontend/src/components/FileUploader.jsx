import { useRef, useState } from "react";
import { FileText, FolderOpen, RefreshCw, X } from "lucide-react";
import { CloudUploadArt } from "../assets/illustrations";
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB } from "../services/converterApi";
import { formatFileSize } from "../utils/formatFileSize";
import ProcessingStatus from "./ProcessingStatus";

function DashedBorder() {
    return (
        <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
            <defs>
                <linearGradient id="upload-dash-gradient" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0" stopColor="#FF7518" />
                    <stop offset="1" stopColor="#F20B83" />
                </linearGradient>
            </defs>
            <rect
                x="1.5"
                y="1.5"
                rx="32"
                ry="32"
                fill="none"
                stroke="url(#upload-dash-gradient)"
                strokeWidth="2"
                strokeDasharray="9 7"
                style={{ width: "calc(100% - 3px)", height: "calc(100% - 3px)" }}
            />
        </svg>
    );
}

function EmptyState({ error, onChoose }) {
    return (
        <>
            <CloudUploadArt className="h-28 w-40 sm:h-32 sm:w-48" />
            <h2 className="mt-1 text-3xl font-bold text-navy sm:text-4xl">Drag &amp; Drop Your File Here</h2>
            <div className="my-3 flex w-72 max-w-full items-center gap-3 text-sm font-medium text-navy">
                <span className="h-0.5 flex-1 bg-linear-to-r from-transparent to-brand-pink" />
                or
                <span className="h-0.5 flex-1 bg-linear-to-l from-transparent to-brand-pink" />
            </div>
            <button
                type="button"
                onClick={onChoose}
                className="flex items-center gap-3 rounded-full bg-linear-to-r from-brand-orange to-brand-pink px-12 py-4 text-xl font-semibold text-white shadow-[0_12px_30px_-8px_rgba(242,11,131,0.55)] transition hover:scale-[1.02] hover:shadow-[0_16px_36px_-8px_rgba(242,11,131,0.65)] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-pink"
            >
                <FolderOpen size={26} />
                Choose File
            </button>
            <p className="mt-5 text-sm font-medium text-navy sm:text-base">
                Supports: {ACCEPTED_EXTENSIONS.map((ext) => ext.toUpperCase()).join(", ")}
                <span className="mx-3 text-navy/60">|</span>
                Max Size: {MAX_UPLOAD_MB} MB
            </p>
            {error && (
                <p className="mt-4 max-w-md text-sm font-semibold text-brand-pink" role="alert">
                    {error}
                </p>
            )}
        </>
    );
}

function SelectedFile({ file, busy, status, onReplace, onRemove }) {
    const extension = file.name.split(".").pop().toUpperCase();

    return (
        <div className="flex w-full max-w-xl flex-col items-center gap-6">
            <div className="flex w-full items-center gap-4 rounded-2xl border border-lavender bg-white p-4 text-left shadow-sm">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-pink-light to-lavender text-brand-pink">
                    <FileText size={28} />
                </span>
                <div className="min-w-0 flex-1">
                    <p className="truncate text-base font-semibold text-navy" title={file.name}>
                        {file.name}
                    </p>
                    <p className="text-sm text-navy/60">
                        {formatFileSize(file.size)} · {extension}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={onReplace}
                    disabled={busy}
                    aria-label="Replace file"
                    className="flex h-10 w-10 items-center justify-center rounded-xl text-deep-purple transition hover:bg-lavender-light disabled:cursor-not-allowed disabled:opacity-40"
                >
                    <RefreshCw size={20} />
                </button>
                <button
                    type="button"
                    onClick={onRemove}
                    aria-label={busy ? "Cancel conversion" : "Remove file"}
                    className="flex h-10 w-10 items-center justify-center rounded-xl text-brand-pink transition hover:bg-pink-light"
                >
                    <X size={22} />
                </button>
            </div>
            {status}
        </div>
    );
}

export default function FileUploader({
    file,
    phase,
    uploadProgress,
    progress,
    stage,
    error,
    totalQuestions,
    onSelect,
    onRemove,
}) {
    const inputRef = useRef(null);
    const [dragging, setDragging] = useState(false);
    const busy = phase === "uploading" || phase === "processing";

    const openPicker = () => inputRef.current?.click();

    const handleFiles = (files) => {
        const [first] = files ?? [];
        if (first) onSelect(first);
    };

    const handleDrop = (event) => {
        event.preventDefault();
        setDragging(false);
        if (!busy) handleFiles(event.dataTransfer.files);
    };

    const handleDragOver = (event) => {
        event.preventDefault();
        if (!busy) setDragging(true);
    };

    const handleDragLeave = (event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);
    };

    const handleInputChange = (event) => {
        handleFiles(event.target.files);
        event.target.value = "";
    };

    const handleReplace = () => {
        onRemove();
        openPicker();
    };

    return (
        <div className="mx-auto w-full max-w-4xl rounded-[44px] bg-white/70 p-3 shadow-[0_30px_80px_-30px_rgba(242,11,131,0.4)] ring-1 ring-white">
            <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                aria-label="File drop zone"
                className={`relative flex min-h-[320px] flex-col items-center justify-center rounded-[34px] px-5 py-10 text-center transition sm:min-h-[340px] sm:px-10 ${dragging ? "bg-pink-light" : "bg-linear-to-b from-white to-pink-light/50"
                    }`}
            >
                <DashedBorder />
                <input
                    ref={inputRef}
                    type="file"
                    hidden
                    accept={ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(",")}
                    onChange={handleInputChange}
                />
                {file ? (
                    <SelectedFile
                        file={file}
                        busy={busy}
                        onReplace={handleReplace}
                        onRemove={onRemove}
                        status={
                            <ProcessingStatus
                                phase={phase}
                                uploadProgress={uploadProgress}
                                progress={progress}
                                stage={stage}
                                error={error}
                                totalQuestions={totalQuestions}
                            />
                        }
                    />
                ) : (
                    <EmptyState error={error} onChoose={openPicker} />
                )}
            </div>
        </div>
    );
}