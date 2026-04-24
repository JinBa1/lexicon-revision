import type { StudyAnswerStatus } from "@/lib/api/types";

export function AnswerStatusBanner({ status }: { status: StudyAnswerStatus }) {
  if (status === "ok") return null;
  const copy = statusCopy(status);
  return (
    <div className="mb-4 rounded-sm border border-claret bg-claret-soft px-4 py-3 font-display text-[13px] text-claret">
      {copy}
    </div>
  );
}

function statusCopy(status: Exclude<StudyAnswerStatus, "ok">): string {
  switch (status) {
    case "partial":
      return "Partial answer — see limitations.";
    case "insufficient_evidence":
      return "Insufficient evidence — consider retrieving matching questions instead.";
    case "generation_failed":
      return "The answer service is temporarily unavailable.";
    case "retrieval_failed":
      return "Retrieval failed. Try broadening filters or switching collection.";
    default:
      return assertNever(status);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled answer status: ${value}`);
}
