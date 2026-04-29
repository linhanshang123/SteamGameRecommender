"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { env } from "@/lib/env";

export function SearchForm() {
  const { userId } = useAuth();
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const nextPrompt = prompt.trim();
    if (!nextPrompt) {
      setError("Describe the kind of game you want first.");
      return;
    }

    setIsSubmitting(true);

    try {
      if (!env.backendUrl) {
        throw new Error(
          "Backend is not configured yet. Set NEXT_PUBLIC_BACKEND_URL after Phase 2.",
        );
      }

      const response = await fetch(`${env.backendUrl}/recommendations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-user-id": userId ?? "",
        },
        body: JSON.stringify({ prompt: nextPrompt }),
      });

      const payload = (await response.json()) as { sessionId?: string; error?: string };

      if (!response.ok || !payload.sessionId) {
        throw new Error(payload.error ?? "Recommendation request failed.");
      }

      router.push(`/recommendations/${payload.sessionId}`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="panel relative mx-auto flex w-full max-w-4xl flex-col gap-4 rounded-[2rem] px-5 py-5 md:px-6"
    >
      <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-cyan-200/60 to-transparent" />
      <label htmlFor="prompt" className="text-xs uppercase tracking-[0.32em] text-slate-300/70">
        Describe your next Steam game
      </label>
      <textarea
        id="prompt"
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        placeholder="Something like Hades, but faster, cleaner, and less grindy. I want strong combat feel and stylish art."
        className="min-h-36 resize-none rounded-[1.5rem] border border-white/8 bg-slate-950/40 px-5 py-4 text-base text-white outline-none transition placeholder:text-slate-400/55 focus:border-cyan-200/45 focus:bg-slate-950/60 md:text-lg"
      />
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <p className="text-sm text-slate-300/72">
          The UI is ready for the backend split. Recommendation submission will use the FastAPI service once NEXT_PUBLIC_BACKEND_URL is configured.
        </p>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-full bg-gradient-to-r from-indigo-300 via-sky-300 to-cyan-200 px-5 py-3 text-sm font-semibold text-slate-950 shadow-[0_0_34px_rgba(116,221,255,0.25)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isSubmitting ? "Generating..." : "Get recommendations"}
        </button>
      </div>
      {error ? <p className="text-sm text-rose-300">{error}</p> : null}
    </form>
  );
}
