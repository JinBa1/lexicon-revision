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

export const env: Env = {
  apiBaseUrl: required("VITE_API_BASE_URL", import.meta.env.VITE_API_BASE_URL),
  authMode:
    (import.meta.env.VITE_AUTH_MODE as "stub_header" | "clerk" | undefined) ?? "stub_header",
  stubAuthEmail:
    typeof import.meta.env.VITE_STUB_AUTH_EMAIL === "string" &&
    import.meta.env.VITE_STUB_AUTH_EMAIL.trim() !== ""
      ? import.meta.env.VITE_STUB_AUTH_EMAIL.trim()
      : null,
  clerkPublishableKey: required(
    "VITE_CLERK_PUBLISHABLE_KEY",
    import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
  ),
  buildSha: import.meta.env.VITE_BUILD_SHA ?? "dev",
};

if (env.authMode === "clerk" && env.clerkPublishableKey.trim() === "") {
  throw new Error("VITE_CLERK_PUBLISHABLE_KEY is required when VITE_AUTH_MODE=clerk");
}
