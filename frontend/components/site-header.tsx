import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";
import { fetchSteamAccountStatus } from "@/lib/backend-api";

const navItems = [
  { href: "/", label: "Discover" },
  { href: "/history", label: "History" },
] as const;

export async function SiteHeader() {
  const { userId } = await auth();
  let steamAccount = null;
  if (userId) {
    try {
      steamAccount = await fetchSteamAccountStatus(userId);
    } catch {
      steamAccount = null;
    }
  }

  return (
    <header className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
      <Link href="/" className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-2xl border border-white/10 bg-white/6 shadow-[0_0_36px_rgba(121,183,255,0.22)]" />
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-slate-300/70">Steam</p>
          <p className="text-lg font-semibold tracking-[0.06em] text-white">Recommender</p>
        </div>
      </Link>

      <nav className="hidden items-center gap-3 md:flex">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200/88 transition hover:border-cyan-300/30 hover:bg-white/10"
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <SignedOut>
          <Link
            href="/sign-in"
            className="rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="rounded-full bg-gradient-to-r from-indigo-300 via-sky-300 to-cyan-200 px-4 py-2 text-sm font-medium text-slate-950 shadow-[0_0_28px_rgba(142,167,255,0.35)] transition hover:brightness-105"
          >
            Create account
          </Link>
        </SignedOut>
        <SignedIn>
          <Link
            href="/profile"
            className="rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12"
          >
            Profile
          </Link>
          {steamAccount?.linked ? (
            <a
              href={steamAccount.profileUrl ?? "/"}
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-full border border-emerald-200/16 bg-emerald-100/8 px-4 py-2 text-sm text-emerald-50 transition hover:border-emerald-200/28 hover:bg-emerald-100/14"
            >
              Steam linked
            </a>
          ) : (
            <Link
              href="/api/steam/connect"
              className="rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12"
            >
              Connect Steam
            </Link>
          )}
          <UserButton afterSignOutUrl="/" />
        </SignedIn>
      </div>
    </header>
  );
}
