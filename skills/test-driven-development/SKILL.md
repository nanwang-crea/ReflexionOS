---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code — write the test first, watch it fail, then write minimal code to pass.
category: discipline
---

# Test-Driven Development (TDD)

## Overview

Write the test first. Watch it fail. Write minimal code to pass.

**Core principle:** if you didn't watch the test fail, you don't know if it tests the right thing.

**Violating the letter of the rules is violating the spirit of the rules.**

## When to Use

**Always:**
- New features
- Bug fixes
- Refactoring
- Behavior changes

**Exceptions (ask the user):**
- Throwaway prototypes
- Generated code
- Configuration files

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Delete means delete

## Red-Green-Refactor

1. **RED** — Write one minimal failing test showing what should happen
2. **Verify RED** — Run the test, confirm it fails for the right reason
3. **GREEN** — Write simplest code to pass the test
4. **Verify GREEN** — Run all tests, confirm everything passes
5. **REFACTOR** — Clean up while keeping tests green
6. **Repeat** — Next failing test for next feature

## Good Tests

| Quality | Good | Bad |
|---------|------|-----|
| **Minimal** | One behavior per test | "and" in the test name |
| **Clear** | Name describes behavior | `test1`, `test2` |
| **Real** | Tests actual code behavior | Tests mock behavior |

## Why Order Matters

Tests written after code pass immediately. Passing immediately proves nothing:
- Might test the wrong thing
- Might test implementation, not behavior
- You never saw it catch a bug

Test-first forces you to see the test fail, proving it actually tests something.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Simple code breaks. Test takes 30 seconds. |
| "I'll test after" | Tests passing immediately prove nothing. |
| "Already manually tested" | Ad-hoc ≠ systematic. No record, can't re-run. |
| "Deleting X hours is wasteful" | Sunk cost fallacy. Keeping unverified code is debt. |

## Red Flags

- Code before test
- Test passes immediately
- "I already manually tested it"
- "Tests after achieve the same purpose"
- "It's about spirit not ritual"

**All of these mean: delete code, start over with TDD.**
