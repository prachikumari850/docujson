
import { useState } from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import AuthLayout from "../components/auth/AuthLayout";

export default function Login() {
    const [showPassword, setShowPassword] = useState(false);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [message, setMessage] = useState("");

    const handleSubmit = (event) => {
        event.preventDefault();
        setMessage("Authentication service is not connected yet.");
    };

    return (
        <AuthLayout
            title="Welcome Back"
            subtitle="Sign in to continue to your NEETDAY workspace."
        >
            <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                    <label htmlFor="email" className="mb-2 block text-sm font-semibold text-navy">
                        Email Address
                    </label>
                    <div className="relative">
                        <Mail size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-deep-purple/50" />
                        <input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            placeholder="Enter your email"
                            autoComplete="email"
                            required
                            className="w-full rounded-xl border border-lavender bg-[#FCFAFF] py-3.5 pl-11 pr-4 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple focus:ring-2 focus:ring-lavender"
                        />
                    </div>
                </div>

                <div>
                    <div className="mb-2 flex items-center justify-between">
                        <label htmlFor="password" className="text-sm font-semibold text-navy">
                            Password
                        </label>
                        <Link
                            to="/forgot-password"
                            className="text-xs font-semibold text-brand-pink transition hover:text-brand-orange"
                        >
                            Forgot Password?
                        </Link>
                    </div>

                    <div className="relative">
                        <LockKeyhole size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-deep-purple/50" />
                        <input
                            id="password"
                            type={showPassword ? "text" : "password"}
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            placeholder="Enter your password"
                            autoComplete="current-password"
                            required
                            className="w-full rounded-xl border border-lavender bg-[#FCFAFF] py-3.5 pl-11 pr-12 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple focus:ring-2 focus:ring-lavender"
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword((visible) => !visible)}
                            aria-label={showPassword ? "Hide password" : "Show password"}
                            className="absolute right-4 top-1/2 -translate-y-1/2 text-navy/50 hover:text-deep-purple"
                        >
                            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                </div>

                {message && (
                    <p role="status" className="rounded-xl bg-sky-soft/70 px-4 py-3 text-sm text-deep-purple">
                        {message}
                    </p>
                )}

                <button
                    type="submit"
                    className="w-full rounded-xl bg-linear-to-r from-brand-orange to-brand-pink py-3.5 text-sm font-bold text-white shadow-lg shadow-brand-pink/20 transition hover:-translate-y-0.5 hover:shadow-xl"
                >
                    Sign In
                </button>

                <p className="pt-2 text-center text-sm text-navy/65">
                    Don't have an account?{" "}
                    <Link to="/signup" className="font-bold text-brand-pink hover:text-brand-orange">
                        Create Account
                    </Link>
                </p>
            </form>
        </AuthLayout>
    );
}
