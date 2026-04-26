import type { StudyAnswerStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";

type BannerVariant = {
  className: string;
  title: string;
  body: string;
};

const bannerVariants: Record<Exclude<StudyAnswerStatus, "ok">, BannerVariant> = {
  partial: {
    className: "bg-paper-raised border border-rule border-l-4 border-l-claret text-ink",
    title: "Partial answer",
    body: "Some sub-questions had no strong evidence — see Limitations below.",
  },
  insufficient_evidence: {
    className: "bg-claret-soft border border-claret border-l-4 border-l-claret text-ink",
    title: "Insufficient evidence",
    body: "Try retrieving matching questions instead, or broaden your filters.",
  },
  generation_failed: {
    className: "bg-claret-soft border border-claret border-l-4 border-l-claret text-claret",
    title: "Could not generate answer",
    body: "The answer service is temporarily unavailable. Try again in a moment.",
  },
  retrieval_failed: {
    className: "bg-claret-soft border border-claret border-l-4 border-l-claret text-claret",
    title: "Retrieval failed",
    body: "Try broadening your filters or switching collection.",
  },
};

export function AnswerStatusBanner({ status }: { status: StudyAnswerStatus }) {
  if (status === "ok") return null;

  const variant = bannerVariants[status];

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("mb-4 rounded-sm px-4 py-3 font-body text-[13px]", variant.className)}
    >
      <div className="font-display text-[14px] font-bold">{variant.title}</div>
      <div className="mt-1">{variant.body}</div>
    </div>
  );
}
