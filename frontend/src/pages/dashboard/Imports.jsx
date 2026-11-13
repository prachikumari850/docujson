
import { FileText, ShieldCheck, Upload } from "lucide-react";
import DownloadActions from "../../components/DownloadActions";
import FileUploader from "../../components/FileUploader";
import QuestionPreview from "../../components/QuestionPreview";
import { useConverter } from "../../hooks/useConverter";

export default function Imports() {
    const converter = useConverter();
    const completed = converter.phase === "completed";

    return (
        <div className="space-y-8">
            <section>
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <h2 className="text-xl font-bold text-navy">Import Documents</h2>
                        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-navy/60">
                            Upload question papers and optional answer keys to extract structured educational content.
                        </p>
                    </div>

                    <div className="flex items-center gap-2 rounded-xl border border-lavender bg-white px-3 py-2 text-xs font-semibold text-deep-purple">
                        <ShieldCheck size={16} />
                        Document Processing
                    </div>
                </div>
            </section>

            <section className="rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-7">
                <div className="mb-6 flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-lavender-light text-deep-purple">
                        <Upload size={21} />
                    </div>
                    <div>
                        <h3 className="font-bold text-navy">Upload Your Files</h3>
                        <p className="mt-1 text-xs text-navy/55">
                            Select a question paper and optionally add its answer key.
                        </p>
                    </div>
                </div>

                <FileUploader
                    files={converter.files}
                    roles={converter.roles}
                    phase={converter.phase}
                    uploadProgress={converter.uploadProgress}
                    progress={converter.progress}
                    stage={converter.stage}
                    error={converter.error}
                    totalQuestions={converter.result?.document?.total_questions}
                    onSelect={converter.selectFiles}
                    onRoleChange={converter.setFileRole}
                    onRemove={converter.removeFile}
                    onProcess={converter.runConversion}
                />
            </section>

            {completed && (
                <section className="rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-7">
                    <div className="mb-5 flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-pink-light text-brand-pink">
                            <FileText size={21} />
                        </div>
                        <div>
                            <h3 className="font-bold text-navy">Extraction Results</h3>
                            <p className="mt-1 text-xs text-navy/55">
                                Review the extracted content and download the results.
                            </p>
                        </div>
                    </div>

                    <DownloadActions
                        enabled={completed}
                        downloading={converter.downloading}
                        error={converter.downloadError}
                        onDownload={converter.download}
                    />

                    <QuestionPreview
                        result={converter.result}
                        conversionId={converter.conversionId}
                    />
                </section>
            )}

            {!completed && (
                <div className="rounded-2xl border border-dashed border-lavender bg-white/60 p-6 text-center">
                    <FileText size={27} className="mx-auto text-deep-purple/50" />
                    <p className="mt-3 text-sm font-semibold text-navy">
                        Your extraction results will appear here
                    </p>
                    <p className="mt-1 text-xs text-navy/50">
                        Upload and process a document to view extracted questions and answers.
                    </p>
                </div>
            )}
        </div>
    );
}
