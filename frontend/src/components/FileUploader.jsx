import { useRef, useState } from "react";
import { FileText, FolderOpen, Play, X } from "lucide-react";
import { CloudUploadArt } from "../assets/illustrations";
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB } from "../services/converterApi";
import { formatFileSize } from "../utils/formatFileSize";
import ProcessingStatus from "./ProcessingStatus";

function DashedBorder() {
    return <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true"><defs><linearGradient id="upload-dash-gradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#FF7518" /><stop offset="1" stopColor="#F20B83" /></linearGradient></defs><rect x="1.5" y="1.5" rx="32" ry="32" fill="none" stroke="url(#upload-dash-gradient)" strokeWidth="2" strokeDasharray="9 7" style={{ width: "calc(100% - 3px)", height: "calc(100% - 3px)" }} /></svg>;
}

export default function FileUploader({ files, roles, phase, uploadProgress, progress, stage, error, totalQuestions, onSelect, onRoleChange, onRemove, onProcess }) {
    const inputRef = useRef(null);
    const [dragging, setDragging] = useState(false);
    const busy = phase === "uploading" || phase === "processing";
    const openPicker = () => inputRef.current?.click();
    const handleFiles = (incoming) => { if (incoming?.length) onSelect(incoming); };
    const handleDrop = (event) => { event.preventDefault(); setDragging(false); if (!busy) handleFiles(event.dataTransfer.files); };

    return (
        <div className="mx-auto w-full max-w-4xl rounded-[44px] bg-white/70 p-3 shadow-[0_30px_80px_-30px_rgba(242,11,131,0.4)] ring-1 ring-white">
            <div onDrop={handleDrop} onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false); }} aria-label="File drop zone" className={`relative flex min-h-[320px] flex-col items-center justify-center rounded-[34px] px-5 py-10 text-center transition sm:min-h-[340px] sm:px-10 ${dragging ? "bg-pink-light" : "bg-linear-to-b from-white to-pink-light/50"}`}>
                <DashedBorder />
                <input ref={inputRef} type="file" hidden multiple accept={ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(",")} onChange={(event) => { handleFiles(event.target.files); event.target.value = ""; }} />
                {!files.length ? <>
                    <CloudUploadArt className="h-28 w-40 sm:h-32 sm:w-48" />
                    <h2 className="mt-1 text-3xl font-bold text-navy sm:text-4xl">Drag &amp; Drop Your File Here</h2>
                    <div className="my-3 flex w-72 max-w-full items-center gap-3 text-sm font-medium text-navy"><span className="h-0.5 flex-1 bg-linear-to-r from-transparent to-brand-pink" />or<span className="h-0.5 flex-1 bg-linear-to-l from-transparent to-brand-pink" /></div>
                    <button type="button" onClick={openPicker} className="flex items-center gap-3 rounded-full bg-linear-to-r from-brand-orange to-brand-pink px-12 py-4 text-xl font-semibold text-white shadow-[0_12px_30px_-8px_rgba(242,11,131,0.55)] transition hover:scale-[1.02]"><FolderOpen size={26} />Choose Files</button>
                    <p className="mt-5 text-sm font-medium text-navy sm:text-base">Supports: {ACCEPTED_EXTENSIONS.map((ext) => ext.toUpperCase()).join(", ")}<span className="mx-3 text-navy/60">|</span>Combined max: {MAX_UPLOAD_MB} MB</p>
                </> : <div className="flex w-full max-w-2xl flex-col items-center gap-4">
                    <h2 className="text-2xl font-bold text-navy">Files ready to process</h2>
                    <div className="w-full space-y-3">
                        {files.map((file, index) => <div key={`${file.name}-${file.lastModified}`} className="flex flex-wrap items-center gap-3 rounded-2xl border border-lavender bg-white p-3 text-left shadow-sm">
                            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-pink-light to-lavender text-brand-pink"><FileText size={25} /></span>
                            <div className="min-w-0 flex-1"><p className="truncate font-semibold text-navy" title={file.name}>{file.name}</p><p className="text-sm text-navy/60">{formatFileSize(file.size)} · {file.name.split(".").pop().toUpperCase()}</p></div>
                            <label className="text-sm font-semibold text-navy">Role <select disabled={busy} value={roles[index]} onChange={(event) => onRoleChange(index, event.target.value)} className="ml-2 rounded-lg border border-lavender bg-white px-2 py-2"><option value="question_paper">Question paper</option><option value="answer_key">Answer key</option></select></label>
                            <button type="button" disabled={busy} onClick={() => onRemove(index)} aria-label={`Remove ${file.name}`} className="flex h-10 w-10 items-center justify-center rounded-xl text-brand-pink hover:bg-pink-light disabled:opacity-40"><X size={22} /></button>
                        </div>)}
                    </div>
                    {!busy && files.length < 2 && <button type="button" onClick={openPicker} className="rounded-full border border-lavender bg-white px-5 py-2 font-semibold text-deep-purple hover:bg-lavender-light">Add another file</button>}
                    {!busy && <button type="button" onClick={onProcess} className="flex items-center gap-2 rounded-full bg-linear-to-r from-brand-orange to-brand-pink px-8 py-3 font-semibold text-white shadow-md"><Play size={18} />Process files</button>}
                    <ProcessingStatus phase={phase} uploadProgress={uploadProgress} progress={progress} stage={stage} error={error} totalQuestions={totalQuestions} />
                    {error && phase !== "failed" && <p className="text-sm font-semibold text-brand-pink" role="alert">{error}</p>}
                </div>}
                {error && !files.length && <p className="mt-4 max-w-md text-sm font-semibold text-brand-pink" role="alert">{error}</p>}
            </div>
        </div>
    );
}
