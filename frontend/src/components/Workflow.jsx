import { ArrowRight, Braces, CloudUpload, Download, FileText, Layers } from "lucide-react";

const STEPS = [
    { icon: CloudUpload, label: "1. Upload File", detail: "", tone: "from-sky-soft to-white", color: "text-sky-500" },
    { icon: FileText, label: "2. Extract Content", detail: "(Text, Images, SVG)", tone: "from-lavender to-white", color: "text-deep-purple" },
    { icon: Layers, label: "3. Structure Questions & Answers", detail: "", tone: "from-orange-100 to-white", color: "text-brand-orange" },
    { icon: Braces, label: "4. Generate JSON", detail: "", tone: "from-pink-light to-white", color: "text-brand-pink" },
    { icon: Download, label: "5. Download", detail: "(JSON / ZIP)", tone: "from-orange-100 to-white", color: "text-brand-orange" },
];

export default function Workflow() {
    return (
        <section id="how-it-works" className="mx-auto mt-14 w-full max-w-6xl">
            <div className="flex items-center justify-center gap-4">
                <span className="h-0.5 w-20 bg-linear-to-r from-brand-orange to-brand-pink sm:w-28" />
                <h2 className="text-2xl font-bold text-navy sm:text-3xl">How It Works</h2>
                <span className="h-0.5 w-20 bg-linear-to-l from-brand-orange to-brand-pink sm:w-28" />
            </div>

            <ol className="mt-6 flex flex-col items-stretch gap-2 lg:flex-row lg:items-center lg:justify-center lg:gap-3">
                {STEPS.map(({ icon: Icon, label, detail, tone, color }, index) => (
                    <li key={label} className="flex flex-col items-center gap-2 lg:flex-row lg:gap-3">
                        <div
                            className={`flex w-full min-w-40 flex-col items-center justify-center gap-2 rounded-2xl bg-linear-to-b ${tone} px-4 py-4 text-center shadow-[0_12px_28px_-16px_rgba(73,50,140,0.4)] ring-1 ring-white lg:h-28 lg:w-auto lg:max-w-52`}
                        >
                            <Icon size={30} strokeWidth={1.8} className={color} />
                            <p className="text-sm font-semibold leading-snug text-navy">
                                {label}
                                {detail && <span className="block font-medium text-navy/80">{detail}</span>}
                            </p>
                        </div>
                        {index < STEPS.length - 1 && (
                            <ArrowRight size={26} className="shrink-0 rotate-90 text-deep-purple/70 lg:rotate-0" aria-hidden="true" />
                        )}
                    </li>
                ))}
            </ol>
        </section>
    );
}