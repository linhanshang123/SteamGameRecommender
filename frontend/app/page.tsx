import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/nextjs";
import { SearchForm } from "@/components/search-form";
import { SiteHeader } from "@/components/site-header";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ steam?: string }>;
}) {
  const { steam } = await searchParams;

  return (
    <main className="min-h-screen overflow-hidden">
      <div className="absolute inset-x-0 top-24 mx-auto h-[520px] max-w-5xl rounded-full bg-[radial-gradient(circle,_rgba(172,126,255,0.32),_transparent_44%)] blur-3xl" />
      <div className="absolute left-1/2 top-[24rem] h-72 w-72 -translate-x-1/2 rounded-full bg-[radial-gradient(circle,_rgba(255,196,110,0.22),_transparent_52%)] blur-3xl" />

      <SiteHeader />

      <section className="relative z-10 mx-auto flex max-w-7xl flex-col px-6 pb-24 pt-10 lg:px-10 lg:pt-14">
        {steam === "connected" ? (
          <div className="panel mx-auto mb-6 w-full max-w-4xl rounded-2xl border border-emerald-200/18 bg-emerald-100/8 px-5 py-4 text-sm text-emerald-50">
            Steam account linked. Future recommendation requests will exclude owned games by default.
          </div>
        ) : null}
        {steam === "error" ? (
          <div className="panel mx-auto mb-6 w-full max-w-4xl rounded-2xl border border-rose-200/18 bg-rose-100/8 px-5 py-4 text-sm text-rose-100">
            Steam linking failed. Try again, and make sure the app can reach the backend and Steam OpenID.
          </div>
        ) : null}

        <div className="mx-auto max-w-4xl text-center">
          <p className="text-sm uppercase tracking-[0.4em] text-slate-300/62">SteamRecommender</p>
          <h1 className="text-balance mt-6 text-5xl font-semibold tracking-[-0.05em] text-white md:text-7xl">
            Find the Steam game that matches the feeling in your head.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-8 text-slate-200/72 md:text-lg">
            Describe the combat, pace, art style, or mood you want. The app maps that intent to Steam tags, searches the local catalog, and ranks candidates with a transparent formula.
          </p>
        </div>

        <div className="mt-10">
          <SignedIn>
            <SearchForm />
          </SignedIn>
          <SignedOut>
            <div className="panel mx-auto flex max-w-3xl flex-col items-center gap-5 rounded-[2rem] px-6 py-8 text-center">
              <p className="max-w-2xl text-base leading-7 text-slate-200/76">
                Sign in to save recommendation history and generate ranked results from the Steam catalog.
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                <SignInButton mode="modal">
                  <button className="rounded-full bg-gradient-to-r from-indigo-300 via-sky-300 to-cyan-200 px-5 py-3 text-sm font-semibold text-slate-950">
                    Sign in to start
                  </button>
                </SignInButton>
                <SignUpButton mode="modal">
                  <button className="rounded-full border border-white/12 bg-white/6 px-5 py-3 text-sm text-white">
                    Create account
                  </button>
                </SignUpButton>
              </div>
            </div>
          </SignedOut>
        </div>

        <div className="mx-auto mt-14 grid w-full max-w-5xl gap-4 md:grid-cols-3">
          {[
            {
              title: "Catalog grounded",
              description: "Recommendations come from the imported Steam dataset, not from free-form LLM guesses.",
            },
            {
              title: "Weighted ranking",
              description: "Every result is scored from tag fit, text fit, rating confidence, popularity reliability, and optional history.",
            },
            {
              title: "History ready",
              description: "Each search is attached to the signed-in user so previous recommendation sessions stay visible.",
            },
          ].map((item) => (
            <article key={item.title} className="panel rounded-[1.5rem] px-5 py-5">
              <h2 className="text-lg font-semibold text-white">{item.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-300/72">{item.description}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
