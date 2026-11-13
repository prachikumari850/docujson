
import { useState } from "react";
import { Bell, LogOut, Menu, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function DashboardTopbar({ title, onMenuClick }) {
    const navigate = useNavigate();
    const { user, organization, logout } = useAuth();

    const [loggingOut, setLoggingOut] = useState(false);
    const [error, setError] = useState("");

    const initials = (user?.name || "N")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase();

    const handleLogout = async () => {
        if (loggingOut) return;

        setLoggingOut(true);
        setError("");

        try {
            await logout();
            navigate("/login", { replace: true });
        } catch (err) {
            setError(err.message || "Unable to log out. Please try again.");
        } finally {
            setLoggingOut(false);
        }
    };

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
                    <p className="hidden truncate text-xs text-navy/50 sm:block">
                        {organization?.name || "Manage your workspace"}
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

                <div className="hidden min-w-0 text-right sm:block">
                    <p className="max-w-36 truncate text-sm font-semibold text-navy">
                        {user?.name || "User"}
                    </p>
                    <p className="max-w-36 truncate text-xs text-navy/50">
                        {user?.email || ""}
                    </p>
                </div>

                <div
                    title={user?.name || "User"}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-brand-orange to-brand-pink text-sm font-bold text-white shadow-sm"
                >
                    {initials}
                </div>

                <button
                    type="button"
                    onClick={handleLogout}
                    disabled={loggingOut}
                    aria-label="Log out"
                    title="Log out"
                    className="flex h-10 items-center justify-center gap-2 rounded-xl border border-lavender px-3 text-sm font-semibold text-navy transition hover:border-brand-pink hover:bg-pink-light hover:text-brand-pink disabled:cursor-not-allowed disabled:opacity-60"
                >
                    <LogOut size={17} />
                    <span className="hidden md:inline">
                        {loggingOut ? "Logging out..." : "Logout"}
                    </span>
                </button>
            </div>

            {error && (
                <div
                    role="alert"
                    className="absolute right-4 top-full mt-2 max-w-sm rounded-xl border border-red-200 bg-white px-4 py-3 text-xs text-red-600 shadow-lg"
                >
                    {error}
                </div>
            )}
        </header>
    );
}
