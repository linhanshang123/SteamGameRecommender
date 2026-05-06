import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { env } from "@/lib/env";
import { linkSteamAccount } from "@/lib/backend-api";
import { extractSteamId, verifySteamOpenId } from "@/lib/steam-openid";

function redirectWithStatus(requestUrl: URL, status: "connected" | "error") {
  const destination = new URL("/", requestUrl.origin);
  destination.searchParams.set("steam", status);
  return NextResponse.redirect(destination);
}

export async function GET(request: Request) {
  const { userId } = await auth();
  const requestUrl = new URL(request.url);
  if (!userId) {
    return redirectWithStatus(requestUrl, "error");
  }

  const verified = await verifySteamOpenId(requestUrl.searchParams);
  if (!verified) {
    return redirectWithStatus(requestUrl, "error");
  }

  const steamId = extractSteamId(requestUrl.searchParams.get("openid.claimed_id"));
  if (!steamId) {
    return redirectWithStatus(requestUrl, "error");
  }

  try {
    if (!env.backendUrl) {
      throw new Error("Backend is not configured.");
    }
    await linkSteamAccount(userId, steamId);
    return redirectWithStatus(requestUrl, "connected");
  } catch {
    return redirectWithStatus(requestUrl, "error");
  }
}
