import type { RankedRecommendation } from "@/lib/types";

function steamHeaderImage(appid: string) {
  return `https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/${appid}/header.jpg`;
}

function steamStoreUrl(appid: string) {
  return `https://store.steampowered.com/app/${appid}/`;
}

function formatPrice(price: number | null) {
  if (price === null || price === 0) {
    return price === 0 ? "Free" : "N/A";
  }

  return `$${price.toFixed(2)}`;
}

function formatReviewCount(totalReviews: number | null) {
  return new Intl.NumberFormat("en-US", {
    notation: totalReviews && totalReviews >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(totalReviews ?? 0);
}

export function RecommendationCard({
  recommendation,
}: {
  recommendation: RankedRecommendation;
}) {
  return (
    <article className="panel overflow-hidden rounded-[1.75rem]">
      <div className="relative h-40 overflow-hidden">
        <img
          src={steamHeaderImage(recommendation.appid)}
          alt={recommendation.name}
          className="h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-transparent" />
        <div className="absolute left-4 top-4 rounded-full border border-white/15 bg-black/35 px-3 py-1 text-xs uppercase tracking-[0.25em] text-white/80">
          #{recommendation.rank}
        </div>
      </div>

      <div className="space-y-5 px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-white">{recommendation.name}</h2>
            <p className="mt-1 text-sm text-slate-300/76">
              {recommendation.year ?? "Unknown year"} · {formatPrice(recommendation.price)}
            </p>
          </div>
          <div className="rounded-2xl border border-cyan-200/18 bg-cyan-100/6 px-3 py-2 text-right">
            <p className="text-[0.65rem] uppercase tracking-[0.22em] text-slate-300/66">
              Match score
            </p>
            <p className="text-lg font-semibold text-cyan-100">
              {(recommendation.finalScore * 100).toFixed(0)}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {recommendation.tags.slice(0, 5).map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs text-slate-100/86"
            >
              {tag}
            </span>
          ))}
        </div>

        <p className="text-sm leading-6 text-slate-200/86">{recommendation.reason}</p>

        <a
          href={steamStoreUrl(recommendation.appid)}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center justify-center rounded-full border border-cyan-200/20 bg-cyan-100/8 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-200/35 hover:bg-cyan-100/14"
          aria-label={`View ${recommendation.name} on Steam`}
        >
          View on Steam
        </a>

        <dl className="grid grid-cols-2 gap-3 text-sm text-slate-300/80 md:grid-cols-3">
          <div className="rounded-2xl border border-white/8 bg-white/4 px-3 py-3">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-400">Rating</dt>
            <dd className="mt-1 text-white">
              {(recommendation.ratingRatio * 100).toFixed(0)}%
            </dd>
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/4 px-3 py-3">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-400">Tag fit</dt>
            <dd className="mt-1 text-white">
              {(recommendation.scoreBreakdown.tag_match_score * 100).toFixed(0)}%
            </dd>
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/4 px-3 py-3">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-400">Review count</dt>
            <dd className="mt-1 text-white">
              {formatReviewCount(recommendation.totalReviews)}
            </dd>
          </div>
        </dl>
      </div>
    </article>
  );
}
