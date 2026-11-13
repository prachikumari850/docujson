
import { NavLink } from "react-router-dom";
import {
    BarChart3,
    BookOpen,
    ChevronLeft,
    ClipboardCheck,
    FileText,
    FolderOpen,
    LayoutDashboard,
    Library,
    Settings,
    Upload,
    X,
} from "lucide-react";
import { LogoMark } from "../../assets/illustrations";

const NAVIGATION = [
    {
        label: "Overview",
        path: "/dashboard",
        icon: LayoutDashboard,
        end: true,
    },
    {
        label: "Imports",
        path: "/dashboard/imports",
        icon: Upload,
    },
    {
        label: "Documents",
        path: "/dashboard/documents",
        icon: FolderOpen,
    },
    {
        label: "Questions",
        path: "/dashboard/questions",
        icon: BookOpen,
    },
    {
        label: "Review",
        path: "/dashboard/review",
        icon: ClipboardCheck,
    },
    {
        label: "Answer Keys",
        path: "/dashboard/answer-keys",
        icon: FileText,
    },
    {
        label: "Publishing",
        path: "/dashboard/publishing",
        icon: Library,
    },
    {
        label: "Analytics",
        path: "/dashboard/analytics",
        icon: BarChart3,
    },
];

export default function DashboardSidebar({ mobileOpen, onClose }) {
    return (
        <>
            {mobileOpen && (
                <button
                    type="button"
                    aria-label="Close navigation"
                    onClick={onClose}
                    className="fixed inset-0 z-40 bg-navy/40 backdrop-blur-sm lg:hidden"
                />
            )}

            <aside
                className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-lavender bg-white transition-transform duration-300 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"
                    }`}
            >
                <div className="flex h-20 items-center justify-between border-b border-lavender/70 px-6">
                    <a href="/" className="flex items-center gap-2.5">
                        <LogoMark className="h-9 w-9" />
                        <span className="text-2xl font-extrabold tracking-tight text-navy">
                            NEET<span className="text-brand-orange">DAY</span>
                        </span>
                    </a>

                    <button
                        type="button"
                        aria-label="Close navigation"
                        onClick={onClose}
                        className="rounded-lg p-2 text-navy/60 hover:bg-lavender-light lg:hidden"
                    >
                        <X size={20} />
                    </button>
                </div>

                <div className="px-5 pt-7">
                    <p className="mb-3 px-3 text-[11px] font-bold uppercase tracking-[0.14em] text-navy/40">
                        Workspace
                    </p>

                    <nav className="space-y-1" aria-label="Dashboard navigation">
                        {NAVIGATION.map(({ label, path, icon: Icon, end }) => (
                            <NavLink
                                key={path}
                                to={path}
                                end={end}
                                onClick={onClose}
                                className={({ isActive }) =>
                                    `flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-semibold transition ${isActive
                                        ? "bg-linear-to-r from-lavender to-pink-light text-deep-purple shadow-sm"
                                        : "text-navy/65 hover:bg-lavender-light hover:text-navy"
                                    }`
                                }
                            >
                                <Icon size={19} strokeWidth={1.9} />
                                {label}
                            </NavLink>
                        ))}
                    </nav>
                </div>

                <div className="mt-auto p-5">
                    <NavLink
                        to="/dashboard/settings"
                        onClick={onClose}
                        className={({ isActive }) =>
                            `flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-semibold transition ${isActive
                                ? "bg-lavender-light text-deep-purple"
                                : "text-navy/65 hover:bg-lavender-light hover:text-navy"
                            }`
                        }
                    >
                        <Settings size={19} />
                        Settings
                    </NavLink>

                    <div className="mt-4 rounded-2xl bg-linear-to-br from-lavender-light to-pink-light/70 p-4">
                        <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-deep-purple">
                                NEETDAY Workspace
                            </span>
                            <ChevronLeft size={16} className="rotate-180 text-deep-purple/60" />
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-navy/60">
                            Your document intelligence workspace.
                        </p>
                    </div>
                </div>
            </aside>
        </>
    );
}
