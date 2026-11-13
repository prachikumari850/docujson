import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";
import {
    getCurrentUser,
    logout as logoutApi,
} from "../services/authApi";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [organization, setOrganization] = useState(null);
    const [status, setStatus] = useState("loading");
    const [error, setError] = useState("");

    const applyAuthResponse = useCallback((data) => {
        setUser(data.user);
        setOrganization(data.organization);
        setError("");
        setStatus("authenticated");
    }, []);

    const clearAuth = useCallback(() => {
        setUser(null);
        setOrganization(null);
        setError("");
        setStatus("unauthenticated");
    }, []);

    const refreshUser = useCallback(async () => {
        setStatus("loading");
        setError("");

        try {
            const data = await getCurrentUser();
            applyAuthResponse(data);
            return data;
        } catch (err) {
            if (err.status === 401) {
                clearAuth();
                return null;
            }

            setStatus("error");
            setError(err.message || "Unable to verify your session.");
            throw err;
        }
    }, [applyAuthResponse, clearAuth]);

    useEffect(() => {
        let active = true;

        getCurrentUser()
            .then((data) => {
                if (active) {
                    applyAuthResponse(data);
                }
            })
            .catch((err) => {
                if (!active) return;

                if (err.status === 401) {
                    clearAuth();
                    return;
                }

                setStatus("error");
                setError(err.message || "Unable to verify your session.");
            });

        return () => {
            active = false;
        };
    }, [applyAuthResponse, clearAuth]);

    const logout = useCallback(async () => {
        await logoutApi();
        clearAuth();
    }, [clearAuth]);

    const value = useMemo(
        () => ({
            user,
            organization,
            status,
            error,
            refreshUser,
            logout,
        }),
        [user, organization, status, error, refreshUser, logout]
    );

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);

    if (!context) {
        throw new Error("useAuth must be used inside AuthProvider.");
    }

    return context;
}