import Link from "next/link";
import type { ParsedUserIntent } from "@/lib/types";

export function HistorySessionCard({
  session,
}: {
  session: {
    id: string;
    prompt: string;
    created_at: string;
    normalized_preferences: ParsedUserIntent;
    previewTitles: string[];
  };
}) {
  return (
    <Link
      href={`/recommendations/${session.id}`}
      className="panel block rounded-[1.75rem] px-5 py-5 transition hover:-translate-y-0.5"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
            {new Date(session.created_at).toLocaleString()}
          </p>
          <h2 className="mt-2 text-lg font-semibold text-white">{session.prompt}</h2>
        </div>
        <span className="rounded-full border border-white/10 bg-white/6 px-3 py-1 text-xs text-slate-200/86">
          {session.normalized_preferences.preferred_tags.length} mapped tags
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {session.previewTitles.length ? (
          session.previewTitles.map((title) => (
            <span
              key={title}
              className="rounded-full border border-cyan-200/12 bg-cyan-100/6 px-3 py-1 text-xs text-cyan-50/90"
            >
              {title}
            </span>
          ))
        ) : (
          <span className="text-sm text-slate-300/72">No preview titles stored yet.</span>
        )}
      </div>
    </Link>
  );
}
