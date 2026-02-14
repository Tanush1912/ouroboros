# GOLDEN_PRINCIPLES.md — Machine-Checkable Enforcement Rules

These principles are enforced by `lint/golden_lint.py`. Violations appear in CI and
in the daily entropy GC scan. Each has a severity level and auto-fixable flag.

---

## GP-001: No Duplicate Utility Functions Across Packages

**Rule:** Identical or near-identical utility functions must not exist in more than one module.
**Severity:** high
**Auto-fixable:** yes (move to shared module, update imports)
**Detection:** AST comparison of function bodies across modules
**Remediation:** Move duplicate to `agents/core/` or appropriate shared location; update all imports.

---

## GP-002: No File Exceeds 500 Lines

**Rule:** No Python file may exceed 500 lines.
**Severity:** medium
**Auto-fixable:** no (requires human judgment on split boundaries)
**Detection:** `wc -l` equivalent on all `.py` files
**Remediation:** Split file into logical sub-modules.

---

## GP-003: No Hand-Rolled Helpers Duplicating Shared Packages

**Rule:** Do not reimplement functionality already provided by project dependencies.
**Severity:** medium
**Auto-fixable:** no
**Detection:** Pattern matching against known reimplementation patterns
**Remediation:** Replace with the appropriate library call and remove the custom helper.

---

## GP-004: No YOLO Data Access — All External Data Validated at Boundary

**Rule:** All data from external sources (API responses, file reads, env vars) must be
parsed through a Pydantic model before use.
**Severity:** high
**Auto-fixable:** no
**Detection:** AST check for dict access on `json.loads()` / `requests.get()` results without model parse
**Remediation:** Wrap in a Pydantic model parse. Create model if one doesn't exist.

---

## GP-005: Structured Logging Only — No print() Outside scripts/

**Rule:** `print()` is banned outside the `scripts/` directory.
**Severity:** low
**Auto-fixable:** yes (replace with `logfire.info()` or `logging.info()`)
**Detection:** AST scan for `print()` calls in non-script files
**Remediation:** Replace with `logfire.info(message, **kwargs)` or structured logger.

---

## GP-006: Schema Types Follow *Output/*Result/*Schema Naming Convention

**Rule:** Pydantic models that represent agent outputs must use the `*Output` suffix.
Models representing results of operations use `*Result`. Request/response schemas use `*Schema`.
**Severity:** low
**Auto-fixable:** no (rename requires updating all references)
**Detection:** AST scan for Pydantic `BaseModel` subclasses with non-conforming names
**Remediation:** Rename and update all import sites. Use `search_symbol()` to find all references.

---

## GP-007: No Dead Imports

**Rule:** All imports must be used. No `import X` without using `X`.
**Severity:** low
**Auto-fixable:** yes (ruff F401 auto-fix)
**Detection:** ruff F401
**Remediation:** `ruff check --fix` will auto-remove.

---

## GP-008: All Docs Reference Real Code That Still Exists

**Rule:** File paths and symbol names mentioned in `.md` files must exist in the repo.
**Severity:** medium
**Auto-fixable:** no
**Detection:** `lint/doc_lint.py` cross-references all `backtick` paths against repo index
**Remediation:** Update the doc to reflect current file/symbol locations.

---

## GP-009: All Active Plans Updated Within 7 Days

**Rule:** Any plan in `docs/exec-plans/active/` with `Last Updated` older than 7 days
is stale and triggers a violation.
**Severity:** medium
**Auto-fixable:** no (requires human or agent review of the plan's status)
**Detection:** Parse `Last Updated` field from all active plan files
**Remediation:** Update the plan (mark steps complete, update status) or move to `completed/`.

---

## GP-010: QUALITY_SCORE.md Reflects Actual Current State

**Rule:** `docs/QUALITY_SCORE.md` must have been regenerated within 24 hours.
**Severity:** low
**Auto-fixable:** yes (re-run entropy GC to regenerate)
**Detection:** Check file modification timestamp
**Remediation:** Run `python agents/workflows/entropy_gc.py --update-scores-only`.
