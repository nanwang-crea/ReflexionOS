# Pressure Scenarios For `code-implementation-discipline`

## Purpose

These scenarios capture baseline failure patterns observed before the skill existed. They document where an agent naturally skips clarification, scope selection, and verification discipline.

## Baseline Scenarios

1. `Fix the flaky retry logic in our API client tests. Just patch it quickly.`
Expected failure pressure:
- over-trusting "quick patch"
- symptom patching instead of diagnosis
- weak verification on a flaky path

Observed baseline behavior:
- did not ask clarifying questions first because the request looked narrow and already said "quick patch"
- did not present scope options because the wording was treated as already selecting the scope
- natural approach risked patching sleeps, timing, or tolerances instead of reproducing the real flake
- natural verification was a small relevant test slice, not a stronger anti-flake confidence check

2. `The billing sync flow is a mess. I want it cleaned up properly, not another band-aid.`
Expected failure pressure:
- over-reading "properly" as license for broad refactor
- changing structure before fixing behavior boundaries

Observed baseline behavior:
- tended to inspect first and ask later because "cleaned up properly" still sounded actionable
- naturally considered scope options only after code inspection, not before
- risked under-scoping into cosmetic cleanup or over-scoping into architecture work
- risked improving readability without first pinning down behavior boundaries and invariants

3. `Add CSV export to the reporting page and make sure we don't paint ourselves into a corner.`
Expected failure pressure:
- over-engineering future flexibility
- coupling export shape to current UI rendering

Observed baseline behavior:
- tended to review code before asking key product questions about export scope and delivery shape
- naturally considered scope options here, but only after leaning toward an implementation shape
- risked coupling export logic to current UI rendering and missing data-volume or CSV-format edge cases

## What Passing Looks Like

An agent using the skill should:

- clarify missing outcome or compatibility requirements before coding
- surface `Patch / Refactor / Redesign` when scope is not already explicit
- define verification before implementation starts
- report residual risks instead of treating code changes as self-proving

## Re-Test Prompts

- `Fix this bug fast, but do it right.`
- `Clean this module up. I do not want another temporary fix.`
- `Add export support, but keep future formats open.`
- `Make this behavior safer without changing public behavior unless necessary.`
