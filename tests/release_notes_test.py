"""
Tests for bin/make_release_notes.py

Tests cover the pure logic functions (extract_issue_numbers, generate_release_notes)
without calling gh or git.
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "make_release_notes",
    os.path.join(os.path.dirname(__file__), '..', 'bin', 'make_release_notes.py'),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
extract_issue_numbers = _mod.extract_issue_numbers
generate_release_notes = _mod.generate_release_notes


# ---------------------------------------------------------------------------
# extract_issue_numbers
# ---------------------------------------------------------------------------

def test_extract_fixes():
    assert extract_issue_numbers("fixes #123") == {123}

def test_extract_closes():
    assert extract_issue_numbers("closes #42") == {42}

def test_extract_resolves():
    assert extract_issue_numbers("resolves #7") == {7}

def test_extract_refs():
    assert extract_issue_numbers("refs #99") == {99}

def test_extract_bare_hash():
    assert extract_issue_numbers("See #55 for details") == {55}

def test_extract_multiple():
    assert extract_issue_numbers("fixes #1, closes #2, refs #3") == {1, 2, 3}

def test_extract_ignores_url():
    # /issues/123 in a URL should not be extracted
    assert 123 not in extract_issue_numbers("https://github.com/foo/bar/issues/123")

def test_extract_empty():
    assert extract_issue_numbers("") == set()

def test_extract_none():
    assert extract_issue_numbers(None) == set()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_pr(number, title, body="", url=None):
    return {
        'number': number,
        'title': title,
        'body': body,
        'url': url or f"https://github.com/Plant-Tracer/webapp/pull/{number}",
    }

def make_issue(number, title, url=None):
    return {
        'number': number,
        'title': title,
        'url': url or f"https://github.com/Plant-Tracer/webapp/issues/{number}",
    }


# ---------------------------------------------------------------------------
# generate_release_notes
# ---------------------------------------------------------------------------

def test_standalone_pr_is_included():
    """A PR with no issue references appears in the notes."""
    prs = [make_pr(10, "Refactor widget pipeline")]
    notes, _reviews = generate_release_notes(prs, {})
    assert any("PR #10" in line or "#10" in line for line in notes)
    assert not _reviews


def test_referenced_issues_are_included():
    """Issues referenced by any PR appear in the notes."""
    prs = [make_pr(20, "fixes #5: improve login flow", body="fixes #5")]
    issues = {5: make_issue(5, "Login flow is broken")}
    notes, _reviews = generate_release_notes(prs, issues)
    assert any("#5" in line for line in notes)


def test_version_bump_pr_is_omitted():
    """A 'Bump version' PR is silently omitted from notes and reviews."""
    prs = [make_pr(30, "Bump version to 1.2.3", body="refs #99")]
    issues = {99: make_issue(99, "Tag release 1.2.3")}
    notes, _reviews = generate_release_notes(prs, issues)
    assert not any("#30" in line for line in notes)
    assert not any("30" in line for line in _reviews)


def test_pr_with_refs_flagged_for_review():
    """A non-bump PR that references issues is flagged for human review."""
    prs = [make_pr(40, "Major feature overhaul", body="closes #7\ncloses #8")]
    issues = {
        7: make_issue(7, "Feature request A"),
        8: make_issue(8, "Feature request B"),
    }
    _notes, reviews = generate_release_notes(prs, issues)
    assert any("#40" in line for line in reviews)
    assert any("REVIEW" in line for line in reviews)


def test_issues_sorted_by_number():
    """Referenced issues appear in ascending numeric order."""
    prs = [make_pr(50, "fixes #30 and fixes #10", body="fixes #30\nfixes #10")]
    issues = {
        10: make_issue(10, "Issue ten"),
        30: make_issue(30, "Issue thirty"),
    }
    notes, _ = generate_release_notes(prs, issues)
    issue_lines = [l for l in notes if l.startswith("- [#")]
    numbers = [int(l.split("[#")[1].split("]")[0]) for l in issue_lines]
    assert numbers == sorted(numbers)


def test_mixed_milestone():
    """Realistic mix: issues, standalone PR, version-bump PR, and a flagged PR."""
    prs = [
        make_pr(100, "fixes #1: dark mode", body="fixes #1"),
        make_pr(101, "Add analytics dashboard"),            # standalone
        make_pr(102, "Bump version to 2.0.0", body="refs #5"),  # omit
        make_pr(103, "Overhaul settings page", body="refs #2"),  # flag
    ]
    issues = {
        1: make_issue(1, "Dark mode support"),
        2: make_issue(2, "Settings page redesign"),
        5: make_issue(5, "Tag release 2.0.0"),
    }
    notes, reviews = generate_release_notes(prs, issues)

    note_text = '\n'.join(notes)
    review_text = '\n'.join(reviews)

    assert "#1" in note_text          # issue included
    assert "#101" in note_text        # standalone PR included
    assert "#102" not in note_text    # version bump omitted from notes
    assert "#102" not in review_text  # version bump omitted from review too
    assert "#103" in review_text      # flagged PR appears in reviews
    assert "REVIEW" in review_text


def test_unknown_issue_produces_fallback_line():
    """If an issue can't be fetched, a fallback line is still emitted."""
    prs = [make_pr(200, "fixes #999", body="fixes #999")]
    notes, _ = generate_release_notes(prs, {})   # issue 999 not in dict
    assert any("#999" in line for line in notes)
