# Code Review + Audit — GCP_LOGGING (2025-12-15)

## Scope
- Repo: `/home/daclab-ai/GCP_LOGGING`
- Branch: `main`
- HEAD: `0637d9acb9234b386a65fdab9cb1e215da777746` (`feat: add smart agent tools with intelligent defaults`)
- Reviewed areas:
  - Backend: `src/` (FastAPI API + LangGraph agent + BigQuery query layer + Firebase persistence)
  - Cloud Functions: `functions/`
  - Deployment: `Dockerfile`, `.github/workflows/deploy-production.yml`, `scripts/deploy_prod.sh`
  - Docs/specs: `docs/specs/CANONICAL_CONTRACT.md`, `docs/ARCHITECTURE.md`, `docs/ADR_0001_LOG_STORAGE.md`
- Local working tree status at review time (uncommitted):
  - Modified: `CLAUDE.md`, `src/api/main.py`, `src/glass_pane/__init__.py`
  - Deleted: `src/glass_pane/static/css/design-system.css`, `src/glass_pane/templates/index.html`
  - Untracked (not reviewed exhaustively): `frontend/`, `dashboard_assets/`, `database-debug.log`, `pubsub-debug.log`, `incident_report.md`, `investigation_plan.yaml`, etc.

## Build/Test Status
Backend (Python):
- `python3 --version` → **Python 3.12.3**
- `python3 -m compileall -q src functions` → **OK**
- `pytest -q` (after creating `.venv` and installing `requirements.txt`) → **2 passed**, **2 warnings**
  - DeprecationWarning: `google._upb._message.*` uses deprecated CPython APIs (warns about Python 3.14)

Frontend (React/Vite):
- Not executed (directory `frontend/` is currently untracked; no CI job).

## Key Findings

### BLOCKER

#### 1) No authN/authZ on user-scoped endpoints (sessions, saved queries)
- **Severity:** BLOCKER
- **Evidence:**
  - `src/api/main.py:245-357` exposes session/query CRUD and trusts caller-provided `user_id`.
    - `create_session()` uses `request.user_id` directly (`src/api/main.py:245-256`).
    - `list_sessions()` accepts `user_id` as a query parameter (`src/api/main.py:264-277`).
    - `save_query()` uses `request.user_id` directly (`src/api/main.py:324-336`).
    - `list_saved_queries()` accepts `user_id` as a query parameter (`src/api/main.py:344-357`).
  - `src/services/firebase_service.py` uses Firebase Admin / server credentials (`firebase_admin`, `firestore`) and stores/queries by that `userId` field (`src/services/firebase_service.py:14-16`, `105-139`, `158-186`, `368-426`).
  - Deployment currently makes the service public:
    - Cloud Run deploy uses `--allow-unauthenticated` in GitHub Actions (`.github/workflows/deploy-production.yml:76-78`).
    - The manual prod script does the same (`scripts/deploy_prod.sh:65-78`, esp. `:70`).
- **Impact:** Any internet caller can create/list/read/modify other users’ sessions and saved queries by choosing arbitrary `user_id` values. If this data contains log context, this is a direct data exposure path.
- **Recommended fix:**
  - Implement request authentication and enforce ownership:
    - Prefer Firebase Auth: require `Authorization: Bearer <Firebase ID token>`; verify via `firebase_admin.auth.verify_id_token`; derive `uid` and ignore caller-provided `user_id`.
    - Enforce `session.userId == uid` checks before returning session or messages.
    - Consider Cloud Run IAM (remove `--allow-unauthenticated`) once a client auth strategy is in place.
- **Verification steps:**
  - Add unit tests for auth dependency.
  - Add endpoint tests:
    - Missing/invalid token → `401`.
    - Cross-user session access → `403` (or `404` to avoid oracle).

#### 2) SSE chat endpoint leaks internal tracebacks and tool I/O
- **Severity:** BLOCKER
- **Evidence:**
  - `src/api/main.py:461-468` yields a payload containing `traceback.format_exc()` back to the client.
  - `src/api/main.py:427-447` streams tool inputs/outputs to clients, including raw tool output content.
- **Impact:** Internal stack traces and tool outputs can reveal implementation details and potentially sensitive log content. This also increases the blast radius if the LLM/tool layer ever touches secrets.
- **Recommended fix:**
  - Replace traceback-in-response with a safe error envelope (include a correlation/request id, but not internals).
  - Gate verbose error details behind an explicit `DEBUG`/`ENV=local` flag.
  - Redact tool inputs/outputs before streaming, or only stream a summarized view.
- **Verification steps:**
  - Force an exception in the chat flow and confirm the SSE stream does **not** contain a traceback.
  - Add tests for the redaction/sanitization function.

### HIGH

#### 3) Mutable default arguments risk data bleed (and potential privacy issues)
- **Severity:** HIGH
- **Evidence:**
  - `src/agent/persistence.py:9-21` defines defaults like `scope: Dict[str, Any] = {}` and `evidence: List[...] = []`.
- **Impact:** Mutable defaults can be shared between calls, causing cross-request contamination and incorrect persistence (worst case: cross-user data bleed into stored artifacts).
- **Recommended fix:** Use `None` defaults and initialize inside the function.
- **Verification steps:** Add unit test that calls `persist_agent_run()` twice and asserts per-call isolation of `evidence`, `scope`, etc.

#### 4) PII/secret redaction is claimed but not enforced in code paths
- **Severity:** HIGH
- **Evidence:**
  - Agent tool normalization extracts and returns fields likely to contain PII (IP, user agent, URLs): `src/agent/tools/definitions.py:19-55` and `src/agent/tools/contracts.py:25-41`.
  - The Firebase embedding function stores `embedding_text` including log message content (`functions/firebase/main.py:110-125`).
  - Docs claim redaction (“Sensitive data is redacted before LLM processing”), but there is no clear shared redaction utility applied to these tool outputs.
- **Impact:** Logs frequently contain emails, IPs, bearer tokens, session IDs, and user identifiers. Sending them to LLMs or persisting them in Firestore without redaction is a compliance and incident risk.
- **Recommended fix:**
  - Create a single redaction module (e.g. `src/security/redaction.py`) with tested patterns (tokens, API keys, emails, IPs, auth headers).
  - Apply it:
    - Before tool outputs are returned to the LLM.
    - Before SSE tool output is streamed to clients.
    - Before embeddings are generated/stored.
  - Add retention policy / TTL strategy for Firestore `embeddings` if this will run in production.
- **Verification steps:** Unit tests over representative log payload fixtures proving redaction.

#### 5) Dependency versions are largely unpinned (reproducibility risk)
- **Severity:** HIGH
- **Evidence:**
  - `requirements.txt:1-17` specifies mostly unpinned dependencies.
  - `Dockerfile:8-9` installs directly from `requirements.txt` during builds.
- **Impact:** Builds can change over time without code changes (breakage, supply chain drift). Prod debugging becomes harder when versions aren’t reproducible.
- **Recommended fix:**
  - Introduce a lock/constraints file (`requirements.lock` via `pip-tools`, `uv`, or Poetry).
  - Update Dockerfile + CI to install from locked set.
- **Verification steps:** clean build using only the lock file succeeds; CI matches local env.

### MEDIUM

#### 6) Hard-coded CORS origins (and credentials enabled)
- **Severity:** MEDIUM
- **Evidence:** `src/api/main.py:27-38` hard-codes dev + one production URL and sets `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.
- **Impact:** Environment drift (staging/custom domains break), and policy may become overly permissive as the app evolves.
- **Recommended fix:** Configure allowed origins via env var (comma-separated), validate scheme/host, and set `allow_credentials` only if you actually use cookies.
- **Verification steps:** local dev origin works; an unlisted origin fails with CORS.

#### 7) Docs and operational artifacts drift from actual code
- **Severity:** MEDIUM
- **Evidence:**
  - `GO_LIVE_CHECKLIST.md:24-27` uses `{"query": ...}` but `ChatRequest` expects `message` (`src/api/main.py:66-71`).
  - `CLAUDE.md:91-96` references `.github/workflows/deploy.yml`, but the repo contains `.github/workflows/deploy-production.yml`.
  - `README.md:18-25` describes server-rendered UI templates under `src/glass_pane/`, but the current diff deletes `src/glass_pane/templates/index.html`.
- **Impact:** Onboarding + incident response slows down; runbooks may instruct broken commands.
- **Recommended fix:** Update docs to match the current FastAPI API contract and the deployment workflow filename.
- **Verification steps:** run the documented smoke-test curls against a local server and ensure they succeed.

#### 8) Placeholder tools can mislead the agent/user
- **Severity:** MEDIUM
- **Evidence:**
  - `repo_search_tool()` returns a dummy `{matches: []}` (`src/agent/tools/definitions.py:86-94`).
  - `runbook_search_tool()` returns `[]` (`src/agent/tools/definitions.py:170-176`).
- **Impact:** The agent may claim it searched code/runbooks but actually cannot, reducing reliability.
- **Recommended fix:** Either implement these tools (e.g., search an indexed corpus/runbook store) or remove from tool list until real.
- **Verification steps:** add a test that proves `repo_search_tool` returns actual matches for a known pattern.

#### 9) FinOps materialization job appears incomplete/incorrect
- **Severity:** MEDIUM
- **Evidence:** `src/finops/materialize_jobs.py:20-41` uses a simplified InfoSchema query; `referenced_tables.table_id` is unlikely to be valid as written.
- **Impact:** Scheduled job can fail or generate incorrect cost reporting.
- **Recommended fix:** Validate query against BigQuery InfoSchema schema, add a dry-run in CI, and/or add integration test in a sandbox project.
- **Verification steps:** dry-run + one-day execution in a non-prod dataset.

### LOW

#### 10) Logging/observability is inconsistent (print vs structured logs)
- **Severity:** LOW
- **Evidence:**
  - `src/api/main.py:462-466` prints errors.
  - `src/agent/llm.py:10` prints model init.
  - `src/services/firebase_service.py:71-77` prints environment selection.
- **Impact:** Harder to debug incidents; risk of logging sensitive payloads.
- **Recommended fix:** Standardize on `logging` with structured fields and per-request correlation id (Cloud Run trace header integration).
- **Verification steps:** ensure logs contain request_id/trace_id and do not contain raw sensitive fields.

## Quick Wins (≤ 2 hours)
- Fix mutable defaults in `src/agent/persistence.py` and add a small unit test.
- Remove stack traces from SSE responses (`src/api/main.py`) and return a safe error shape.
- Make CORS origins configurable via env (`src/api/main.py`).
- Add gitignore rules for local debug artifacts (`database-debug.log`, `pubsub-debug.log`, `frontend/playwright-report/`).
- Update `GO_LIVE_CHECKLIST.md` curl example to use `{ "message": "..." }`.

## Hardening Plan (1–2 weeks)
- Implement authN/authZ for all user-scoped endpoints (Firebase Auth verification + ownership checks).
- Add a tested redaction layer for logs/tool outputs and apply it consistently (LLM, SSE, embeddings).
- Add BigQuery cost guardrails to API queries (`maximum_bytes_billed`, bounded time windows).
- Lock dependencies (requirements lockfile) and add CI security scanning (pip-audit / osv-scanner).
- Expand test coverage: endpoint tests for auth + core API behaviors.

## Resolution - 2025-12-15

### Applied Fixes

#### 1) AuthN/AuthZ (BLOCKER #1)
- **Status:** FIXED
- **Action:**
  - Added `src/api/auth.py` implementing `get_current_user_uid` using `firebase_admin.auth.verify_id_token`.
  - Updated `src/api/main.py` endpoints (`/api/sessions`, `/api/saved-queries`, `/api/chat`) to require authentication.
  - Enforced ownership checks: users can only access their own sessions.
- **Verification:**
  - Added `tests/unit/test_api_security.py` verifying 401 on missing auth, 403 on cross-user access, and 200 on valid access.
  - 5/5 security tests passed.

#### 2) SSE Chat Hardening (BLOCKER #2)
- **Status:** FIXED
- **Action:**
  - Wrapped `event_stream` in `src/api/main.py` with try-except block.
  - Replaced `traceback.format_exc()` with safe error payload `{"message": "An internal error...", "reference_id": "uuid"}`.
  - Log full traceback server-side with reference ID.
  - Redacted tool inputs/outputs using new redaction utility.
- **Verification:**
  - Manual verification via code review and test coverage of redaction logic.

#### 3) Redaction (HIGH #4)
- **Status:** FIXED (Partially - Applied to Chat and Tools)
- **Action:**
  - Created `src/security/redaction.py` handling email, IP, Bearer token, and API key patterns.
  - Applied `redactor.scrub_data` to tool inputs/outputs in `api/chat` stream.
- **Verification:**
  - Added `tests/unit/test_redaction.py`.
  - 4/4 redaction tests passed.

#### 4) Mutable Defaults (HIGH #3)
- **Status:** FIXED
- **Action:**
  - Updated `src/agent/persistence.py` to use `None` as default for mutable args and initialize inside function.
- **Verification:**
  - Added `tests/unit/test_persistence.py`.
  - 1/1 persistence test passed.

#### 5) CORS Config (MEDIUM #6)
- **Status:** FIXED
- **Action:**
  - Updated `src/api/main.py` to read `ALLOWED_ORIGINS` from env var.
- **Verification:**
  - Code review confirmed logic.

### Verification Summary
- `python3 -m compileall -q src functions` → **OK**
- `pytest tests/unit` → **12 passed, 0 failed**
