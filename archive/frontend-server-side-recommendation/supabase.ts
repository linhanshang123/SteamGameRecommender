import { createClient } from "@supabase/supabase-js";
import { env } from "@/lib/env";
import type { Database } from "@/lib/types";

export function createSupabaseServerClient() {
  return createClient<Database>(env.supabaseUrl, env.supabasePublishableKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  });
}
