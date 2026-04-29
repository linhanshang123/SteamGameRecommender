import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { createRecommendationSession } from "@/lib/recommendation/service";

export async function POST(request: Request) {
  const { userId } = await auth();

  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = (await request.json()) as { prompt?: string };
  const prompt = body.prompt?.trim();

  if (!prompt) {
    return NextResponse.json({ error: "Prompt is required." }, { status: 400 });
  }

  if (prompt.length > 800) {
    return NextResponse.json(
      { error: "Prompt must be shorter than 800 characters." },
      { status: 400 },
    );
  }

  try {
    const result = await createRecommendationSession({
      prompt,
      userId,
    });

    return NextResponse.json(result);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Recommendation generation failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
