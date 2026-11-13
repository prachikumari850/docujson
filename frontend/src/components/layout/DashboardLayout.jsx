
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import DashboardSidebar from "./DashboardSidebar";
import DashboardTopbar from "./DashboardTopbar";

const PAGE_TITLES = {
    "/dashboard": "Overview",
    "/dashboard/imports": "Imports",
    "/dashboard/documents": "Documents",
    "/dashboard/questions": "Questions",
    "/dashboard/review": "Review Content",
    "/dashboard/answer-keys": "Answer Keys",
    "/dashboard/publishing": "Publishing",
    "/dashboard/analytics": "Analytics",
    "/dashboard/settings": "Settings",
};

export default function DashboardLayout() {
    const [mobileOpen, setMobileOpen] = useState(false);
    const { pathname } = useLocation();
    const title = PAGE_TITLES[pathname] || "Workspace";

    return (
        <div className="flex min-h-screen bg-[#F8F5FF]">
            <DashboardSidebar
                mobileOpen={mobileOpen}
                onClose={() => setMobileOpen(false)}
            />

            <div className="min-w-0 flex-1">
                <DashboardTopbar
                    title={title}
                    onMenuClick={() => setMobileOpen(true)}
                />

                <main className="mx-auto w-full max-w-[1600px] p-4 sm:p-7 lg:p-9">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
