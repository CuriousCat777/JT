#!/usr/bin/env python3
"""Guardian One — Self-Improvement Pipeline.

Runs the test suite iteratively, captures failures, analyzes patterns,
applies auto-fixes, and generates improvement logs.

Usage:
    python search/self_improve.py                   # Run with defaults
    python search/self_improve.py --iterations 5    # More iterations
    python search/self_improve.py --verbose          # Verbose output
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIR = REPO_ROOT / "search"
TEST_FILE = SEARCH_DIR / "tests" / "test_search_comprehensive.py"
LOGS_DIR = SEARCH_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def file_hash(path: Path) -> str:
    """SHA256 of a file."""
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def run_tests(verbose: bool = False) -> dict:
    """Run pytest and capture results as JSON."""
    cmd = [
        sys.executable, "-m", "pytest",
        str(TEST_FILE),
        "--tb=short", "-q",
        "--no-header",
    ]
    if verbose:
        cmd.append("-v")

    start = time.time()
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(REPO_ROOT), timeout=300,
    )
    duration = time.time() - start

    stdout = result.stdout
    stderr = result.stderr
    output = stdout + "\n" + stderr

    # Parse results from pytest output
    passed = 0
    failed = 0
    errors = 0
    skipped = 0
    xfailed = 0
    failures = []

    # Parse summary line like "3063 passed, 10 skipped, 36 xfailed"
    summary_match = re.search(
        r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?(?:.*?(\d+) skipped)?(?:.*?(\d+) xfailed)?",
        output,
    )
    if summary_match:
        passed = int(summary_match.group(1) or 0)
        failed = int(summary_match.group(2) or 0)
        errors = int(summary_match.group(3) or 0)
        skipped = int(summary_match.group(4) or 0)
        xfailed = int(summary_match.group(5) or 0)

    # Parse individual failures
    fail_pattern = re.compile(r"FAILED (.+?)(?:\s+-\s+(.+))?$", re.MULTILINE)
    for match in fail_pattern.finditer(output):
        test_path = match.group(1)
        reason = match.group(2) or ""
        # Categorize
        category = categorize_failure(test_path, reason)
        failures.append({
            "test_name": test_path,
            "category": category,
            "error_message": reason[:500],
            "suggestion": suggest_fix(category, test_path, reason),
        })

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "xfailed": xfailed,
        "total": passed + failed + errors + skipped + xfailed,
        "failures": failures,
        "duration_seconds": round(duration, 2),
        "return_code": result.returncode,
        "raw_output": output[-3000:],  # Last 3000 chars
    }


def categorize_failure(test_name: str, error: str) -> str:
    """Categorize a test failure by pattern."""
    tn = test_name.lower()
    err = error.lower()

    if "live" in tn or "reachable" in tn:
        return "live_integration"
    if "security" in tn or "injection" in tn or "xss" in tn:
        return "security"
    if "validation" in tn or "schema" in tn:
        return "validation"
    if "pagination" in tn or "page" in tn:
        return "pagination"
    if "filter" in tn or "facet" in tn:
        return "filter"
    if "frontend" in tn or "html" in tn or "dom" in tn:
        return "frontend"
    if "docker" in tn or "compose" in tn:
        return "infrastructure"
    if "type" in err or "typeerror" in err:
        return "type_error"
    if "key" in err or "keyerror" in err:
        return "missing_field"
    if "assert" in err:
        return "assertion"
    if "import" in err:
        return "import_error"
    if "timeout" in err or "connection" in err:
        return "connectivity"
    return "other"


def suggest_fix(category: str, test_name: str, error: str) -> str:
    """Generate a fix suggestion based on failure category."""
    suggestions = {
        "live_integration": "Start search engines: cd search/ && docker compose up -d",
        "security": "Add input sanitization to search_routes.py query parameter handling",
        "validation": "Add field validation to seed_documents.py DOCUMENTS schema",
        "pagination": "Add bounds checking to page/per_page parameters in search_routes.py",
        "filter": "Verify filter attribute names match between frontend and backend",
        "frontend": "Check HTML element IDs and CSS classes match design spec",
        "infrastructure": "Verify docker-compose.yml service definitions and port mappings",
        "type_error": "Add type coercion for query parameters (int(), str())",
        "missing_field": "Add default values for optional fields in document schema",
        "assertion": "Review expected values in test assertions against actual implementation",
        "import_error": "Install missing dependencies: pip install -r search/requirements.txt",
        "connectivity": "Check network connectivity and service availability",
        "other": "Manual review required — check test output for details",
    }
    return suggestions.get(category, suggestions["other"])


def apply_auto_fixes(failures: list, iteration: int) -> list:
    """Attempt to auto-fix common issues. Returns list of changes made."""
    improvements = []
    routes_path = REPO_ROOT / "guardian_one" / "web" / "search_routes.py"

    if not routes_path.exists():
        return improvements

    content = routes_path.read_text()
    original_hash = file_hash(routes_path)
    changed = False

    # Fix 1: Add input validation for page/per_page (prevent negative/zero)
    if "page = int(request.args.get(\"page\", 1))" in content:
        content = content.replace(
            'page = int(request.args.get("page", 1))',
            'page = max(1, int(request.args.get("page", 1)))',
        )
        content = content.replace(
            'per_page = int(request.args.get("per_page", 10))',
            'per_page = max(1, min(100, int(request.args.get("per_page", 10))))',
        )
        improvements.append({
            "file": str(routes_path),
            "change_description": "Added bounds checking: page >= 1, 1 <= per_page <= 100",
            "before_hash": original_hash,
            "after_hash": "pending",
            "iteration": iteration,
        })
        changed = True

    # Fix 2: Add try/except for int conversion of page params
    if changed or "ValueError" not in content:
        old_ts = 'page = max(1, int(request.args.get("page", 1)))'
        new_ts = '''try:
            page = max(1, int(request.args.get("page", 1)))
        except (ValueError, TypeError):
            page = 1'''
        if old_ts in content and "try:" not in content.split("search_typesense")[1].split("def ")[0]:
            # Only apply if not already wrapped
            pass  # Complex replacement deferred

    if changed:
        routes_path.write_text(content)
        for imp in improvements:
            imp["after_hash"] = file_hash(routes_path)

    return improvements


def generate_report(iterations: list, total_duration: float) -> tuple[str, dict]:
    """Generate markdown report and JSON log."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Summary stats
    first = iterations[0] if iterations else {}
    last = iterations[-1] if iterations else {}
    total_improvements = sum(len(it.get("improvements", [])) for it in iterations)

    json_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "1.0.0",
        "total_iterations": len(iterations),
        "pipeline_duration_seconds": round(total_duration, 2),
        "summary": {
            "initial_passed": first.get("passed", 0),
            "initial_failed": first.get("failed", 0),
            "final_passed": last.get("passed", 0),
            "final_failed": last.get("failed", 0),
            "total_improvements_applied": total_improvements,
            "improvement_rate": (
                f"{((last.get('passed', 0) - first.get('passed', 0)) / max(1, first.get('total', 1))) * 100:.1f}%"
                if first.get("total") else "N/A"
            ),
        },
        "iterations": iterations,
        "failure_categories": {},
    }

    # Aggregate failure categories
    for it in iterations:
        for f in it.get("failures", []):
            cat = f["category"]
            json_log["failure_categories"][cat] = json_log["failure_categories"].get(cat, 0) + 1

    # Markdown report
    md = f"""# Guardian One — Self-Improvement Pipeline Report

**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
**Pipeline Duration:** {total_duration:.1f}s
**Iterations:** {len(iterations)}

---

## Summary

| Metric | Initial | Final | Delta |
|--------|---------|-------|-------|
| Tests Passed | {first.get('passed', 0)} | {last.get('passed', 0)} | +{last.get('passed', 0) - first.get('passed', 0)} |
| Tests Failed | {first.get('failed', 0)} | {last.get('failed', 0)} | {last.get('failed', 0) - first.get('failed', 0)} |
| Tests Skipped | {first.get('skipped', 0)} | {last.get('skipped', 0)} | {last.get('skipped', 0) - first.get('skipped', 0)} |
| Expected Failures | {first.get('xfailed', 0)} | {last.get('xfailed', 0)} | {last.get('xfailed', 0) - first.get('xfailed', 0)} |
| Total | {first.get('total', 0)} | {last.get('total', 0)} | {last.get('total', 0) - first.get('total', 0)} |
| Duration | {first.get('duration_seconds', 0)}s | {last.get('duration_seconds', 0)}s | |

## Improvement Trajectory

"""

    for i, it in enumerate(iterations):
        status = "PASS" if it.get("failed", 0) == 0 else "FAIL"
        md += f"### Iteration {i + 1} [{status}]\n\n"
        md += f"- **Passed:** {it.get('passed', 0)}\n"
        md += f"- **Failed:** {it.get('failed', 0)}\n"
        md += f"- **Skipped:** {it.get('skipped', 0)}\n"
        md += f"- **Duration:** {it.get('duration_seconds', 0)}s\n"

        if it.get("improvements"):
            md += f"- **Improvements Applied:** {len(it['improvements'])}\n"
            for imp in it["improvements"]:
                md += f"  - {imp['change_description']}\n"

        if it.get("failures"):
            md += f"\n**Failures ({len(it['failures'])}):**\n\n"
            for f in it["failures"][:10]:  # Show first 10
                md += f"- `{f['test_name']}` [{f['category']}]\n"
                md += f"  - Suggestion: {f['suggestion']}\n"
        md += "\n"

    if json_log["failure_categories"]:
        md += "## Failure Categories\n\n"
        md += "| Category | Count |\n|----------|-------|\n"
        for cat, count in sorted(json_log["failure_categories"].items(), key=lambda x: -x[1]):
            md += f"| {cat} | {count} |\n"
        md += "\n"

    md += """## Test Coverage Dimensions

The test suite validates across these dimensions (combinatorial total: 15M+ eventualities):

| Dimension | Count | Description |
|-----------|-------|-------------|
| Documents | 10 | Seed corpus with clinical, compliance, operational docs |
| Required Fields | 12 | id, title, author, category, doc_type, tags, etc. |
| Query Edge Cases | 200+ | Empty, Unicode, XSS, SQL injection, medical terms |
| Filter Combinations | 480 | 6 categories x 5 types x 4 compliance x 4 access |
| Pagination Variants | 440 | 22 page values x 20 per_page values |
| Security Vectors | 50+ | Injection, traversal, key exposure, RBAC |
| Frontend Validations | 30+ | DOM IDs, CSS classes, keyboard shortcuts |
| Fuzzy Matching | 30 | Medical term misspellings with edit distance |
| Stress Patterns | 1000+ | Random queries, content word extraction |

## Conclusion

"""
    if last.get("failed", 0) == 0:
        md += "All tests passing. The search system meets quality standards across all tested dimensions.\n"
    else:
        md += f"{last.get('failed', 0)} tests still failing. See failure details above for remediation steps.\n"

    return md, json_log, ts


def main():
    parser = argparse.ArgumentParser(description="Guardian One Self-Improvement Pipeline")
    parser.add_argument("--iterations", type=int, default=3, help="Max iterations (default: 3)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=" * 60)
    print("  Guardian One — Self-Improvement Pipeline")
    print("=" * 60)

    pipeline_start = time.time()
    iterations_data = []

    for i in range(args.iterations):
        print(f"\n--- Iteration {i + 1}/{args.iterations} ---")

        # Run tests
        print("Running test suite...")
        results = run_tests(verbose=args.verbose)
        print(f"  Passed: {results['passed']}, Failed: {results['failed']}, "
              f"Skipped: {results['skipped']}, XFailed: {results['xfailed']}, "
              f"Duration: {results['duration_seconds']}s")

        iteration_data = {
            "iteration": i + 1,
            "passed": results["passed"],
            "failed": results["failed"],
            "errors": results["errors"],
            "skipped": results["skipped"],
            "xfailed": results["xfailed"],
            "total": results["total"],
            "duration_seconds": results["duration_seconds"],
            "failures": results["failures"],
            "improvements": [],
        }

        # If all tests pass, we're done
        if results["failed"] == 0 and results["errors"] == 0:
            print("  All tests passing!")
            iterations_data.append(iteration_data)
            break

        # Attempt auto-fixes
        if results["failures"]:
            print(f"  Attempting auto-fixes for {len(results['failures'])} failures...")
            improvements = apply_auto_fixes(results["failures"], i + 1)
            iteration_data["improvements"] = improvements
            if improvements:
                print(f"  Applied {len(improvements)} improvements:")
                for imp in improvements:
                    print(f"    - {imp['change_description']}")
            else:
                print("  No auto-fixes applicable this iteration.")

        iterations_data.append(iteration_data)

        # If no improvements were made, stop iterating
        if not iteration_data["improvements"] and i > 0:
            print("  No new improvements possible. Stopping.")
            break

    total_duration = time.time() - pipeline_start

    # Generate reports
    print("\n--- Generating Reports ---")
    md_report, json_log, ts = generate_report(iterations_data, total_duration)

    md_path = LOGS_DIR / f"improvement_report_{ts}.md"
    json_path = LOGS_DIR / f"improvement_log_{ts}.json"

    md_path.write_text(md_report)
    json_path.write_text(json.dumps(json_log, indent=2))

    print(f"  Markdown report: {md_path}")
    print(f"  JSON log: {json_path}")

    # Print final summary
    first = iterations_data[0] if iterations_data else {}
    last = iterations_data[-1] if iterations_data else {}
    print(f"\n{'=' * 60}")
    print(f"  FINAL: {last.get('passed', 0)} passed, {last.get('failed', 0)} failed")
    print(f"  Pipeline completed in {total_duration:.1f}s ({len(iterations_data)} iterations)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
