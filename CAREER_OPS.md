# Job discovery adapter for career-ops

This fork adds `python -m jobspy.career_ops`, an isolated discovery command.
It does not edit portals, pipeline, scan history, agent state, or resumes. It
makes no model calls and does not score or rank jobs by candidate fit.

## Run

Install this checkout in a virtual environment (`pip install -e .`), then:

```sh
python -m jobspy.career_ops \
  --site indeed --site linkedin \
  --query 'software engineer' \
  --location 'San Francisco, CA' \
  --hours-old 48 --limit 5 --timeout 60 > discovery.json
```

Repeat `--query` for `ai engineer` or `forward deployed engineer`, and repeat
`--location` for other target locations. Supported boards are Indeed, LinkedIn,
Glassdoor and ZipRecruiter. US is selected for boards that require a country.
Explicitly specify every board to avoid silently querying all upstream sources.
The adapter limits one invocation to 24 board/query/location tasks and 50 requested
results per task. It queries tasks sequentially with a two-second pause.

Each task runs in a fresh subprocess with a wall-clock timeout. One board is
passed to JobSpy at a time. No discovery results or JDs are read from a cache;
there is no cached or alternate-source fallback. Source websites may still
serve stale data. JobSpy fetches search results; the downstream agent must fetch
and verify the current full JD before screening. Extra per-job description
requests are disabled here.

## Output contract

Stdout is a JSON object containing `jobs`, `runs`, `status`, and `cacheReused`.
Each job includes scanner-compatible `title`, `url`, `company`, `location`,
optional `postedAt` (epoch milliseconds), description when supplied by search,
and optional annual salary. Provenance retains board URL, query, search location
and discovery timestamp. A source-supplied direct application URL takes priority;
it is not independently verified. Unknown dates remain unknown. Hourly or other
nonannual pay stays in `sourceSalary`, never masquerading as annual salary.

Deduplication applies only within the current invocation, using exact normalized
posting URLs and source-supplied direct URLs. Known marketing parameters are
removed from identity keys, but posting IDs are preserved. All contributing
sources are retained. Different URLs for the same opening can still survive;
the parent's cross-listing deduplication must handle those. Nothing is sorted by
fit. These are candidates for the existing title/location/date filters and
code-based eligibility checks, not preapproved matches.

Exit codes:

- `0`: every task completed without a reported error (possibly zero jobs).
- `2`: invalid CLI arguments.
- `3`: failed or partially failed discovery; inspect JSON `runs` and retain any
  successful jobs. Errors and upstream warnings are separate from empty results.

The existing career-ops `normalizeParserJob` accepts these records. Its generic
local-parser runner, however, discards output on nonzero exit and requires an
in-repository launcher. Before live integration, add an explicit provider that
consumes exit 3 partial results, reports source failures, sets a sufficient total
timeout, and runs the existing filters/deduplication. No provider has been
installed in the live agent by this adaptation.

## Verification

```sh
python -m unittest discover -s tests -v
ruff check jobspy/career_ops.py tests/test_career_ops.py
```

The live smoke test should use at most five requested jobs per board and confirm
new usable URLs, valid date/salary normalization, bounded runtime, explicit
rate-limit/failure reporting and compatibility with the parent normalizer.
No claim of board reliability follows from one successful run. Keep raw test
results outside the repository; the MIT license and upstream attribution remain.
