export type Env = {
  apiBaseUrl: string;
  authMode: "stub_header" | "clerk";
  stubAuthEmail: string | null;
  clerkPublishableKey: string;
  buildSha: string;
};

function required(name: string, value: string | undefined): string {
  if (!value || value.trim() === "") {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

function optional(value: string | undefined): string {
  return value?.trim() ?? "";
}

function parseAuthMode(value: string | undefined): Env["authMode"] {
  const normalizedValue = value?.trim();
  if (!normalizedValue) {
    return "stub_header";
  }

  if (normalizedValue === "stub_header" || normalizedValue === "clerk") {
    return normalizedValue;
  }

  throw new Error("VITE_AUTH_MODE must be one of: stub_header, clerk");
}

const authMode = parseAuthMode(import.meta.env.VITE_AUTH_MODE);
const clerkPublishableKey = optional(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY);

if (authMode === "clerk" && clerkPublishableKey === "") {
  throw new Error("VITE_CLERK_PUBLISHABLE_KEY is required when VITE_AUTH_MODE=clerk");
}

export const env: Env = {
  apiBaseUrl: required("VITE_API_BASE_URL", import.meta.env.VITE_API_BASE_URL),
  authMode,
  stubAuthEmail:
    typeof import.meta.env.VITE_STUB_AUTH_EMAIL === "string" &&
    import.meta.env.VITE_STUB_AUTH_EMAIL.trim() !== ""
      ? import.meta.env.VITE_STUB_AUTH_EMAIL.trim()
      : null,
  clerkPublishableKey,
  buildSha: import.meta.env.VITE_BUILD_SHA ?? "dev",
};
