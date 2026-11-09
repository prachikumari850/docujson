import { Download, FileArchive, LoaderCircle } from "lucide-react";

const ACTIONS = [
    {
        kind: "json",
        title: "Download JSON",
        suffix: "",
        hint: "Structured questions & answers",
        Icon: Download,
        gradient: "from-[#FF9A0A] to-[#FF5A1F]",
        glow: "shadow-[0_18px_40px_-14px_rgba(255,117,24,0.7)]",
    },
    {
        kind: "zip",
        title: "Download ZIP",
        suffix: " (with Media)",
        hint: "JSON + extracted images, SVGs & diagrams",
        Icon: FileArchive,
        gradient: "from-[#F20B83] to-[#C21FA0]",
        glow: "shadow-[0_18px_40px_-14px_rgba(242,11,131,0.7)]",
    },
];

export default function DownloadActions({ enabled, downloading, error, onDownload }) {
    return (
        <div className="mx-auto mt-7 w-full max-w-4xl">
            <div className="grid gap-5 px-1 sm:grid-cols-2 sm:px-4">
                {ACTIONS.map(({ kind, title, suffix, hint, Icon, gradient, glow }) => {
                    const loading = downloading === kind;
                    const disabled = !enabled || downloading !== null;
                    return (
                        <button
                            key={kind}
                            type="button"
                            disabled={disabled}
                            onClick={() => onDownload(kind)}
                            className={`flex items-center gap-5 rounded-2xl bg-linear-to-r ${gradient} px-6 py-4 text-left text-white ring-4 ring-white/70 transition ${disabled
                                ? "cursor-not-allowed opacity-55 saturate-50"
                                : `${glow} hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-pink`
                                }`}
                        >
                            {loading ? <LoaderCircle size={44} className="shrink-0 animate-spin" /> : <Icon size={44} strokeWidth={1.6} className="shrink-0" />}
                            <span className="min-w-0">
                                <span className="block text-xl font-bold leading-tight sm:text-2xl">
                                    {title}
                                    {suffix && <span className="text-base font-medium sm:text-lg">{suffix}</span>}
                                </span>
                                <span className="mt-0.5 block text-sm font-medium text-white/90">{hint}</span>
                            </span>
                        </button>
                    );
                })}
            </div>
            {error && (
                <p className="mt-4 text-center text-sm font-semibold text-brand-pink" role="alert">
                    {error}
                </p>
            )}
        </div>
    );
}