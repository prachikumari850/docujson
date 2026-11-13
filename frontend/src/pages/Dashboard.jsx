
import { Link } from "react-router-dom";
import {
    ArrowRight,
    BarChart3,
    BookOpen,
    CheckCircle2,
    FileText,
    FolderOpen,
    Upload,
} from "lucide-react";

const OVERVIEW_CARDS = [
    {
        title: "Total Documents",
        value: "—",
        detail: "Documents in your workspace",
        icon: FolderOpen,
        color: "bg-lavender-light text-deep-purple",
    },
    {
        title: "Questions Extracted",
        value: "—",
        detail: "Questions processed",
        icon: BookOpen,
        color: "bg-pink-light text-brand-pink",
    },
    {
        title: "Pending Reviews",
        value: "—",
        detail: "Items awaiting review",
        icon: CheckCircle2,
        color: "bg-orange-100 text-brand-orange",
    },
    {
        title: "Published Content",
        value: "—",
        detail: "Approved content published",
        icon: BarChart3,
        color: "bg-sky-soft text-sky-600",
    },
];

const QUICK_ACTIONS = [
    {
        title: "Import Documents",
        description: "Upload PDFs and other supported files.",
        icon: Upload,
        path: "/dashboard/imports",
        color: "bg-lavender-light text-deep-purple",
    },
    {
        title: "Manage Documents",
        description: "Browse and organize imported documents.",
        icon: FolderOpen,
        path: "/dashboard/documents",
        color: "bg-pink-light text-brand-pink",
    },
    {
        title: "Review Questions",
        description: "Inspect and validate extracted questions.",
        icon: BookOpen,
        path: "/dashboard/review",
        color: "bg-orange-100 text-brand-orange",
    },
];

function OverviewCard({ title, value, detail, icon: Icon, color }) {
    return (
        <div className="rounded-2xl border border-lavender/70 bg-white p-5 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)]">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-sm font-medium text-navy/60">{title}</p>
                    <p className="mt-3 text-3xl font-bold text-navy">{value}</p>
                </div>
                <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${color}`}>
                    <Icon size={23} />
                </div>
            </div>
            <p className="mt-3 text-xs text-navy/45">{detail}</p>
        </div>
    );
}

function QuickAction({ title, description, icon: Icon, path, color }) {
    return (
        <Link
            to={path}
            className="group flex items-center gap-4 rounded-2xl border border-lavender/70 bg-white p-4 transition hover:-translate-y-0.5 hover:border-deep-purple/30 hover:shadow-lg hover:shadow-deep-purple/5"
        >
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${color}`}>
                <Icon size={22} />
            </div>

            <div className="min-w-0 flex-1">
                <h3 className="text-sm font-bold text-navy">{title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-navy/55">{description}</p>
            </div>

            <ArrowRight
                size={18}
                className="shrink-0 text-navy/30 transition group-hover:translate-x-1 group-hover:text-brand-pink"
            />
        </Link>
    );
}

export default function Dashboard() {
    return (
        <div className="space-y-8">
            <section className="relative overflow-hidden rounded-3xl bg-linear-to-r from-[#49328C] via-[#7652B5] to-[#C66F9F] p-6 shadow-[0_18px_40px_-20px_rgba(73,50,140,0.45)] sm:p-8">
                <div className="relative z-10 max-w-2xl">
                    <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white">
                        <span className="h-2 w-2 rounded-full bg-emerald-300" />
                        Your workspace
                    </span>

                    <h2 className="mt-4 text-2xl font-bold leading-tight text-white sm:text-3xl">
                        Welcome to NEETDAY
                    </h2>

                    <p className="mt-3 max-w-xl text-sm leading-relaxed text-white/80 sm:text-base">
                        Import your educational documents and turn them into structured, review-ready content.
                    </p>

                    <Link
                        to="/dashboard/imports"
                        className="mt-6 inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-bold text-deep-purple shadow-md transition hover:-translate-y-0.5 hover:shadow-lg"
                    >
                        <Upload size={17} />
                        Import Documents
                        <ArrowRight size={16} />
                    </Link>
                </div>

                <div className="pointer-events-none absolute -right-10 -top-20 h-72 w-72 rounded-full border-[35px] border-white/10" />
                <div className="pointer-events-none absolute -bottom-36 right-36 h-72 w-72 rounded-full border-[35px] border-white/10" />
            </section>

            <section>
                <div className="mb-4">
                    <h2 className="text-lg font-bold text-navy">Workspace Overview</h2>
                    <p className="mt-1 text-sm text-navy/55">
                        Your document and content activity will appear here.
                    </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    {OVERVIEW_CARDS.map((card) => (
                        <OverviewCard key={card.title} {...card} />
                    ))}
                </div>
            </section>

            <section>
                <div className="mb-4">
                    <h2 className="text-lg font-bold text-navy">Quick Actions</h2>
                    <p className="mt-1 text-sm text-navy/55">
                        Continue working with your educational content.
                    </p>
                </div>

                <div className="grid gap-4 lg:grid-cols-3">
                    {QUICK_ACTIONS.map((action) => (
                        <QuickAction key={action.title} {...action} />
                    ))}
                </div>
            </section>

            <section className="rounded-2xl border border-lavender/70 bg-white p-6 shadow-[0_8px_25px_-18px_rgba(73,50,140,0.3)] sm:p-8">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <h2 className="text-lg font-bold text-navy">Recent Imports</h2>
                        <p className="mt-1 text-sm text-navy/55">
                            Recently imported documents will appear here.
                        </p>
                    </div>

                    <Link
                        to="/dashboard/imports"
                        className="inline-flex items-center gap-2 text-sm font-semibold text-deep-purple transition hover:text-brand-pink"
                    >
                        View Imports
                        <ArrowRight size={16} />
                    </Link>
                </div>

                <div className="mt-7 flex flex-col items-center justify-center rounded-2xl border border-dashed border-lavender bg-[#FCFAFF] px-5 py-10 text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-lavender-light text-deep-purple">
                        <FileText size={27} />
                    </div>
                    <h3 className="mt-4 text-sm font-bold text-navy">No documents imported yet</h3>
                    <p className="mt-2 max-w-sm text-xs leading-relaxed text-navy/55">
                        Your imported documents and their processing status will be displayed here.
                    </p>
                    <Link
                        to="/dashboard/imports"
                        className="mt-5 rounded-xl bg-linear-to-r from-brand-orange to-brand-pink px-5 py-2.5 text-xs font-bold text-white shadow-sm transition hover:shadow-md"
                    >
                        Import Your First Document
                    </Link>
                </div>
            </section>
        </div>
    );
}
