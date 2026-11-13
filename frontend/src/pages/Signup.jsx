
import { useState } from "react";
import { Link } from "react-router-dom";
import { Eye, EyeOff, LockKeyhole, Mail, UserRound } from "lucide-react";
import AuthLayout from "../components/auth/AuthLayout";

export default function Signup() {
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [form, setForm] = useState({
        name: "",
        email: "",
        password: "",
        confirmPassword: "",
    });
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");

    const updateField = (event) => {
        setForm((current) => ({
            ...current,
            [event.target.name]: event.target.value,
        }));
        setError("");
        setMessage("");
    };

    const handleSubmit = (event) => {
        event.preventDefault();

        if (form.password.length < 8) {
            setError("Password must contain at least 8 characters.");
            return;
        }

        if (form.password !== form.confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        setMessage("Account creation service is not connected yet.");
    };

    return (
        <AuthLayout
            title="Create Account"
            subtitle="Create your account to get started with NEETDAY."
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="name" className="mb-2 block text-sm font-semibold text-navy">
                        Full Name
                    </label>
                    <div className="relative">
                        <UserRound size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-deep-purple/50" />
                        <input
                            id="name"
                            name="name"
                            type="text"
                            value={form.name}
                            onChange={updateField}
                            placeholder="Enter your full name"
                            autoComplete="name"
                            required
                            className="w-full rounded-xl border border-lavender bg-[#FCFAFF] py-3.5 pl-11 pr-4 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple focus:ring-2 focus:ring-lavender"
                        />
                    </div>
                </div>

                <div>
                    <label htmlFor="email" className="mb-2 block text-sm font-semibold text-navy">
                        Email Address
                    </label>
                    <div className="relative">
                        <Mail size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-deep-purple/50" />
                        <input
                            id="email"
                            name="email"
                            type="email"
                            value={form.email}
                            onChange={updateField}
                            placeholder="Enter your email"
                            autoComplete="email"
                            required
                            className="w-full rounded-xl border border-lavender bg-[#FCFAFF] py-3.5 pl-11 pr-4 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple focus:ring-2 focus:ring-lavender"
                        />
                    </div>
                </div>

                <div>
                    <label htmlFor="password" className="mb-2 block text-sm font-semibold text-navy">
                        Password
                    </label>
                    <div className="relative">
                        <LockKeyhole size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-deep-purple/50" />
                        <input
                            id="password"
                            name="password"
                            type={showPassword ? "text" : "password"}
                            value={form.password}
                            onChange={updateField}
                            placeholder="Minimum 8 characters"
                            autoComplete="new-password"
                            required
                            minLength={8}
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

                <div>
                    <label htmlFor="confirmPassword" className="mb-2 block text-sm font-semibold text-navy">
                        Confirm Password
                    </label>
                    <div className="relative">
                        <LockKeyhole size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-deep-purple/50" />
                        <input
                            id="confirmPassword"
                            name="confirmPassword"
                            type={showConfirmPassword ? "text" : "password"}
                            value={form.confirmPassword}
                            onChange={updateField}
                            placeholder="Re-enter your password"
                            autoComplete="new-password"
                            required
                            className="w-full rounded-xl border border-lavender bg-[#FCFAFF] py-3.5 pl-11 pr-12 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple focus:ring-2 focus:ring-lavender"
                        />
                        <button
                            type="button"
                            onClick={() => setShowConfirmPassword((visible) => !visible)}
                            aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                            className="absolute right-4 top-1/2 -translate-y-1/2 text-navy/50 hover:text-deep-purple"
                        >
                            {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                </div>

                {error && (
                    <p role="alert" className="rounded-xl bg-pink-light px-4 py-3 text-sm text-brand-pink">
                        {error}
                    </p>
                )}

                {message && (
                    <p role="status" className="rounded-xl bg-sky-soft/70 px-4 py-3 text-sm text-deep-purple">
                        {message}
                    </p>
                )}

                <button
                    type="submit"
                    className="w-full rounded-xl bg-linear-to-r from-brand-orange to-brand-pink py-3.5 text-sm font-bold text-white shadow-lg shadow-brand-pink/20 transition hover:-translate-y-0.5 hover:shadow-xl"
                >
                    Create Account
                </button>

                <p className="pt-2 text-center text-sm text-navy/65">
                    Already have an account?{" "}
                    <Link to="/login" className="font-bold text-brand-pink hover:text-brand-orange">
                        Sign In
                    </Link>
                </p>
            </form>
        </AuthLayout>
    );
}
