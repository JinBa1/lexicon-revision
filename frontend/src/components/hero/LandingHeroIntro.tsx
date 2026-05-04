import { LANDING_HERO_COPY } from "@/lib/publicCopy";

export function LandingHeroIntro() {
  return (
    <div className="text-center">
      <div className="font-ui text-[11px] uppercase tracking-widest text-claret">
        {LANDING_HERO_COPY.eyebrow}
      </div>
      <h1 className="mx-auto mt-3 max-w-5xl font-display text-4xl font-semibold leading-tight text-ink sm:text-5xl lg:text-[4.8rem]">
        {LANDING_HERO_COPY.title}
      </h1>
      <p className="mx-auto mt-5 max-w-2xl font-body text-base leading-relaxed text-ink-muted">
        {LANDING_HERO_COPY.lead}
      </p>
    </div>
  );
}
