"""Bounded, uncached JobSpy discovery adapter; never writes to a job queue."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SITES = ("indeed", "linkedin", "glassdoor", "zip_recruiter")


def text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def public_url(value: object) -> str:
    value = text(value)
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if (
            parts.scheme not in ("https", "http")
            or not host
            or parts.username
            or parts.password
        ):
            return ""
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return value
    except ValueError:
        return ""


def identity(url: str) -> str:
    """Remove known marketing parameters only; preserve posting identity."""
    p = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in ("trk", "trackingid")
    ]
    return urlunsplit(
        (p.scheme.lower(), p.netloc.lower(), p.path, urlencode(query), "")
    )


def number(value: object) -> float | None:
    if (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    ):
        return float(value)
    return None


def normalize(row: dict, site: str, query: str, location: str, now: str) -> dict | None:
    source = public_url(row.get("job_url"))
    title = text(row.get("title"))
    if not source or not title:
        return None
    direct = public_url(row.get("job_url_direct"))
    job = {
        "title": title,
        "url": direct or source,
        "company": text(row.get("company")),
        "location": text(row.get("location")),
        "sourceUrl": source,
        "source": "jobspy:" + site,
        "discoveredAt": now,
        "provenance": [
            {"site": site, "url": source, "query": query, "searchLocation": location}
        ],
        "description": text(row.get("description")),
    }
    if direct:
        job["applyUrl"] = direct  # Source-supplied, not independently verified.
    if text(row.get("id")):
        job["externalId"] = text(row["id"])
    posted = text(row.get("date_posted"))
    try:
        parsed = date.fromisoformat(posted)
        job["postedAt"] = int(
            datetime(
                parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc
            ).timestamp()
            * 1000
        )
        job["datePosted"] = posted
    except ValueError:
        pass  # Discovery time is never substituted for publication time.
    pay = {
        key: val
        for key, raw in [("min", row.get("min_amount")), ("max", row.get("max_amount"))]
        if (val := number(raw)) is not None
    }
    if pay:
        job["sourceSalary"] = {
            **pay,
            "interval": text(row.get("interval")),
            "currency": text(row.get("currency")),
        }
        # career-ops interprets salary as annual: never pass hourly pay as annual.
        if row.get("interval") == "yearly":
            job["salary"] = {**pay, "currency": text(row.get("currency"))}
    return job


def worker(payload: dict) -> dict:
    from jobspy import scrape_jobs

    frame = scrape_jobs(
        site_name=[payload["site"]],
        search_term=payload["query"],
        location=payload["location"],
        results_wanted=payload["limit"],
        hours_old=payload["hours"],
        country_indeed="USA",
        fetch_description=False,
        enforce_annual_salary=False,
        verbose=0,
    )
    # pandas serializes NaN as null; the API's date-only value is retained below.
    rows = json.loads(frame.to_json(orient="records", date_format="iso"))
    for row in rows:
        if isinstance(row.get("date_posted"), str):
            row["date_posted"] = row["date_posted"].split("T")[0]
    return {
        "rows": rows,
        "errors": frame.attrs.get("errors", {}),
        "warnings": frame.attrs.get("warnings", {}),
    }


def collect(
    sites: list[str],
    queries: list[str],
    locations: list[str],
    limit: int,
    hours: int,
    timeout: int,
    pause: float,
) -> dict:
    jobs: dict[str, dict] = {}
    runs = []
    now = datetime.now(timezone.utc).isoformat()
    tasks = [
        (s, q, loc)
        for s in dict.fromkeys(sites)
        for q in dict.fromkeys(queries)
        for loc in dict.fromkeys(locations)
    ]
    for index, (site, query, location) in enumerate(tasks):
        payload = {
            "site": site,
            "query": query,
            "location": location,
            "limit": limit,
            "hours": hours,
        }
        started = time.monotonic()
        run = {**payload, "status": "ok", "count": 0}
        try:
            result = subprocess.run(
                [sys.executable, "-m", "jobspy.career_ops", "--worker"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode:
                raise RuntimeError((result.stderr or "worker failed")[-800:])
            data = json.loads(result.stdout)
            run["errors"] = data.get("errors", {})
            run["warnings"] = data.get("warnings", {})
            if run["errors"]:
                run["status"] = "error"
            for row in data["rows"]:
                job = normalize(row, site, query, location, now)
                if not job:
                    run["invalidRows"] = run.get("invalidRows", 0) + 1
                    continue
                key = identity(job["url"])
                if key in jobs:
                    jobs[key]["provenance"].extend(job["provenance"])
                else:
                    jobs[key] = job
                run["count"] += 1
        except (
            subprocess.TimeoutExpired,
            RuntimeError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            run.update(status="error", errors={"adapter": str(exc)})
        run["seconds"] = round(time.monotonic() - started, 2)
        runs.append(run)
        if index + 1 < len(tasks):
            time.sleep(pause)
    errors = sum(r["status"] == "error" for r in runs)
    return {
        "schema": "career-ops-jobspy-v1",
        "status": "partial" if errors and jobs else "error" if errors else "ok",
        "cacheReused": False,
        "jobs": list(jobs.values()),
        "runs": runs,
        "notes": [
            "Listings and source-supplied application URLs still require liveness and JD verification."
        ],
    }


def main() -> int:
    if sys.argv[1:] == ["--worker"]:
        print(json.dumps(worker(json.load(sys.stdin)), allow_nan=False))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", action="append", choices=SITES, required=True)
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--location", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--hours-old", type=int, default=48)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--pause", type=float, default=2)
    args = parser.parse_args()
    if (
        not 1 <= args.limit <= 50
        or not 1 <= args.hours_old <= 168
        or not 1 <= args.timeout <= 180
        or not 0 <= args.pause <= 60
    ):
        parser.error(
            "Limits: 1–50 results, 1–168 hours, 1–180 seconds timeout, 0–60 seconds pause"
        )
    if (
        any(not s.strip() for s in args.query + args.location)
        or len(args.site) * len(args.query) * len(args.location) > 24
    ):
        parser.error(
            "Use nonblank queries/locations and at most 24 board/query/location tasks"
        )
    result = collect(
        args.site,
        args.query,
        args.location,
        args.limit,
        args.hours_old,
        args.timeout,
        args.pause,
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
