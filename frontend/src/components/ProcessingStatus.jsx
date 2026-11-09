import { CircleAlert, CircleCheck } from "lucide-react";

function ProgressBar({ label, value, indeterminate }) {
    return (
        <div className="w-full max-w-xl" role="status" aria-live="polite">
            <div className="mb-2 flex items-center justify-between text-sm font-semibold text-navy">
                <span>{label}</span>
                {!indeterminate && <span>{Math.round(value)}%</span>}
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-lavender">
                <div
                    className={`h-full rounded-full bg-linear-to-r from-brand-orange to-brand-pink transition-all duration-300 ${indeterminate ? "progress-indeterminate" : ""
                        }`}
                    style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
                />
            </div>
        </div>
    );
}

export default function ProcessingStatus({ phase, uploadProgress, progress, stage, error, totalQuestions }) {
    if (phase === "uploading") {
        return <ProgressBar label="Uploading file…" value={uploadProgress} />;
    }
    if (phase === "processing") {
        return <ProgressBar label={stage || "Processing document…"} value={progress} indeterminate={progress <= 0} />;
    }
    if (phase === "completed") {
        return (
            <p className="flex items-center gap-2 text-base font-semibold text-emerald-600" role="status">
                <CircleCheck size={22} />
                Conversion complete{Number.isFinite(totalQuestions) ? ` — ${totalQuestions} questions found` : ""}
            </p>
        );
    }
    if (phase === "failed") {
        return (
            <p className="flex items-start gap-2 text-left text-base font-semibold text-brand-pink" role="alert">
                <CircleAlert size={22} className="mt-0.5 shrink-0" />
                {error}
            </p>
        );
    }
    return null;
}