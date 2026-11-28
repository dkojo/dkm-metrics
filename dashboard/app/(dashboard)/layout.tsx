import Link from "next/link";

import { logout } from "@/app/actions";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link href="/" className="font-semibold tracking-tight">
            dkm<span className="text-accent">·</span>metrics
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/experiments/new" className="btn btn-primary">
              New experiment
            </Link>
            <form action={logout}>
              <button type="submit" className="btn">Sign out</button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </>
  );
}
