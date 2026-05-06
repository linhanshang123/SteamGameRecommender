import type {
  HistoryEntry,
  RecommendationResponse,
  RecommendationSessionResponse,
  SteamAccountStatus,
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

  return parseJson<RecommendationSessionResponse>(response);
}

export async function fetchSteamAccountStatus(userId: string) {
  const response = await fetch(`${getBackendUrl()}/steam/account`, {
    headers: {
      "x-user-id": userId,
    },
    cache: "no-store",
  });

  return parseJson<SteamAccountStatus>(response);
}

export async function linkSteamAccount(userId: string, steamId: string) {
  const response = await fetch(`${getBackendUrl()}/steam/link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-user-id": userId,
    },
    body: JSON.stringify({ steamId }),
    cache: "no-store",
  });

  return parseJson<SteamAccountStatus>(response);
}

export type CreateRecommendationPayload = RecommendationResponse;
