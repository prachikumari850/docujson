import { ArrowRight, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Decor } from "../assets/illustrations";
import DocumentIntelligenceArt from "../components/DocumentIntelligenceArt";
import FeatureCards from "../components/FeatureCards";
import Navbar from "../components/Navbar";
import Workflow from "../components/Workflow";

function Hero() {
    return (
        <section className="grid items-center gap-12 py-12 lg:grid-cols-2 lg:gap-8 lg:py-16">
            <div className="text-center lg:text-left">
                <span className="inline-flex items-center gap-2 rounded-full border border-brand-orange/60 bg-white px-4 py-2 text-sm font-semibold text-navy shadow-sm">
                    <Sparkles size={16} className="fill-brand-orange text-brand-orange" />
                    AI-Powered Document Intelligence
                </span>

                <h1 className="mt-6 text-4xl font-extrabold leading-tight tracking-tight text-navy sm:text-5xl lg:text-6xl">
                    Turn documents into{" "}
                    <span className="bg-linear-to-r from-brand-orange to-brand-pink bg-clip-text text-transparent">
                        structured knowledge.
                    </span>
                </h1>

                <p className="mx-auto mt-6 max-w-xl text-base font-medium leading-relaxed text-deep-purple sm:text-lg lg:mx-0">
                    Import documents, extract meaningful content, organize questions and answers, review results, and
                    prepare structured educational content with AI-powered intelligence.
                </p>

                <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row lg:justify-start">
                    <Link
                        to="/signup"
                        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-linear-to-r from-brand-orange to-brand-pink px-7 py-3.5 text-sm font-bold text-white shadow-lg shadow-brand-pink/20 transition hover:-translate-y-0.5 hover:shadow-xl sm:w-auto"
                    >
                        Get Started
                        <ArrowRight size={18} />
                    </Link>
                    <Link
                        to="/login"
                        className="inline-flex w-full items-center justify-center rounded-xl border border-lavender bg-white px-7 py-3.5 text-sm font-bold text-navy shadow-sm transition hover:bg-lavender-light sm:w-auto"
                    >
                        Login to Workspace
                    </Link>
                </div>

                <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-sm font-medium text-navy/70 lg:justify-start">
                    <span className="inline-flex items-center gap-2">
                        <ShieldCheck size={17} className="text-emerald-600" />
                        Structured review workflow
                    </span>
                    <span className="inline-flex items-center gap-2">
                        <ShieldCheck size={17} className="text-emerald-600" />
                        Document-focused processing
                    </span>
                </div>
            </div>

            <div className="px-2 sm:px-6 lg:px-0">
                <DocumentIntelligenceArt />
            </div>
        </section>
    );
}

function CallToAction() {
    return (
        <section className="mt-16 overflow-hidden rounded-3xl bg-linear-to-r from-[#49328C] via-[#7753B9] to-[#C66F9F] px-6 py-12 text-center shadow-[0_20px_50px_-25px_rgba(73,50,140,0.5)] sm:px-12">
            <h2 className="text-2xl font-bold text-white sm:text-3xl">
                Make your documents more useful.
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-white/85 sm:text-base">
                Bring your educational content into one organized workspace for extraction, review, and publishing.
            </p>
            <Link
                to="/signup"
                className="mt-7 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 font-bold text-deep-purple shadow-md transition hover:-translate-y-0.5 hover:shadow-lg"
            >
                Create Your Workspace
                <ArrowRight size={18} />
            </Link>
        </section>
    );
}

export default function Home() {
    return (
        <div
            id="home"
            className="relative min-h-screen overflow-x-hidden bg-linear-to-b from-[#F7F0FF] via-[#FBF3FF] to-[#FFEEF6]"
        >
            <Decor />
            <Navbar />

            <main className="relative z-10 mx-auto w-full max-w-7xl px-4 pb-20 sm:px-6">
                <Hero />
                <FeatureCards />
                <Workflow />
                <CallToAction />
            </main>

            <footer className="relative z-10 border-t border-lavender/70 bg-white/50">
                <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-4 py-6 text-center sm:flex-row sm:px-6 sm:text-left">
                    <p className="text-sm font-bold text-navy">
                        NEET<span className="text-brand-orange">DAY</span>
                    </p>
                    <p className="text-xs font-medium text-navy/60">
                        AI-powered document intelligence and content management.
                    </p>
                </div>
            </footer>
        </div>
    );
}
