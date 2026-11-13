import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function ProtectedRoute({ children }) {
    const { status, error, refreshUser } = useAuth();
    const location = useLocation();

    if (status === "loading") {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#F8F5FF]">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-lavender border-t-deep-purple" />
            </div>
        );
    }

    if (status === "error") {
        return (
            <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#F8F5FF] px-5 text-center">
                <h2 className="text-xl font-bold text-navy">
                    Unable to verify your session
                </h2>

                <p className="max-w-md text-sm text-navy/60">
                    {error}
                </p>

                <button
                    type="button"
                    onClick={() => refreshUser().catch(() => { })}
                    className="rounded-xl bg-deep-purple px-5 py-3 text-sm font-semibold text-white transition hover:bg-navy"
                >
                    Retry
                </button>
            </div>
        );
    }

    if (status !== "authenticated") {
        return (
            <Navigate
                to="/login"
                replace
                state={{ from: location }}
            />
        );
    }

    return children;
}