
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { LogoMark } from "../../assets/illustrations";
import DocumentIntelligenceArt from "../DocumentIntelligenceArt";

export default function AuthLayout({ children, title, subtitle }) {
    return (
        <main className="min-h-screen overflow-hidden bg-linear-to-br from-[#F7F0FF] via-[#FBF3FF] to-[#FFEEF6]">
            <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-5 py-5 sm:px-8">
                <header className="flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-2.5">
                        <LogoMark className="h-9 w-9" />
                        <span className="text-2xl font-extrabold tracking-tight text-navy">
                            NEET<span className="text-brand-orange">DAY</span>
                        </span>
                    </Link>

                    <Link
                        to="/"
                        className="inline-flex items-center gap-2 text-sm font-semibold text-navy/70 transition hover:text-brand-pink"
                    >
                        <ArrowLeft size={17} />
                        Back to Home
                    </Link>
                </header>

                <div className="grid flex-1 items-center gap-10 py-12 lg:grid-cols-2 lg:gap-16">
                    <section className="hidden lg:block">
                        <div className="max-w-xl">
                            <span className="inline-flex items-center gap-2 rounded-full border border-brand-orange/50 bg-white px-4 py-2 text-xs font-semibold text-navy shadow-sm">
                                AI-Powered Document Intelligence
                            </span>

                            <h1 className="mt-6 text-4xl font-extrabold leading-tight text-navy xl:text-5xl">
                                Your content.
                                <span className="block bg-linear-to-r from-brand-orange to-brand-pink bg-clip-text text-transparent">
                                    Organized intelligently.
                                </span>
                            </h1>

                            <p className="mt-5 max-w-lg text-base leading-relaxed text-deep-purple">
                                Bring your educational documents into one workspace. Extract, structure, review, and
                                manage content through an intelligent workflow.
                            </p>
                        </div>

                        <div className="mt-8">
                            <DocumentIntelligenceArt />
                        </div>
                    </section>

                    <section className="mx-auto w-full max-w-md">
                        <div className="rounded-3xl border border-white bg-white/90 p-6 shadow-[0_20px_60px_-25px_rgba(73,50,140,0.3)] backdrop-blur sm:p-9">
                            <div className="mb-7 text-center">
                                <h2 className="text-2xl font-bold text-navy sm:text-3xl">
                                    {title}
                                </h2>
                                <p className="mt-2 text-sm leading-relaxed text-navy/60">
                                    {subtitle}
                                </p>
                            </div>

                            {children}
                        </div>
                    </section>
                </div>

                <footer className="py-3 text-center text-xs font-medium text-navy/50">
                    NEETDAY · AI-Powered Document Intelligence
                </footer>
            </div>
        </main>
    );
}
