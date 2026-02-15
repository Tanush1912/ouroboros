# QUALITY_SCORE.md — Per-Domain Quality Grades

> Auto-updated by the entropy GC workflow (`agents/workflows/entropy_gc.py`).
> Last updated: 2026-03-05 (initial baseline)

---

## Summary

| Domain | Score | Trend | Violations |
|---|---|---|---|
| agents/core | 10.0 | — | 0 |
| agents/models | 10.0 | — | 0 |
| agents/workers | 10.0 | — | 0 |
| agents/tools | 10.0 | — | 0 |
| agents/workflows | 10.0 | — | 0 |
| lint | 10.0 | — | 0 |
| repo_index | 10.0 | — | 0 |
| tests | 10.0 | — | 0 |

**Overall: 10.0 / 10.0**

---

## Principle Coverage

| Principle | Status | Last Checked |
|---|---|---|
| GP-001: No duplicate utilities | PASS | 2026-03-05 |
| GP-002: No file > 500 lines | PASS | 2026-03-05 |
| GP-003: No hand-rolled duplicates | PASS | 2026-03-05 |
| GP-004: All external data validated | PASS | 2026-03-05 |
| GP-005: No print() outside scripts/ | PASS | 2026-03-05 |
| GP-006: Schema naming conventions | PASS | 2026-03-05 |
| GP-007: No dead imports | PASS | 2026-03-05 |
| GP-008: Docs reference real code | PASS | 2026-03-05 |
| GP-009: Active plans updated < 7 days | PASS | 2026-03-05 |
| GP-010: Quality score current | PASS | 2026-03-05 |

---

## Agent Eval Results

| Test | Status | Iterations | Notes |
|---|---|---|---|
| test_bug_fix | NOT RUN | — | Requires agent eval setup |
| test_feature_gen | NOT RUN | — | Requires agent eval setup |
| test_entropy_gc | NOT RUN | — | Requires agent eval setup |

---

## Notes

Initial baseline. All scores 10.0 — system is freshly initialized.
Run `python agents/workflows/entropy_gc.py` to generate real scores.
