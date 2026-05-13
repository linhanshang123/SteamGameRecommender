import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { refreshSteamAccount } from "@/lib/backend-api";

function redirectWithStatus(request: Request, status: "refreshed" | "error") {
  const destination = new URL("/profile", request.url);
  destination.searchParams.set("steam", status);
  return NextResponse.redirect(destination);
}

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }

  try {
    await refreshSteamAccount(userId);
    return redirectWithStatus(request, "refreshed");
  } catch {
    return redirectWithStatus(request, "error");
  }
}
