import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { buildSteamOpenIdUrl } from "@/lib/steam-openid";

export async function GET(request: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }

  const requestUrl = new URL(request.url);
  const redirectUrl = buildSteamOpenIdUrl(requestUrl.origin, "/api/steam/callback");
  return NextResponse.redirect(redirectUrl);
}
