# Patch Plan — 2025-12-15

This plan applies the highest-risk fixes first (security/data exposure), then reliability, then maintainability.

## Apply in this order

### 1) Remove traceback + raw tool payload leakage in `/api/chat` (SSE)
- **Files:** `src/api/main.py`
- **Why first:** This is a direct information disclosure vector.
- **Risk notes:** Low-to-medium. Clients may rely on current payload shape.
- **Rollback notes:** Revert the change; or temporarily gate the new behavior behind an env var (e.g., `SAFE_ERRORS=true`).
- **Verification:**
  - `source .venv/bin/activate && pytest -q`
  - Run `uvicorn src.api.main:app --reload` and trigger an error path; confirm SSE does not include traceback text.

### 2) Fix mutable default args in agent persistence
- **Files:** `src/agent/persistence.py`
- **Why:** Prevents cross-run contamination and possible privacy bleed.
- **Risk notes:** Low.
- **Rollback notes:** Revert commit.
- **Verification:** `source .venv/bin/activate && pytest -q` (add a focused unit test).

### 3) Add authentication + enforce ownership for sessions/saved queries
- **Files:** `src/api/main.py`, `src/services/firebase_service.py` (and optionally a new `src/api/auth.py`)
- **Why:** Blocks unauthorized reads/writes of user-scoped data.
- **Risk notes:** Medium-to-high (breaking API change; frontend must send tokens).
- **Rollback notes:**
  - Ship behind a feature flag (`AUTH_REQUIRED=false` in non-prod) if needed.
  - If Cloud Run IAM is enabled later, stage it separately.
- **Verification:**
  - Unit tests for token verification logic.
  - Endpoint tests:
    - Missing token → 401
    - Cross-user access → 403/404

### 4) Implement redaction pipeline and apply to tool outputs + embeddings
- **Files:** `src/agent/tools/definitions.py`, `functions/firebase/main.py`, `src/api/main.py`
- **Why:** Ensures logs/embeddings don’t leak secrets/PII to LLMs or storage.
- **Risk notes:** Medium (could reduce debugging fidelity; must tune patterns).
- **Rollback notes:** Keep redaction patterns configurable; allow a local-only bypass.
- **Verification:**
  - Unit tests with fixtures containing emails, IPs, bearer tokens.
  - Manual: verify SSE tool output is redacted.

### 5) Add BigQuery cost guardrails to API endpoints
- **Files:** `src/api/main.py`, `src/glass_pane/config.py`
- **Why:** Prevents accidental high-cost queries from public endpoints.
- **Risk notes:** Medium (queries may fail if cap is too low).
- **Rollback notes:** Increase cap; disable cap via env var temporarily.
- **Verification:** Mock-based tests that assert `maximum_bytes_billed` is set on job config.

### 6) Make CORS origins configurable
- **Files:** `src/api/main.py`
- **Why:** Avoid environment drift and accidental exposure.
- **Risk notes:** Low.
- **Rollback notes:** Revert or include current hard-coded list as default.
- **Verification:** Browser/manual checks from allowed and disallowed origins.

### 7) Dependency locking + CI hardening
- **Files:** `requirements.txt`, `Dockerfile`, `.github/workflows/deploy-production.yml`
- **Why:** Reproducible builds + basic supply-chain safety.
- **Risk notes:** Medium (version pins can surface incompatibilities).
- **Rollback notes:** Keep the prior `requirements.txt` install path temporarily.
- **Verification:** `docker build .` + CI run.

### 8) Docs + ignores cleanup
- **Files:** `GO_LIVE_CHECKLIST.md`, `CLAUDE.md`, `README.md`, `.gitignore`
- **Why:** Reduce operational mistakes.
- **Risk notes:** Low.
- **Rollback notes:** Revert.
- **Verification:** Run the documented smoke tests.

## Smoke test checklist
- Backend unit tests: `source .venv/bin/activate && pytest -q`
- Start server: `uvicorn src.api.main:app --host 0.0.0.0 --port 8080`
- Health: `curl -sS http://localhost:8080/health`
- Auth gate (after TASK-001): `curl -i http://localhost:8080/api/sessions` returns `401`
- Chat SSE (basic): `curl -N -X POST http://localhost:8080/api/chat -H 'Content-Type: application/json' -d '{"message":"hello"}'`
- Ensure no traceback text is emitted in SSE on failures.

## Execution Log - 2025-12-15

- **Applied:** Items 1, 2, 3, 4 (partial), 6.
- **Details:**
  - Implemented `src/api/auth.py` and updated all user-scoped endpoints.
  - Hardened SSE stream in `src/api/main.py`.
  - Implemented redaction in `src/security/redaction.py` and applied to chat tools.
  - Fixed mutable defaults in `src/agent/persistence.py`.
  - Made CORS configurable.
- **Verification:** All unit tests passed (including new security/redaction tests).