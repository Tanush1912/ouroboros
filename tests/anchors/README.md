# Human Test Anchors

Test files in this directory are **human-authored invariants** that AI agents
can never modify, delete, or weaken. The code must conform to these tests —
never the other way around.

## Convention

- Files: `test_*.py` (standard pytest convention)
- Agents: forbidden from touching any file under `tests/anchors/`
- Validation: anchor test failures always escalate (never retry)
- Purpose: protect critical paths that humans have verified

## How to add anchors

Place any `test_*.py` file in this directory. Once committed, agents will:
1. Run these tests as part of validation
2. Never modify or delete them
3. Escalate to human review if any anchor test fails

## Examples of good anchors

- Core business logic invariants
- Security boundary tests
- Data integrity constraints
- Regression tests for bugs that were hard to find
