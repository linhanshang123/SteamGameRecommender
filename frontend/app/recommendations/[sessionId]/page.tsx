import { auth } from "@clerk/nextjs/server";
import Link from "next/link";
import { redirect } from "next/navigation";
import { RecommendationCard } from "@/components/recommendation-card";
import { SiteHeader } from "@/components/site-header";
import { fetchRecommendationSession } from "@/lib/backend-api";
import type { RecommendationArchetype, RecommendationBuckets } from "@/lib/types";

const BUCKETS = [
  {
    key: "closest_matches",
    title: "Closest Matches",
    description: "The same-direction answers with the least structural drift.",
  },
  {
    key: "similar_but_novel",
    title: "Similar But Novel",
    description: "The core feel is still there, but one fresh angle justifies the pick.",
  },
  {
    key: "niche_picks",
    title: "Niche Picks",
    description: "Higher-variance bets with one standout reason to take the gamble.",
  },
] as const;

const EMPTY_ARCHETYPE: RecommendationArchetype = {
  summary: "",
  core_experience: [],
  required_alignment: [],
  allowed_novelty_axes: [],
  hard_drifts_to_avoid: [],
};

const EMPTY_BUCKETS: RecommendationBuckets = {
  closest_matches: [],
  similar_but_novel: [],
  niche_picks: [],
};

export default async function RecommendationSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { userId } = await auth();
  if (!userId) {
    redirect("/");
  }

  const { sessionId } = await params;
  const session = await fetchRecommendationSession(sessionId, userId);
  const archetype = session.archetype ?? session.session.archetype ?? EMPTY_ARCHETYPE;
  const buckets = session.buckets ?? EMPTY_BUCKETS;

  return (
    <main className="min-h-screen pb-16">
      <SiteHeader />
      <section className="mx-auto max-w-6xl px-6 py-8 lg:px-10">
        <div className="panel rounded-[2rem] px-6 py-6">
          <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Prompt</p>
          <h1 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white">
            {session.session.prompt}
          </h1>
          <div className="mt-5 flex flex-wrap gap-2">
            {session.session.normalized_preferences.preferred_tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-cyan-200/12 bg-cyan-100/6 px-3 py-1 text-xs text-cyan-50/92"
              >
                {tag}
              </span>
            ))}
            {!session.session.normalized_preferences.preferred_tags.length ? (
              <span className="text-sm text-slate-300/72">
                No exact Steam tags were extracted, so text fit carries more weight here.
              </span>
            ) : null}
          </div>
          <div className="mt-5">
            <Link
              href="/"
              className="rounded-full border border-white/12 bg-white/6 px-4 py-2 text-sm text-white"
            >
              Run another search
            </Link>
          </div>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.2fr,0.8fr]">
          <div className="panel rounded-[2rem] px-6 py-6">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Target archetype</p>
            {archetype.summary ? (
              <p className="mt-4 text-lg leading-8 text-white">{archetype.summary}</p>
            ) : (
              <p className="mt-4 text-sm leading-7 text-slate-300/72">
                This saved session predates archetype framing, so only the recommendation list is
                available.
              </p>
            )}
          </div>
          <div className="panel rounded-[2rem] px-6 py-6">
            <p className="text-sm uppercase tracking-[0.28em] text-slate-400">Hard drifts to avoid</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {archetype.hard_drifts_to_avoid.length ? (
                archetype.hard_drifts_to_avoid.map((item) => (
                  <span
                    key={item}
                    className="rounded-full border border-rose-200/14 bg-rose-100/8 px-3 py-1 text-xs text-rose-50/92"
                  >
                    {item}
                  </span>
                ))
              ) : (
                <span className="text-sm text-slate-300/72">
                  No strong drift filters were inferred for this query.
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-8 space-y-8">
          {BUCKETS.map((bucket) => {
            const recommendations = buckets[bucket.key];
            return (
              <section key={bucket.key} className="space-y-4">
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">
                      {bucket.title}
                    </h2>
                    <p className="mt-2 text-sm text-slate-300/76">{bucket.description}</p>
                  </div>
                  <p className="text-sm uppercase tracking-[0.22em] text-slate-500">
                    {recommendations.length} result{recommendations.length === 1 ? "" : "s"}
                  </p>
                </div>
                {recommendations.length ? (
                  <div className="grid gap-5">
                    {recommendations.map((recommendation) => (
                      <RecommendationCard
                        key={recommendation.appid}
                        recommendation={recommendation}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="panel rounded-[1.75rem] px-5 py-5 text-sm text-slate-300/74">
                    No candidate earned this angle cleanly enough to show it.
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </section>
    </main>
  );
}
