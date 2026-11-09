import { Star } from "lucide-react";
import { Decor, DocsArt, JsonArt } from "../assets/illustrations";
import DownloadActions from "../components/DownloadActions";
import FeatureCards from "../components/FeatureCards";
import FileUploader from "../components/FileUploader";
import Navbar from "../components/Navbar";
import QuestionPreview from "../components/QuestionPreview";
import Workflow from "../components/Workflow";
import { useConverter } from "../hooks/useConverter";

function Hero() {
    return (
        <div className="mx-auto max-w-3xl text-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-orange/60 bg-white px-4 py-1.5 text-sm font-semibold text-navy shadow-sm">
                <Star size={15} className="fill-brand-orange text-brand-orange" />
                AI-Powered <span aria-hidden="true">•</span> Local Processing
            </span>
            <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight text-navy sm:text-5xl lg:text-6xl">
                Document to{" "}
                <span className="bg-linear-to-r from-brand-orange to-brand-pink bg-clip-text text-transparent">JSON</span>{" "}
                Converter
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-base font-medium leading-relaxed text-deep-purple sm:text-lg">
                Upload a PDF or DOCX (question paper, study material, etc.) and convert it into a structured JSON with
                questions, answers, options and diagrams (including SVG).
            </p>
        </div>
    );
}

export default function Home() {
    const converter = useConverter();
    const completed = converter.phase === "completed";

    return (
        <div id="home" className="relative min-h-screen overflow-x-hidden bg-linear-to-b from-[#F7F0FF] via-[#FBF3FF] to-[#FFEEF6]">
            <Decor />
            <Navbar />

            <main className="relative z-10 mx-auto w-full max-w-7xl px-4 pb-24 pt-8 sm:px-6">
                <div className="relative">
                    <DocsArt className="absolute -left-4 top-14 hidden w-56 xl:block 2xl:left-2" />
                    <JsonArt className="absolute -right-4 top-12 hidden w-60 xl:block 2xl:right-2" />
                    <Hero />
                    <div className="mt-8">
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
                    </div>
                </div>

                <DownloadActions
                    enabled={completed}
                    downloading={converter.downloading}
                    error={converter.downloadError}
                    onDownload={converter.download}
                />

                <FeatureCards />
                <Workflow />
                <QuestionPreview result={completed ? converter.result : null} conversionId={converter.conversionId} />
            </main>
        </div>
    );
}
