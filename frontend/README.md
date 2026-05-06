# Lexicon Revision Frontend

Vite + React + TypeScript single-page app for the Lexicon Revision frontend.

## Develop

Run from `frontend/`:

```bash
corepack pnpm install
corepack pnpm dev
```

## Build

```bash
corepack pnpm run build
```

The static build output is written to `frontend/dist/`.

## Environment Variables

- `VITE_API_BASE_URL`: FastAPI backend origin, for example
  `http://localhost:8000`.
- `VITE_AUTH_MODE`: `stub_header` for local dev/test or `clerk` for
  production/staging Clerk auth. Defaults to `stub_header` when omitted.
- `VITE_CLERK_PUBLISHABLE_KEY`: Clerk publishable key for production/staging
  Clerk auth. Required when `VITE_AUTH_MODE=clerk`; optional in local
  stub-header mode.

## Tests

Run from `frontend/`:

```bash
corepack pnpm test
corepack pnpm lint
corepack pnpm format:check
corepack pnpm typecheck
corepack pnpm test:e2e
```

`test:e2e` runs the mocked API/auth Playwright tests.

## Deployment Coordination

The frontend is intended for Cloudflare Pages as a static SPA with no Pages
Functions or SSR. The production frontend origin is `https://lexiconrevision.uk`.
Cloudflare Pages provides SPA fallback when there is no top-level `404.html`;
do not add a catch-all `_redirects` rule, because Pages redirect rules also
match existing assets.

Configure the frontend build with the chosen backend origin and Clerk mode:

```bash
VITE_API_BASE_URL=<backend-origin>
VITE_AUTH_MODE=clerk
VITE_CLERK_PUBLISHABLE_KEY=...
```

Coordinate the backend production environment with the chosen frontend origin:

```bash
CORS_ALLOWED_ORIGINS=<frontend-origin>
ACCESS_AUTH_PROVIDER=clerk
CLERK_SECRET_KEY=...
CLERK_AUTHORIZED_PARTIES=<frontend-origin>
```
