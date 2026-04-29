const requiredClientEnv = [
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
] as const;

for (const key of requiredClientEnv) {
  if (!process.env[key]) {
    console.warn(`Missing environment variable: ${key}`);
  }
}

export const env = {
  clerkPublishableKey: process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
  clerkSecretKey: process.env.CLERK_SECRET_KEY ?? "",
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabasePublishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
  backendUrl: process.env.NEXT_PUBLIC_BACKEND_URL ?? "",
  openAiApiKey: process.env.OPENAI_API_KEY ?? "",
};
