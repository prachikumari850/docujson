
import { Bell, Menu, Search } from "lucide-react";

export default function DashboardTopbar({ title, onMenuClick }) {
    return (
        <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-lavender/70 bg-white/90 px-4 backdrop-blur sm:px-7">
            <div className="flex min-w-0 items-center gap-3">
                <button
                    type="button"
                    onClick={onMenuClick}
                    aria-label="Open navigation"
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-lavender text-navy lg:hidden"
                >
                    <Menu size={20} />
                </button>

                <div className="min-w-0">
                    <h1 className="truncate text-lg font-bold text-navy sm:text-xl">
                        {title}
                    </h1>
                    <p className="hidden text-xs text-navy/50 sm:block">
                        Manage your content and workspace
                    </p>
                </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-4">
                <button
                    type="button"
                    aria-label="Search"
                    className="flex h-10 w-10 items-center justify-center rounded-xl text-navy/60 transition hover:bg-lavender-light hover:text-deep-purple"
                >
                    <Search size={19} />
                </button>

                <button
                    type="button"
                    aria-label="Notifications"
                    className="relative flex h-10 w-10 items-center justify-center rounded-xl text-navy/60 transition hover:bg-lavender-light hover:text-deep-purple"
                >
                    <Bell size={19} />
                </button>

                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-linear-to-br from-brand-orange to-brand-pink text-sm font-bold text-white shadow-sm">
                    N
                </div>
            </div>
        </header>
    );
}
