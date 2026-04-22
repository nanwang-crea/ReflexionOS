---
name: code-implementation-discipline
description: Use when implementation requests contain scope pressure, ambiguous success criteria, quick-patch language, cleanup-without-band-aids language, or future-proofing pressure that can cause premature coding or under-verification.
---

# Code Implementation Discipline

## Overview

Use this skill to keep code work grounded in real intent instead of jumping from a request straight into edits. Its job is to force the right decision gates when request wording makes it easy to choose scope too early or verify too little.

**Core principle:** understand the problem, choose the right scope, define verification, then implement and review.

## When to Use

- Requests with pressure phrases like "just patch it quickly," "clean this up properly," or "don't paint us into a corner"
- Work where acceptance criteria, compatibility, or impact boundary are not yet explicit
- Tasks where wording pushes toward premature patching, premature refactoring, or under-verification
- Requests where implementation shape is easy to lock in before the real problem is clear

Do not use for pure explanation, read-only investigation, or straightforward edits where scope, acceptance criteria, and compatibility expectations are already explicit.

## Required Skill Boundaries

- **REQUIRED SUB-SKILL:** Use `brainstorming` before implementation when the request is still a design problem.
- **REQUIRED SUB-SKILL:** Use `writing-plans` when the work spans multiple modules or needs a written implementation plan.
- **REQUIRED SUB-SKILL:** Use `systematic-debugging` for bugs, flaky tests, failures, or unexpected behavior.
- **REQUIRED SUB-SKILL:** Use `test-driven-development` before writing production code.
- **REQUIRED SUB-SKILL:** Use `verification-before-completion` before claiming the work is complete.

This skill does not replace those skills. It only routes into them and adds decision gates before implementation starts.

## Decision Gates

1. **Clarify before coding**
Ask until the following are sufficiently clear to start safely:
- target outcome
- non-goals
- impact boundary
- compatibility expectations
- acceptance criteria

If uncertainty remains, write the assumptions explicitly and get user confirmation before implementation. Do not self-approve missing requirements.

2. **Choose scope explicitly**
Do not default to the smallest patch. Present three levels when the request contains mixed scope signals, future-proofing pressure, or unclear cleanup depth. If the user already chose a clear scope, confirm it briefly and proceed.

| Option | Use when | Shape |
|---|---|---|
| Patch | urgent fix, narrow local defect | minimal intrusion |
| Refactor | local cleanup with maintainability gains | moderate restructuring |
| Redesign | root-cause or architecture problem | system-level change |

3. **Define verification before implementation**
State how correctness will be checked:
- existing coverage
- new tests needed
- key user or system paths
- non-functional risks worth checking

4. **Review before closing**
Completion requires:
- what changed
- why this scope was chosen
- what was verified
- remaining risks or gaps
- explicit user confirmation if further refinement may still be needed

## Reality-Driven Heuristics

- Do not let wording like "quick patch" replace diagnosis.
- Do not let wording like "clean it up properly" justify unbounded refactoring.
- Prefer the smallest scope that actually solves the stated problem, not the smallest diff.
- Favor long-term correctness over temporary compatibility layers unless compatibility is a real requirement.
- Test behavior, not implementation trivia.

## What This Skill Does Not Permit

- It does not permit skipping `brainstorming` when the request is still a design problem.
- It does not permit skipping `systematic-debugging` for flaky tests, failures, or unexplained bugs.
- It does not permit skipping `test-driven-development` once production code is about to be written.
- It does not permit skipping `verification-before-completion` before making completion claims.
- It does not replace a written plan when the work genuinely needs one.

## Common Mistakes

| Mistake | Better move |
|---|---|
| Reading code until a solution feels obvious | Stop and confirm missing intent or boundary decisions |
| Treating user phrasing as scope selection | Offer patch/refactor/redesign explicitly |
| Declaring success after one happy-path run | Verify the critical path and regression surface |
| Adding compatibility code by habit | Confirm compatibility is actually required |
| Shipping "cleaner" code without stating risks | Include review notes and residual risk |

## Red Flags

- "I can just patch this quickly"
- "I'll clarify later if needed"
- "The right scope is obvious"
- "Tests passing once is enough"
- "The request says cleanup, so refactor broadly"

These mean the decision gates were skipped. Go back before editing more code.
