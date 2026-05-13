import { auth, currentUser } from "@clerk/nextjs/server";
import Link from "next/link";
import { redirect } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { fetchHistory, fetchSteamAccountStatus } from "@/lib/backend-api";
import type { HistoryEntry } from "@/lib/types";

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Not yet synced";
  }

  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function formatLargeNumber(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: value >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

function collectTopTags(sessions: HistoryEntry[]) {
  const counts = new Map<string, number>();
  for (const session of sessions) {
    for (const tag of session.normalized_preferences.preferred_tags) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }

  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8);
}

function recentPromptPreview(sessions: HistoryEntry[]) {
  return sessions.slice(0, 4).map((session) => ({
    id: session.id,
    prompt: session.prompt,
    createdAt: session.created_at,
    previewTitles: session.previewTitles,
  }));
}

export default async function ProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ steam?: string }>;
}) {
  const { userId } = await auth();
  if (!userId) {
    redirect("/");
  }

  const { steam } = await searchParams;

  const [user, sessions, steamAccount] = await Promise.all([
    currentUser(),
    fetchHistory(userId),
    fetchSteamAccountStatus(userId),
  ]);

  const topTags = collectTopTags(sessions);
  const recentPrompts = recentPromptPreview(sessions);
  const connectedAtLeastOnce = steamAccount.linked;

  return (
    <main className="min-h-screen pb-16">
      <SiteHeader />
      <section className="mx-auto max-w-6xl px-6 py-8 lg:px-10">
        {steam === "refreshed" ? (
          <div className="panel mb-6 rounded-2xl border border-emerald-200/18 bg-emerald-100/8 px-5 py-4 text-sm text-emerald-50">
            Steam library sync completed. New recommendation requests will use the refreshed ownership data.
          </div>
        ) : null}
        {steam === "error" ? (
          <div className="panel mb-6 rounded-2xl border border-rose-200/18 bg-rose-100/8 px-5 py-4 text-sm text-rose-100">
            Steam library refresh failed. Check the sync status below and try again.
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="panel rounded-[2rem] px-6 py-6">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Profile</p>
            <div className="mt-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <h1 className="text-3xl font-semibold tracking-[-0.04em] text-white">
                  {user?.fullName || user?.username || "SteamRecommender user"}
                </h1>
                <p className="mt-2 text-sm text-slate-300/72">
                  {user?.primaryEmailAddress?.emailAddress || userId}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm text-slate-300/80">
                <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Searches</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {formatLargeNumber(sessions.length)}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Top tags tracked</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {formatLargeNumber(topTags.length)}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="panel rounded-[2rem] px-6 py-6">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Steam</p>
            {connectedAtLeastOnce ? (
              <div className="mt-4 space-y-4">
                <div>
                  <p className="text-lg font-semibold text-white">Steam account linked</p>
                  <p className="mt-2 text-sm text-slate-300/72">
                    Owned games are excluded by default from new recommendation requests.
                  </p>
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm text-slate-300/80">
                  <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-4">
                    <dt className="text-xs uppercase tracking-[0.18em] text-slate-400">Sync status</dt>
                    <dd className="mt-2 text-white">{steamAccount.ownershipSyncStatus || "unknown"}</dd>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-4">
                    <dt className="text-xs uppercase tracking-[0.18em] text-slate-400">Owned games</dt>
                    <dd className="mt-2 text-white">{formatLargeNumber(steamAccount.ownedGameCount)}</dd>
                  </div>
                </dl>
                <p className="text-sm text-slate-300/72">
                  Last sync: {formatDate(steamAccount.lastSyncAt)}
                </p>
                {steamAccount.ownershipSyncError ? (
                  <p className="rounded-2xl border border-amber-200/16 bg-amber-100/8 px-4 py-3 text-sm text-amber-50">
                    {steamAccount.ownershipSyncError}
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-3">
                  <a
                    href={steamAccount.profileUrl || "#"}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="rounded-full border border-emerald-200/16 bg-emerald-100/8 px-4 py-2 text-sm text-emerald-50 transition hover:border-emerald-200/28 hover:bg-emerald-100/14"
                  >
                    Open Steam profile
                  </a>
                  <form action="/api/steam/refresh" method="post">
                    <button
                      type="submit"
                      className="rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12"
                    >
                      Refresh Steam library
                    </button>
                  </form>
                </div>
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                <p className="text-sm leading-7 text-slate-300/72">
                  Link a Steam account to automatically exclude owned games and prepare long-term taste modeling from your library.
                </p>
                <Link
                  href="/api/steam/connect"
                  className="inline-flex rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12"
                >
                  Connect Steam
                </Link>
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1fr]">
          <div className="panel rounded-[2rem] px-6 py-6">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Preference signals</p>
            <h2 className="mt-4 text-2xl font-semibold tracking-[-0.03em] text-white">
              Early user profile view
            </h2>
            <p className="mt-3 text-sm leading-7 text-slate-300/72">
              This is the foundation for long-term user profiling. Right now it reflects extracted preference tags from saved searches, not a fully learned preference model yet.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              {topTags.length ? (
                topTags.map(([tag, count]) => (
                  <span
                    key={tag}
                    className="rounded-full border border-cyan-200/12 bg-cyan-100/6 px-3 py-1 text-xs text-cyan-50/92"
                  >
                    {tag} · {count}
                  </span>
                ))
              ) : (
                <p className="text-sm text-slate-300/72">
                  No tag profile yet. Run a few searches to start building preference history.
                </p>
              )}
            </div>
          </div>

          <div className="panel rounded-[2rem] px-6 py-6">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Recent activity</p>
            <div className="mt-4 space-y-3">
              {recentPrompts.length ? (
                recentPrompts.map((session) => (
                  <Link
                    key={session.id}
                    href={`/recommendations/${session.id}`}
                    className="block rounded-2xl border border-white/8 bg-white/4 px-4 py-4 transition hover:border-cyan-300/20 hover:bg-white/6"
                  >
                    <p className="line-clamp-2 text-sm leading-6 text-white">{session.prompt}</p>
                    <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-400">
                      {formatDate(session.createdAt)}
                    </p>
                    {session.previewTitles.length ? (
                      <p className="mt-2 text-sm text-slate-300/72">
                        {session.previewTitles.join(" · ")}
                      </p>
                    ) : null}
                  </Link>
                ))
              ) : (
                <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-8 text-sm text-slate-300/72">
                  No saved recommendation sessions yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
