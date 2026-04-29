# UOE Engineering Access Smoke

## Date

2026-04-29

## Environment

- Local Codex workspace on branch `feat/uoe-engineering-papers`.
- Backend tests run through conda env `rag-exam`.
- Frontend tests run in `frontend/` with `corepack pnpm`.
- No local FastAPI/Vite app or staging app was kept running for manual browser
  smoke in this session.

## Commits

- Backend commit SHA: `a2f988fcf684fa566f71a8814159b5e08d6cb278`
- Frontend commit SHA: `e85f461f987492b1d7421c62dde730e4a2abf664`

## Auth Mode

- Automated backend access tests used repository/service/API test identities,
  including anonymous, stub-header, and Clerk-shaped request identities.
- Frontend tests used existing unit-test fixtures and mocked auth setup.

## Checks Run

| Check | Result | Evidence |
| --- | --- | --- |
| UOE private indexing/access regression slice | Pass with DB tests skipped | `conda run -n rag-exam pytest tests/scripts/test_index_chunks_postgres.py tests/integration/test_pg_repository.py tests/integration/test_collections_listing.py tests/access/test_service_list_collections.py -q` -> `15 passed, 32 skipped`; skips were due to missing `TEST_DATABASE_URL`. |
| Backend access/search API smoke | Pass | `conda run -n rag-exam pytest tests/access tests/search/test_api.py -q` -> `77 passed`. |
| Frontend UOE metadata/filter unit coverage | Pass | `corepack pnpm test -- filters-popover chunk-card` -> Vitest reported `45 passed`, `325 passed`. |
| Frontend typecheck | Pass | `corepack pnpm typecheck`. |
| Frontend lint | Pass | `corepack pnpm lint`. |
| Frontend format check | Pass | `corepack pnpm format:check` -> all matched files use Prettier style. |

## Smoke Results

| Scenario | Result | Notes |
| --- | --- | --- |
| `/collections` returns `uoe-mece10017` locked for anonymous users | Covered by automated repository test | `test_list_collections_keeps_uoe_private_until_edinburgh_membership`. |
| `/collections` returns `uoe-mece10017` accessible for Edinburgh membership | Covered by automated repository test | Same test verifies metadata schema is present only when accessible. |
| Frontend renders UOE filters with `Course Code` and `Course Title` | Covered by automated unit test | `filters-popover.spec.tsx`. |
| Frontend does not render Cambridge `Tripos Part` label for UOE | Covered by automated unit tests | `filters-popover.spec.tsx` and `chunk-card.spec.tsx`. |
| Locked collection rows do not expose filters | Covered by automated unit test | `filters-popover.spec.tsx` uses locked UOE fixture with `metadata_schema: null`. |
| UOE chunk cards render metadata labels from schema | Covered by automated unit test | `chunk-card.spec.tsx`. |
| Manual anonymous/Edinburgh/manual-override/search/source browser smoke | Not run | No running local/staging app or real/stubbed browser identity context was available in this session. |

## Known Gaps

- DB-backed integration assertions skipped without `TEST_DATABASE_URL`.
- Manual browser smoke for anonymous, Edinburgh identity, manual override,
  UOE search results, and UOE source page remains to be run in an environment
  with a running app and test identities.
