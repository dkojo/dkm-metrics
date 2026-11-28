import { dashboardPassword } from "@/lib/session";

import { LoginForm } from "./form";

export const metadata = { title: "Sign in · dkm-metrics" };

export default async function LoginPage(props: PageProps<"/login">) {
  const { next } = await props.searchParams;
  const configured = dashboardPassword().length > 0;

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="card w-full max-w-sm p-6">
        <p className="text-lg font-semibold tracking-tight">
          dkm<span className="text-accent">·</span>metrics
        </p>
        <p className="mt-1 text-sm text-muted">Sign in to the dashboard.</p>
        {configured ? (
          <LoginForm next={typeof next === "string" ? next : "/"} />
        ) : (
          <p className="mt-4 text-sm text-bad">
            No dashboard password is set. Set <code>DKM_DASHBOARD_PASSWORD</code> and restart the dashboard.
          </p>
        )}
      </div>
    </main>
  );
}
