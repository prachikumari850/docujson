
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import DashboardLayout from "./components/layout/DashboardLayout";

const Home = lazy(() => import("./pages/Home"));
const Login = lazy(() => import("./pages/Login"));
const Signup = lazy(() => import("./pages/Signup"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Imports = lazy(() => import("./pages/dashboard/Imports"));
const Documents = lazy(() => import("./pages/dashboard/Documents"));
const Questions = lazy(() => import("./pages/dashboard/Questions"));
const WorkspaceSection = lazy(() => import("./pages/dashboard/WorkspaceSection"));
const Review = lazy(() => import("./pages/dashboard/Review"));
const AnswerKeys = lazy(() => import("./pages/dashboard/AnswerKeys"));
const Publishing = lazy(() => import("./pages/dashboard/Publishing"));
const Analytics = lazy(() => import("./pages/dashboard/Analytics"));
const Settings = lazy(() => import("./pages/dashboard/Settings"));

function PageLoader() {
    return (
        <div className="flex min-h-[50vh] items-center justify-center">
            <div className="h-9 w-9 animate-spin rounded-full border-4 border-lavender border-t-deep-purple" />
        </div>
    );
}

export default function App() {
    return (
        <Suspense fallback={<PageLoader />}>
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/login" element={<Login />} />
                <Route path="/signup" element={<Signup />} />
                <Route path="/forgot-password" element={<ForgotPassword />} />

                <Route path="/dashboard" element={<DashboardLayout />}>
                    <Route index element={<Dashboard />} />
                    <Route path="imports" element={<Imports />} />
                    <Route path="documents" element={<Documents />} />
                    <Route path="questions" element={<Questions />} />

                    <Route path="review" element={<Review />} />

                    <Route path="answer-keys" element={<AnswerKeys />} />

                    <Route path="publishing" element={<Publishing />} />

                    <Route path="analytics" element={<Analytics />} />

                    <Route path="settings" element={<Settings />} />
                </Route>

                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </Suspense>
    );
}
