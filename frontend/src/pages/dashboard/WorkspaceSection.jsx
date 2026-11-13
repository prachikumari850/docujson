
import { ArrowLeft, Construction } from "lucide-react";
import { Link } from "react-router-dom";

export default function WorkspaceSection({ title, description }) {
    return (
        <section className="rounded-3xl border border-lavender/70 bg-white p-6 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-10">
            <div className="mx-auto flex max-w-lg flex-col items-center py-12 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-lavender-light text-deep-purple">
                    <Construction size={30} />
                </div>

                <h2 className="mt-5 text-2xl font-bold text-navy">{title}</h2>

                <p className="mt-3 text-sm leading-relaxed text-navy/55">
                    {description}
                </p>

                <p className="mt-5 rounded-full bg-pink-light px-4 py-2 text-xs font-semibold text-brand-pink">
                    This section is being prepared
                </p>

                <Link
                    to="/dashboard"
                    className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-deep-purple transition hover:text-brand-pink"
                >
                    <ArrowLeft size={16} />
                    Back to Overview
                </Link>
            </div>
        </section>
    );
}
