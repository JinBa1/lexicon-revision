export type ApiErrorInit = {
  status: number;
  code: string;
  detail: ApiErrorDetail;
};

export type ValidationErrorDetail = {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
};

export type ApiErrorObjectDetail = Record<string, unknown>;

export type ApiErrorDetail = string | ValidationErrorDetail[] | ApiErrorObjectDetail | null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: ApiErrorDetail;

  constructor(init: ApiErrorInit) {
    super(typeof init.detail === "string" && init.detail.length > 0 ? init.detail : init.code);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.detail = init.detail;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function isRateLimitBackoffError(error: unknown): boolean {
  if (!isApiError(error)) {
    return false;
  }
  if (error.status === 429) {
    return true;
  }
  if (error.status !== 503) {
    return false;
  }

  const { detail } = error;
  return (
    detail !== null &&
    typeof detail === "object" &&
    !Array.isArray(detail) &&
    detail.code === "rate_limit_unavailable"
  );
}
