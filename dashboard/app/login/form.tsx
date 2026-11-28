"use client";

import { useActionState } from "react";

import { login, type FormState } from "@/app/actions";

export function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState<FormState, FormData>(login, { error: null });

  return (
    <form action={action} className="mt-5 space-y-4">
      <input type="hidden" name="next" value={next} />
      <div>
        <label className="label" htmlFor="password">Password</label>
        <input
          id="password" name="password" type="password" required autoFocus
          autoComplete="current-password" className="input"
        />
      </div>
      {state.error && <p className="text-sm text-bad">{state.error}</p>}
      <button type="submit" disabled={pending} className="btn btn-primary w-full justify-center">
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
