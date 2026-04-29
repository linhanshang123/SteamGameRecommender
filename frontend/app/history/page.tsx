import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { HistorySessionCard } from "@/components/history-session-card";
import { SiteHeader } from "@/components/site-header";
import { fetchHistory } from "@/lib/backend-api";

export default async function HistoryPage() {
  const { userId } = await auth();
  if (!userId) {
    redirect("/");
  }

  const sessions = await fetchHistory(userId);

  return (
    <main className="min-h-screen pb-16">
      <SiteHeader />
      <section className="mx-auto max-w-6xl px-6 py-8 lg:px-10">
        <div className="max-w-3xl">
          <p className="text-sm uppercase tracking-[0.32em] text-slate-400">History</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white">
            Saved recommendation sessions
          </h1>
          <p className="mt-4 text-base leading-7 text-slate-200/72">
            Reopen previous prompts, inspect mapped tags, and compare the top-ranked Steam matches over time.
          </p>
        </div>

        <div className="mt-10 grid gap-4">
          {sessions.length ? (
            sessions.map((session) => <HistorySessionCard key={session.id} session={session} />)
          ) : (
            <div className="panel rounded-[1.75rem] px-6 py-10 text-slate-300/72">
              No recommendation history yet. Run a prompt from the homepage first.
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
