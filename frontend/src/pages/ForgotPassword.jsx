
import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";
import AuthLayout from "../components/auth/AuthLayout";

export default function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [message, setMessage] = useState("");

    const handleSubmit = (event) => {
        event.preventDefault();
        setMessage("Password reset service is not connected yet.");
    };

    return (
        <AuthLayout
            title="Forgot Password?"
            subtitle="Enter your registered email address to request a password reset."
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
                            onChange={(event) => {
                                setEmail(event.target.value);
                                setMessage("");
                            }}
                            placeholder="Enter your registered email"
                            autoComplete="email"
                            required
                            className="w-full rounded-xl border border-lavender bg-[#FCFAFF] py-3.5 pl-11 pr-4 text-sm text-navy outline-none transition placeholder:text-navy/35 focus:border-deep-purple focus:ring-2 focus:ring-lavender"
                        />
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
                    Request Password Reset
                </button>

                <Link
                    to="/login"
                    className="flex items-center justify-center gap-2 pt-2 text-sm font-semibold text-deep-purple transition hover:text-brand-pink"
                >
                    <ArrowLeft size={16} />
                    Back to Login
                </Link>
            </form>
        </AuthLayout>
    );
}
