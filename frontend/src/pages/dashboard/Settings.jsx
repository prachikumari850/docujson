import { useEffect, useState } from "react";
import {
    AlertCircle,
    BrainCircuit,
    CheckCircle2,
    FileText,
    HardDrive,
    RefreshCw,
    ScanText,
    Settings2,
} from "lucide-react";
import { getSettings } from "../../services/converterApi";

function SettingCard({ icon: Icon, title, description, children }) {
    return (
        <section className="rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)]">
            <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-lavender-light text-deep-purple">
                    <Icon size={21} />
                </div>

                <div>
                    <h3 className="font-semibold text-navy">
                        {title}
                    </h3>
                    <p className="mt-1 text-sm text-navy/55">
                        {description}
                    </p>
                </div>
            </div>

            <div className="mt-5 space-y-4">
                {children}
            </div>
        </section>
    );
}

function SettingRow({ label, value }) {
    return (
        <div className="flex items-center justify-between gap-4 border-b border-lavender/40 pb-3 last:border-0 last:pb-0">
            <span className="text-sm text-navy/60">
                {label}
            </span>

            <span className="text-right text-sm font-semibold text-navy">
                {value ?? "—"}
            </span>
        </div>
    );
}

function StatusLabel({ enabled }) {
    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${enabled
            ? "bg-green-50 text-green-700"
            : "bg-gray-100 text-gray-600"
            }`}>
            {enabled ? (
                <CheckCircle2 size={13} />
            ) : (
                <AlertCircle size={13} />
            )}

            {enabled ? "Enabled" : "Disabled"}
        </span>
    );
}

export default function Settings() {
    const [configuration, setConfiguration] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    async function loadSettings(signal) {
        setLoading(true);
        setError("");

        try {
            const data = await getSettings(signal);
            setConfiguration(data);
        } catch (err) {
            if (err.name !== "AbortError") {
                setError(err.message || "Unable to load settings.");
            }
        } finally {
            if (!signal?.aborted) {
                setLoading(false);
            }
        }
    }

    useEffect(() => {
        const controller = new AbortController();

        loadSettings(controller.signal);

        return () => controller.abort();
    }, []);

    if (loading) {
        return (
            <div className="flex min-h-[40vh] items-center justify-center">
                <div className="h-9 w-9 animate-spin rounded-full border-4 border-lavender border-t-deep-purple" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-6">
                <div className="flex items-center gap-2 font-semibold text-red-700">
                    <AlertCircle size={19} />
                    Unable to load settings
                </div>

                <p className="mt-2 text-sm text-red-600">
                    {error}
                </p>

                <button
                    type="button"
                    onClick={() => loadSettings()}
                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-deep-purple px-4 py-2 text-sm font-semibold text-white hover:bg-navy"
                >
                    <RefreshCw size={15} />
                    Retry
                </button>
            </div>
        );
    }

    if (!configuration) return null;

    const { upload, storage, ocr, extraction, ai } = configuration;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2">
                        <Settings2 size={22} className="text-deep-purple" />
                        <h2 className="text-xl font-bold text-navy">
                            Settings
                        </h2>
                    </div>

                    <p className="mt-2 text-sm text-navy/55">
                        View the current application and processing configuration.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => loadSettings()}
                    className="inline-flex items-center gap-2 rounded-xl border border-lavender px-4 py-2 text-sm font-semibold text-deep-purple transition hover:bg-lavender-light"
                >
                    <RefreshCw size={15} />
                    Refresh
                </button>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
                <SettingCard
                    icon={FileText}
                    title="Document Upload"
                    description="Supported file formats and upload limits."
                >
                    <SettingRow
                        label="Maximum upload size"
                        value={`${upload.max_size_mb} MB`}
                    />

                    <SettingRow
                        label="Supported formats"
                        value={upload.supported_formats
                            .map((format) => format.toUpperCase())
                            .join(", ")}
                    />
                </SettingCard>

                <SettingCard
                    icon={HardDrive}
                    title="Storage"
                    description="Current document storage configuration."
                >
                    <SettingRow
                        label="Storage provider"
                        value={
                            storage.type === "local"
                                ? "Local filesystem"
                                : storage.type
                        }
                    />
                </SettingCard>

                <SettingCard
                    icon={ScanText}
                    title="OCR Configuration"
                    description="Optical character recognition settings."
                >
                    <SettingRow
                        label="OCR languages"
                        value={ocr.languages}
                    />

                    <SettingRow
                        label="OCR resolution"
                        value={`${ocr.dpi} DPI`}
                    />
                </SettingCard>

                <SettingCard
                    icon={BrainCircuit}
                    title="Extraction Configuration"
                    description="Document media and mathematical content processing."
                >
                    <SettingRow
                        label="Media crop margin"
                        value={`${extraction.media_crop_margin_pt} pt`}
                    />

                    <SettingRow
                        label="Math crop resolution"
                        value={`${extraction.math_crop_dpi} DPI`}
                    />
                </SettingCard>

                <SettingCard
                    icon={BrainCircuit}
                    title="AI Configuration"
                    description="Local AI model integration status."
                >
                    <div className="flex items-center justify-between gap-3">
                        <span className="text-sm text-navy/60">
                            AI processing
                        </span>
                        <StatusLabel enabled={ai.enabled} />
                    </div>

                    <SettingRow
                        label="Provider"
                        value={ai.provider.toUpperCase()}
                    />

                    <SettingRow
                        label="Model"
                        value={ai.model || "Not configured"}
                    />
                </SettingCard>
            </div>

            <div className="rounded-2xl border border-lavender/60 bg-lavender-light/50 p-4">
                <p className="text-sm font-semibold text-deep-purple">
                    Configuration is read-only
                </p>

                <p className="mt-1 text-sm leading-relaxed text-navy/60">
                    These values are loaded from the backend environment
                    configuration. To change them, update the backend
                    environment settings and restart the backend service.
                </p>
            </div>
        </div>
    );
}
