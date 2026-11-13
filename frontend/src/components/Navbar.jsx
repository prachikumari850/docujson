
import { useState } from "react";
import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { LogoMark } from "../assets/illustrations";

const LINKS = [
    { label: "Home", href: "#home" },
    { label: "Features", href: "#features" },
    { label: "How It Works", href: "#how-it-works" },
];

export default function Navbar() {
    const [menuOpen, setMenuOpen] = useState(false);

    return (
        <header className="sticky top-0 z-40 border-b border-lavender/80 bg-white/85 backdrop-blur">
            <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
                <a href="#home" className="flex items-center gap-2.5">
                    <LogoMark className="h-9 w-9" />
                    <span className="text-2xl font-extrabold tracking-tight text-navy">
                        NEET<span className="text-brand-orange">DAY</span>
                    </span>
                </a>

                <nav className="hidden items-center gap-2 md:flex" aria-label="Primary navigation">
                    {LINKS.map(({ label, href }) => (
                        <a
                            key={label}
                            href={href}
                            className="rounded-xl px-4 py-2 text-[15px] font-semibold text-navy transition hover:bg-lavender-light"
                        >
                            {label}
                        </a>
                    ))}
                </nav>

                <div className="hidden items-center gap-3 md:flex">
                    <Link
                        to="/login"
                        className="rounded-xl px-4 py-2.5 text-sm font-semibold text-navy transition hover:bg-lavender-light"
                    >
                        Login
                    </Link>
                    <Link
                        to="/signup"
                        className="rounded-xl bg-linear-to-r from-brand-orange to-brand-pink px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:-translate-y-0.5 hover:shadow-lg"
                    >
                        Get Started
                    </Link>
                </div>

                <button
                    type="button"
                    aria-label={menuOpen ? "Close menu" : "Open menu"}
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen((open) => !open)}
                    className="flex h-10 w-10 items-center justify-center rounded-xl border border-lavender bg-white text-navy md:hidden"
                >
                    {menuOpen ? <X size={20} /> : <Menu size={20} />}
                </button>
            </div>

            {menuOpen && (
                <nav className="space-y-1 border-t border-lavender bg-white px-4 py-4 md:hidden" aria-label="Mobile navigation">
                    {LINKS.map(({ label, href }) => (
                        <a
                            key={label}
                            href={href}
                            onClick={() => setMenuOpen(false)}
                            className="block rounded-xl px-4 py-3 text-base font-semibold text-navy transition hover:bg-lavender-light"
                        >
                            {label}
                        </a>
                    ))}
                    <div className="grid grid-cols-2 gap-3 pt-3">
                        <Link
                            to="/login"
                            onClick={() => setMenuOpen(false)}
                            className="rounded-xl border border-lavender px-4 py-3 text-center text-sm font-semibold text-navy"
                        >
                            Login
                        </Link>
                        <Link
                            to="/signup"
                            onClick={() => setMenuOpen(false)}
                            className="rounded-xl bg-linear-to-r from-brand-orange to-brand-pink px-4 py-3 text-center text-sm font-semibold text-white"
                        >
                            Get Started
                        </Link>
                    </div>
                </nav>
            )}
        </header>
    );
}
