import { env } from "@/env";

import type { ApiErrorDetail, ValidationErrorDetail } from "./errors";
import { ApiError } from "./errors";

export type GetAuthHeaders = () => Promise<Record<string, string>>;

// `apiFetch` only accepts JSON-serializable request bodies on this branch.
export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

type ApiFetchBaseOptions = {
  path: string;
  getAuthHeaders: GetAuthHeaders;
  onUnauthorized?: () => void | Promise<void>;
  signal?: AbortSignal;
};

type ApiFetchGetOptions = ApiFetchBaseOptions & {
  method?: "GET";
  body?: undefined;
};

type ApiFetchPostOptions = ApiFetchBaseOptions & {
  method?: "POST";
  body: JsonValue;
};

export type ApiFetchOptions = ApiFetchGetOptions | ApiFetchPostOptions;

export async function apiFetch<T = unknown>(options: ApiFetchOptions): Promise<T> {
  const { path, body, getAuthHeaders, onUnauthorized, signal } = options;
  const method = options.method ?? (body === undefined ? "GET" : "POST");
  const headers = new Headers({ accept: "application/json" });
  const serializedBody = serializeRequestBody(body);

  if (method === "GET" && body !== undefined) {
    throw new ApiError({
      status: 400,
      code: "invalid_request",
      detail: "GET requests must not include a request body.",
    });
  }

  if (body !== undefined) {
    headers.set("content-type", "application/json");
  }

  const authHeaders = await getAuthHeaders();
  for (const [key, value] of Object.entries(authHeaders)) {
    headers.set(key, value);
  }

  let response: Response;
  try {
    response = await fetch(buildApiUrl(path), {
      method,
      headers,
      body: serializedBody,
      signal,
    });
  } catch (error) {
    throw normalizeFetchFailure(error);
  }

  if (response.status === 401) {
    triggerUnauthorizedSideEffect(onUnauthorized);
    throw new ApiError({ status: 401, code: "unauthorized", detail: null });
  }

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: codeFromStatus(response.status),
      detail: await readErrorDetail(response),
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return await readSuccessJson<T>(response);
}

async function readErrorDetail(response: Response): Promise<ApiErrorDetail> {
  const rawBody = await readResponseText(response);
  if (rawBody === null) {
    return null;
  }

  const trimmedBody = rawBody.trim();
  if (trimmedBody.length === 0) {
    return null;
  }

  try {
    const payload = JSON.parse(trimmedBody) as { detail?: unknown };
    if (
      typeof payload.detail === "string" ||
      payload.detail === null ||
      isValidationDetail(payload.detail) ||
      isObjectDetail(payload.detail)
    ) {
      return payload.detail;
    }
  } catch {
    return trimmedBody.slice(0, 300);
  }

  return null;
}

function isValidationDetail(value: unknown): value is ValidationErrorDetail[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        Array.isArray((item as Partial<ValidationErrorDetail>).loc) &&
        typeof (item as Partial<ValidationErrorDetail>).msg === "string" &&
        typeof (item as Partial<ValidationErrorDetail>).type === "string",
    )
  );
}

function isObjectDetail(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function buildApiUrl(path: string): string {
  return new URL(stripLeadingSlashes(path), ensureTrailingSlash(env.apiBaseUrl)).toString();
}

function ensureTrailingSlash(url: string): string {
  return url.endsWith("/") ? url : `${url}/`;
}

function stripLeadingSlashes(path: string): string {
  return path.replace(/^\/+/, "");
}

function serializeRequestBody(body: JsonValue | undefined): string | undefined {
  if (body === undefined) {
    return undefined;
  }

  try {
    return JSON.stringify(body);
  } catch {
    throw new ApiError({
      status: 400,
      code: "invalid_request",
      detail: "Request body must be valid JSON.",
    });
  }
}

async function readSuccessJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError({
      status: response.status,
      code: "invalid_response",
      detail: "Expected a JSON response body from the API.",
    });
  }
}

function triggerUnauthorizedSideEffect(
  onUnauthorized: (() => void | Promise<void>) | undefined,
): void {
  if (!onUnauthorized) return;

  void Promise.resolve()
    .then(() => onUnauthorized())
    .catch(() => {
      // Swallow sync and async side-effect failures so the caller still gets
      // the stable unauthorized ApiError contract.
    });
}

function normalizeFetchFailure(error: unknown): ApiError {
  // Transport-level failures happen before any HTTP response exists, so they
  // use status 0 with stable client codes.
  if (isAbortError(error)) {
    return new ApiError({
      status: 0,
      code: "request_aborted",
      detail: readErrorMessage(error) || "The request was aborted.",
    });
  }

  return new ApiError({
    status: 0,
    code: "network_error",
    detail: readErrorMessage(error) || "Network request failed.",
  });
}

function isAbortError(error: unknown): error is { name: string; message?: string } {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}

function readErrorMessage(error: unknown): string | null {
  return typeof error === "object" && error !== null && "message" in error
    ? typeof error.message === "string" && error.message.length > 0
      ? error.message
      : null
    : null;
}

async function readResponseText(response: Response): Promise<string | null> {
  try {
    return await response.text();
  } catch {
    return null;
  }
}

function codeFromStatus(status: number): string {
  if (status === 400 || status === 422) return "invalid_request";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 413) return "request_too_large";
  if (status === 429) return "rate_limited";
  if (status === 503) return "service_unavailable";
  if (status === 504) return "timeout";
  if (status >= 500) return "server_error";
  return "error";
}
