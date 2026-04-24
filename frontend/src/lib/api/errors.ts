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
