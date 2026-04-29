import { auth } from "@clerk/nextjs/server";
import Link from "next/link";
import { redirect } from "next/navigation";
import { RecommendationCard } from "@/components/recommendation-card";
import { SiteHeader } from "@/components/site-header";
import { fetchRecommendationSession } from "@/lib/backend-api";

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

        <div className="mt-8 grid gap-5">
          {session.recommendations.map((recommendation) => (
            <RecommendationCard key={recommendation.appid} recommendation={recommendation} />
          ))}
        </div>
      </section>
    </main>
  );
}
