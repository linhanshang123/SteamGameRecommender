import type {
  BucketEvidence,
  HistoryEntry,
  RankedRecommendation,
  RecommendationArchetype,
  RecommendationBuckets,
  RecommendationResponse,
  RecommendationSessionResponse,
} from "@/lib/types";

function getBackendUrl() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (!backendUrl) {
    throw new Error("NEXT_PUBLIC_BACKEND_URL is not configured.");
  }

  return backendUrl.replace(/\/$/, "");
}

async function parseJson<T>(response: Response) {
  const payload = (await response.json()) as T & { detail?: string };
  if (!response.ok) {
    throw new Error(payload.detail ?? "Backend request failed.");
  }
  return payload;
}

const EMPTY_ARCHETYPE: RecommendationArchetype = {
  summary: "",
  core_experience: [],
  required_alignment: [],
  allowed_novelty_axes: [],
  hard_drifts_to_avoid: [],
};

const EMPTY_BUCKET_EVIDENCE: BucketEvidence = {
  bucket_fit_score: 0,
  novelty_support_score: 0,
  niche_conviction_score: 0,
};

const EMPTY_BUCKETS: RecommendationBuckets = {
  closest_matches: [],
  similar_but_novel: [],
  niche_picks: [],
};

function normalizeRecommendation(
  recommendation: RankedRecommendation,
  fallbackRank: number,
): RankedRecommendation {
  const bucket = recommendation.bucket ?? "closest_matches";

  return {
    ...recommendation,
    bucket,
    bucketRank: recommendation.bucketRank ?? fallbackRank,
    bucketReason:
      recommendation.bucketReason ??
      recommendation.reason ??
      "This saved result predates recommendation-angle framing.",
    bucketEvidence:
      recommendation.bucketEvidence ??
      ({
        ...EMPTY_BUCKET_EVIDENCE,
        bucket_fit_score: recommendation.finalScore,
      } satisfies BucketEvidence),
    secondaryTraits: recommendation.secondaryTraits ?? [],
  };
}

function groupRecommendations(recommendations: RankedRecommendation[]): RecommendationBuckets {
  return {
    closest_matches: recommendations.filter((recommendation) => recommendation.bucket === "closest_matches"),
    similar_but_novel: recommendations.filter(
      (recommendation) => recommendation.bucket === "similar_but_novel",
    ),
    niche_picks: recommendations.filter((recommendation) => recommendation.bucket === "niche_picks"),
  };
}

function normalizeBucketLists(
  buckets: RecommendationBuckets | undefined,
  normalizedRecommendations: RankedRecommendation[],
): RecommendationBuckets {
  if (!buckets) {
    return groupRecommendations(normalizedRecommendations);
  }

  const normalizeBucket = (bucketRecommendations: RankedRecommendation[]) =>
    bucketRecommendations.map((recommendation, index) =>
      normalizeRecommendation(recommendation, recommendation.bucketRank ?? index + 1),
    );

  return {
    closest_matches: normalizeBucket(buckets.closest_matches ?? []),
    similar_but_novel: normalizeBucket(buckets.similar_but_novel ?? []),
    niche_picks: normalizeBucket(buckets.niche_picks ?? []),
  };
}

function normalizeRecommendationSessionResponse(
  payload: RecommendationSessionResponse,
): RecommendationSessionResponse {
  const sourceRecommendations =
    payload.recommendations?.length
      ? payload.recommendations
      : [
          ...(payload.buckets?.closest_matches ?? []),
          ...(payload.buckets?.similar_but_novel ?? []),
          ...(payload.buckets?.niche_picks ?? []),
        ];

  const normalizedRecommendations = sourceRecommendations.map((recommendation, index) =>
    normalizeRecommendation(recommendation, recommendation.rank ?? index + 1),
  );
  const normalizedBuckets = normalizeBucketLists(payload.buckets, normalizedRecommendations);
  const archetype = payload.archetype ?? payload.session.archetype ?? EMPTY_ARCHETYPE;

  return {
    ...payload,
    archetype,
    buckets:
      normalizedRecommendations.length || payload.buckets
        ? normalizedBuckets
        : EMPTY_BUCKETS,
    recommendations: normalizedRecommendations,
    session: {
      ...payload.session,
      archetype: payload.session.archetype ?? archetype,
    },
  };
}

export async function fetchHistory(userId: string) {
  const response = await fetch(`${getBackendUrl()}/history`, {
    headers: {
      "x-user-id": userId,
    },
    cache: "no-store",
  });

  return parseJson<HistoryEntry[]>(response);
}

export async function fetchRecommendationSession(sessionId: string, userId: string) {
  const response = await fetch(`${getBackendUrl()}/recommendations/${sessionId}`, {
    headers: {
      "x-user-id": userId,
    },
    cache: "no-store",
  });

  const payload = await parseJson<RecommendationSessionResponse>(response);
  return normalizeRecommendationSessionResponse(payload);
}

export type CreateRecommendationPayload = RecommendationResponse;
