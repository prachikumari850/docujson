import { useEffect, useState } from "react";
import { House, Menu, Settings, X } from "lucide-react";
import { LogoMark } from "../assets/illustrations";
import { checkHealth } from "../services/converterApi";

const LINKS = [
    { label: "Home", href: "#home", icon: House },
    { label: "Features", href: "#features" },
    { label: "How It Works", href: "#how-it-works" },
    { label: "Examples", href: "#examples" },
];

function describeOllama(ollama) {
    if (!ollama?.enabled) return "Disabled";
    return ollama.available ? `Ready (${ollama.model})` : "Not running";
}

function StatusRow({ label, value, good }) {
    return (
        <div className="flex items-center justify-between gap-6 text-sm">
            <span className="text-navy/70">{label}</span>
            <span className={`font-semibold ${good ? "text-emerald-600" : "text-brand-pink"}`}>{value}</span>
        </div>
    );
}

function SettingsPanel() {
    const [health, setHealth] = useState(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        const controller = new AbortController();
        checkHealth(controller.signal)
            .then(setHealth)
            .catch(() => {
                if (!controller.signal.aborted) setFailed(true);
            });
        return () => controller.abort();
    }, []);

    const loading = !health && !failed;

    return (
        <div className="absolute right-0 top-14 z-50 w-72 space-y-3 rounded-2xl border border-lavender bg-white p-4 shadow-xl">
            <p className="text-sm font-bold text-navy">System status</p>
            {loading && <p className="text-sm text-navy/60">Checking…</p>}
            <StatusRow label="Backend" value={failed ? "Offline" : health ? "Online" : "…"} good={!failed && !!health} />
            {health && (
                <StatusRow
                    label="Ollama (optional)"
                    value={describeOllama(health.ollama)}
                    good={health.ollama?.enabled && health.ollama?.available}
                />
            )}
        </div>
    );
}

export default function Navbar() {
    const [active, setActive] = useState("Home");
    const [menuOpen, setMenuOpen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);

    const handleNavigate = (label) => {
        setActive(label);
        setMenuOpen(false);
    };

    return (
        <header className="sticky top-0 z-40 border-b border-lavender/80 bg-white/85 backdrop-blur">
            <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
                <a href="#home" className="flex items-center gap-2.5" onClick={() => handleNavigate("Home")}>
                    <LogoMark className="h-9 w-9" />
                    <span className="text-2xl font-extrabold tracking-tight text-navy">
                        Docu<span className="text-brand-orange">JSON</span>
                    </span>
                </a>

                <nav className="hidden items-center gap-2 md:flex" aria-label="Primary">
                    {LINKS.map(({ label, href, icon: Icon }) => (
                        <a
                            key={label}
                            href={href}
                            onClick={() => handleNavigate(label)}
                            className={`flex items-center gap-2 rounded-xl px-4 py-2 text-[15px] font-semibold transition ${active === label
                                ? "bg-linear-to-r from-lavender to-pink-light text-navy shadow-sm"
                                : "text-navy hover:bg-lavender-light"
                                }`}
                        >
                            {Icon && <Icon size={18} />}
                            {label}
                        </a>
                    ))}
                </nav>

                <div className="relative flex items-center gap-2">
                    <button
                        type="button"
                        aria-label="Open settings"
                        aria-expanded={settingsOpen}
                        onClick={() => setSettingsOpen((open) => !open)}
                        className="flex h-10 w-10 items-center justify-center rounded-xl border border-lavender bg-white text-navy shadow-sm transition hover:bg-lavender-light"
                    >
                        <Settings size={20} />
                    </button>
                    <button
                        type="button"
                        aria-label="Toggle menu"
                        aria-expanded={menuOpen}
                        onClick={() => setMenuOpen((open) => !open)}
                        className="flex h-10 w-10 items-center justify-center rounded-xl border border-lavender bg-white text-navy md:hidden"
                    >
                        {menuOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>
                    {settingsOpen && <SettingsPanel />}
                </div>
            </div>

            {menuOpen && (
                <nav className="border-t border-lavender bg-white px-4 py-3 md:hidden" aria-label="Mobile">
                    {LINKS.map(({ label, href }) => (
                        <a
                            key={label}
                            href={href}
                            onClick={() => handleNavigate(label)}
                            className="block rounded-xl px-4 py-3 text-base font-semibold text-navy hover:bg-lavender-light"
                        >
                            {label}
                        </a>
                    ))}
                </nav>
            )}
        </header>
    );
}