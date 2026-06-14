#!/usr/bin/env python3
"""
Generate release notes for a GitHub release.

Finds all PRs merged to main since the last release tag, then produces
a formatted markdown list suitable for use with `gh release create --notes`.

Rules (matching the CLAUDE.md release process):
  - All Issues referenced by any merged PR are included.
  - PRs with no issue references are included as standalone entries.
  - Version-bump PRs (title starts with "Bump version") are silently omitted
    as they are always fully captured by their referenced issue.
  - Other PRs that reference issues are flagged with "# REVIEW:" for human
    inspection — the human decides whether the PR adds content beyond its issues.

Usage:
    python3 bin/make_release_notes.py [--since-tag TAG]

Output goes to stdout; progress/warnings go to stderr.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime

REPO = "Plant-Tracer/webapp"

# Matches: fixes #N, closes #N, resolves #N, refs #N, ref #N, bare #N
# Avoids matching URLs like /issues/123 by requiring word boundary before #
ISSUE_REF_RE = re.compile(
    r'(?:(?:fix(?:es)?|clos(?:es)?|resolv(?:es)?|refs?)\s+#(\d+))'
    r'|(?:(?<![/\w])#(\d+))',
    re.IGNORECASE,
)

VERSION_BUMP_RE = re.compile(r'^bump\s+version', re.IGNORECASE)


def extract_issue_numbers(text):
    """Return the set of issue numbers referenced in text."""
    numbers = set()
    for m in ISSUE_REF_RE.finditer(text or ''):
        n = m.group(1) or m.group(2)
        numbers.add(int(n))
    return numbers


def is_version_bump_pr(pr):
    """Return True if this PR is a routine version-bump commit."""
    return bool(VERSION_BUMP_RE.match(pr.get('title', '')))


def generate_release_notes(prs, issues):
    """
    Produce release note lines from a list of PR dicts and an issue dict.

    Args:
        prs: list of dicts with keys: number, title, body, url
        issues: dict mapping issue_number (int) -> dict with keys: number, title, url

    Returns:
        (note_lines, review_lines) — two lists of strings.
        note_lines: the formatted release note entries.
        review_lines: "# REVIEW:" lines for human inspection.
    """
    # Collect every issue number referenced across all PRs
    all_issue_refs = set()
    pr_refs = {}
    for pr in prs:
        refs = extract_issue_numbers(pr.get('title', '') + '\n' + (pr.get('body') or ''))
        pr_refs[pr['number']] = refs
        all_issue_refs.update(refs)

    note_lines = []
    review_lines = []

    # Include all referenced issues, sorted by number
    for n in sorted(all_issue_refs):
        if n in issues:
            issue = issues[n]
            note_lines.append(f"- [#{n}]({issue['url']}) {issue['title']}")
        else:
            note_lines.append(f"- [#{n}](https://github.com/{REPO}/issues/{n}) (issue not found)")

    # Process PRs
    for pr in sorted(prs, key=lambda p: p['number']):
        refs = pr_refs[pr['number']]
        if not refs:
            # Standalone PR — include it
            note_lines.append(f"- [#{pr['number']}]({pr['url']}) {pr['title']}")
        elif is_version_bump_pr(pr):
            # Version bumps are always fully captured by their issue — omit silently
            pass
        else:
            # PR references issues: flag for human review
            ref_str = ', '.join(f'#{n}' for n in sorted(refs))
            review_lines.append(
                f"# REVIEW: PR #{pr['number']} \"{pr['title']}\" — "
                f"references {ref_str}; verify fully captured by those issues"
            )

    return note_lines, review_lines


# ---------------------------------------------------------------------------
# gh / git helpers (separated for testability)
# ---------------------------------------------------------------------------

def run_gh(*args):
    """Run a gh CLI command and return parsed JSON."""
    result = subprocess.run(['gh', *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_latest_tag():
    """Return the most recent ver-* release tag."""
    result = subprocess.run(
        ['git', 'tag', '--sort=-version:refname', '--list', 'ver-*'],
        capture_output=True, text=True, check=True,
    )
    tags = [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]
    if not tags:
        raise RuntimeError("No ver-* release tags found in this repository.")
    return tags[0]


def get_tag_timestamp(tag):
    """Return the ISO 8601 commit timestamp for a tag."""
    result = subprocess.run(
        ['git', 'log', '-1', '--format=%aI', tag],
        capture_output=True, text=True, check=True,
    )
    ts = result.stdout.strip()
    if not ts:
        raise RuntimeError(f"Could not determine timestamp for tag {tag!r}.")
    return ts


def fetch_merged_prs_since(timestamp):
    """Return PRs merged to main after timestamp (ISO 8601 string)."""
    prs = run_gh(
        'pr', 'list',
        '--repo', REPO,
        '--base', 'main',
        '--state', 'merged',
        '--json', 'number,title,body,mergedAt,url',
        '--limit', '500',
    )
    cutoff = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    return [
        pr for pr in prs
        if datetime.fromisoformat(pr['mergedAt'].replace('Z', '+00:00')) > cutoff
    ]


def fetch_issue(number):
    """Fetch a single issue's details. Returns None on failure."""
    try:
        return run_gh('issue', 'view', str(number),
                      '--repo', REPO,
                      '--json', 'number,title,url')
    except subprocess.CalledProcessError:
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            'Generate release notes from PRs merged since the last release tag. '
            'Output is printed to stdout; review flags go at the end.'
        )
    )
    parser.add_argument(
        '--since-tag',
        metavar='TAG',
        help='Generate notes for PRs merged after this tag (default: latest ver-* tag)',
    )
    args = parser.parse_args()

    since_tag = args.since_tag or get_latest_tag()
    print(f"# Generating release notes since tag: {since_tag}", file=sys.stderr)

    timestamp = get_tag_timestamp(since_tag)
    print(f"# Tag timestamp: {timestamp}", file=sys.stderr)

    prs = fetch_merged_prs_since(timestamp)
    print(f"# Merged PRs found: {len(prs)}", file=sys.stderr)
    for pr in sorted(prs, key=lambda p: p['number']):
        print(f"#   PR #{pr['number']}: {pr['title']}", file=sys.stderr)

    # Collect all referenced issue numbers
    all_issue_refs = set()
    for pr in prs:
        refs = extract_issue_numbers(pr.get('title', '') + '\n' + (pr.get('body') or ''))
        all_issue_refs.update(refs)

    # Fetch issue details
    issues = {}
    for n in sorted(all_issue_refs):
        issue = fetch_issue(n)
        if issue:
            issues[n] = issue
        else:
            print(f"# WARNING: could not fetch issue #{n}", file=sys.stderr)

    note_lines, review_lines = generate_release_notes(prs, issues)

    for line in note_lines:
        print(line)
    if review_lines:
        print()
        for line in review_lines:
            print(line)


if __name__ == '__main__':
    main()
