# Isolated adapter verification

Tested October 28, 2026. Live discovery was run from this fork only; no live
career-ops configuration, queue or schedule was changed. No model was called.

## Deterministic tests

Six tests pass: invalid/missing URLs; date and salary semantics; preservation of
posting IDs during deduplication; duplicate provenance and repeated fresh calls;
errors/timeouts versus empty success; partial results surviving another board's
failure. Ruff and Git whitespace checks pass.

## Bounded live tests

Location: San Francisco, CA. Requested posting window: 48 hours. Five results
requested per board. Requests were sequential with two-second pauses.

| Query | Boards | Raw records | Passed existing title filter |
|---|---|---:|---:|
| software engineer | Indeed, LinkedIn | 10 | 1 |
| forward deployed engineer | Indeed, LinkedIn, Glassdoor, ZipRecruiter | 20 | 12 |

All six board/query tasks reported success without upstream warnings or errors.
Per-task elapsed times, including worker startup: 0.81–1.58 seconds. The SWE test
used 1.89 seconds of worker time plus one two-second pause; the FDE test used
4.54 seconds of worker time plus three two-second pauses. Timing excludes parent
startup and is a small sample, not a performance guarantee.

The real career-ops normalizeParserJob function accepted all 30 returned records
without changing their title, URL or posting timestamp. Its configured title
filter was evaluated read-only. Counts are per test, not unique jobs across tests.
Title acceptance is not eligibility approval: location, source date semantics,
full JD requirements, liveness, duplicates, and H-1B checks remain downstream.
Searches returned unrelated and senior listings, confirming those gates are
necessary. Unknown source dates are not replaced with discovery dates.

## Integration status

Not enabled in the live discovery loop. Before enabling it, implement a provider
that explicitly retains successful results from exit-code-3 partial responses and
reports failed boards. Keep full JD fetching, deterministic screening, H-1B
checks, and Nemotron matching in the existing worker. Raw responses are retained
outside this public fork in the local jobspy-adapter-test directory.
