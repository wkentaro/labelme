# GUI QA report contract

## Run metadata

Record these before scenarios start:

- UTC start and end times
- Git commit, dirty-tree state, app version, and artifact path
- source or packaged lane
- OS version, architecture, display scale, window size, and locale
- profile, theme, clean or returning settings state, and input dataset
- `make test` status when it was part of the request
- run directory and process stderr path

## Scenario ledger

Use one row per selected scenario. A selected row never disappears.

| ID  | Status | Attempts | Checkpoints               | Durable oracle              | Finding IDs | Notes |
| --- | ------ | -------: | ------------------------- | --------------------------- | ----------- | ----- |
| A01 | pass   |        1 | before, committed, undone | output JSON has zero shapes | --          | --    |

Allowed statuses:

- `pass`: every stated oracle held and no material friction was observed.
- `fail`: a verified functional, data, visual, accessibility, or performance expectation
  failed.
- `friction`: the task completed, but the interaction created a reportable obstacle.
- `inconclusive`: execution completed but the evidence cannot decide the claim.
- `blocked`: a prerequisite such as an artifact, permission, platform, or service was
  unavailable.
- `not-run`: intentionally outside this run; name the scope decision.

## Finding schema

Give every finding a stable ID such as `F-001` and include:

```markdown
### F-001: Short outcome-oriented title

- Classification: defect | ux-friction | visual | accessibility | performance | automation-gap
- Severity: P0 | P1 | P2 | P3
- Confidence: verified | probable | inconclusive
- Environment: lane, artifact, OS, theme, profile state, dataset
- Scenario: stable scenario ID
- Expected: observable user or data outcome
- Observed: observable outcome without inferred cause
- Impact: affected user and task consequence
- Reproduction: numbered human actions from a fresh precondition
- Attempts: consistent results / total attempts
- Evidence: screenshot, AX excerpt, stderr, saved file, or restart path
- Likely source: file and line only when code inspection directly supports it
- Suggested remedy: concrete direction without implementing it
```

Keep app evidence and harness evidence distinct. An accessibility action that returns an
error is an automation gap; the same control also failing through a visible pointer or
keyboard path is app evidence.

## Severity

- `P0`: data loss or corruption, crash loop, security exposure, or a release-blocking
  failure with no safe recovery.
- `P1`: a primary workflow is blocked, saved state is wrong, or a major accessibility
  path has no workable alternative.
- `P2`: a meaningful error or recurring obstacle has a discoverable workaround.
- `P3`: polish or localized friction with low task impact.

Severity describes impact, not confidence. Keep an inconclusive high-impact risk in the
risk summary without promoting it to a verified P0/P1 finding.

## Report order

Write `report.md` in this order:

1. Verdict and coverage claim
2. Run metadata
3. Verified P0/P1 findings
4. Verified P2/P3 findings
5. UX, visual, and accessibility friction
6. Automation gaps and inconclusive risks
7. Scenario ledger
8. Positive observations
9. Coverage gaps and next run

The verdict names what was covered, not a generic quality score. Prefer “nightly source
lane complete on macOS, light and dark” over “GUI looks good.”
