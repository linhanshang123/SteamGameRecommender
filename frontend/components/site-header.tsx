import Link from "next/link";
import { SignedIn, SignedOut, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";

const navItems = [
  { href: "/", label: "Discover" },
  { href: "/history", label: "History" },
] as const;

export function SiteHeader() {
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
          <SignInButton mode="modal">
            <button className="rounded-full border border-white/12 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12">
              Sign in
            </button>
          </SignInButton>
          <SignUpButton mode="modal">
            <button className="rounded-full bg-gradient-to-r from-indigo-300 via-sky-300 to-cyan-200 px-4 py-2 text-sm font-medium text-slate-950 shadow-[0_0_28px_rgba(142,167,255,0.35)] transition hover:brightness-105">
              Create account
            </button>
          </SignUpButton>
        </SignedOut>
        <SignedIn>
          <UserButton afterSignOutUrl="/" />
        </SignedIn>
      </div>
    </header>
  );
}
