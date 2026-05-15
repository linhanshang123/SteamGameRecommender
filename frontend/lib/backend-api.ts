import type {
  HistoryEntry,
  RecommendationResponse,
  RecommendationSessionResponse,
  SteamAccountStatus,
} from "@/lib/types";

const DEFAULT_BACKEND_TIMEOUT_MS = 5000;
const STEAM_ACCOUNT_TIMEOUT_MS = 1500;

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

async function fetchBackend(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_BACKEND_TIMEOUT_MS,
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(`${getBackendUrl()}${path}`, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Backend request timed out.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchHistory(userId: string) {
  const response = await fetchBackend("/history", {
    headers: {
      "x-user-id": userId,
    },
  });

  return parseJson<HistoryEntry[]>(response);
}

export async function fetchRecommendationSession(sessionId: string, userId: string) {
  const response = await fetchBackend(`/recommendations/${sessionId}`, {
    headers: {
      "x-user-id": userId,
    },
  });

  return parseJson<RecommendationSessionResponse>(response);
}

export async function fetchSteamAccountStatus(userId: string) {
  const response = await fetchBackend(
    "/steam/account",
    {
      headers: {
        "x-user-id": userId,
      },
    },
    STEAM_ACCOUNT_TIMEOUT_MS,
  );

  return parseJson<SteamAccountStatus>(response);
}

export async function linkSteamAccount(userId: string, steamId: string) {
  const response = await fetchBackend("/steam/link", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-user-id": userId,
    },
    body: JSON.stringify({ steamId }),
  });

  return parseJson<SteamAccountStatus>(response);
}

export async function refreshSteamAccount(userId: string) {
  const response = await fetchBackend("/steam/refresh", {
    method: "POST",
    headers: {
      "x-user-id": userId,
    },
  });

  return parseJson<SteamAccountStatus>(response);
}

export type CreateRecommendationPayload = RecommendationResponse;
