# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Plant Tracer is a Flask-based web application for uploading, managing, and annotating plant growth time-lapse videos at https://prod.planttracer.com/. It has a Python/Flask backend, a JavaScript frontend (jQuery loaded globally, with ES modules importing `$` from `utils.js`), DynamoDB for structured data, and S3 for video/frame storage.

## Documentation

When completing work on any Issue or PR, always review whether documentation under `docs/` needs to be updated to reflect the change. This includes:
- User-facing docs (`UserTutorial.rst`, etc.)
- Developer docs (`FlaskAPI.md`, `DynamoDB.rst`, `THEORY_OF_DESIGN.rst`, etc.)
- Release history (`ReleaseHistory.rst`)

If any screenshots in `docs/tutorial_images/` may be affected, flag them for the user rather than updating them automatically.

**`docs/Development/FlaskAPI.md` must be updated in the same commit or PR whenever `src/app/flask_api.py` changes** — document any new endpoints, changed parameters, or behavioral side effects.

After editing any file under `docs/`, always build and verify: `poetry run sphinx-build -W --keep-going -b html docs docs/_build/html`

## Git Workflow

Never commit or push directly to the `main` branch. All changes must go through a feature branch and be merged via Pull Request. Only proceed with a direct commit to `main` if the user explicitly says to override this rule.

Every commit message should reference a GitHub Issue number (preferred) or PR number (e.g. `fixes #123`, `refs #123`, or `refs PR #456`).

- **Automated commits** (Claude, Codex): always include a reference. If no relevant Issue or PR exists, ask the user — and commit without a reference only if the user explicitly approves.
- **Human commits**: before merging a PR, inspect all commits for missing references. If any are found, leave a PR review comment flagging them for the reviewer before merge.

Every PR body must include `fixes #N` or `refs #N` for each Issue the PR resolves or references. This is the canonical place GitHub uses to auto-close Issues on merge and that release note tooling uses to associate PRs with Issues.

## Common Commands

```bash
# Linting
make lint          # Python (pylint, threshold 10.0) + JS/HTML (eslint)
make pylint        # Python only
make eslint        # JS/HTML only
make mypy          # Type checking (optional)

# Testing
make check         # Full CI: lint + pytest + jscoverage
make pytest        # Python tests (requires local DynamoDB + Minio running)
make pytest-coverage  # Python tests with HTML coverage in htmlcov/
make jscoverage    # JavaScript Jest tests with coverage
npm test           # JS tests directly
npm run test-debug # JS tests with verbose output

# Run a single Python test module
AWS_REGION=local PYTHONPATH="lambda-resize/src:src" poetry run pytest tests/endpoint_test.py -v

# Local development
python3 bin/local_services.py minio start       # Start Minio (S3 emulator, ports 9000/9001)
python3 bin/local_services.py dynamodb start    # Start DynamoDB Local (port 8000)
make make-local-bucket                   # Create local S3 bucket
make make-local-demo                     # Create demo course and DB tables
make run-local-debug                     # Flask dev server at localhost:8080
```

## Architecture

### Backend (`src/app/`)
- `flask_app.py` — app factory and route registration
- `flask_api.py` — API Blueprint with REST endpoints (register, upload, list, etc.)
- `odb.py` — DynamoDB abstraction layer (courses, users, api_keys, movies)
- `odb_movie_data.py` — movie/frame data in DB
- `schema.py` — DynamoDB table definitions
- `odbmaint.py` — DB creation/maintenance
- `auth.py`, `apikey.py` — authentication
- `s3_presigned.py` — S3 presigned URLs and uploads
- `mailer.py` — email via SMTP or AWS SES
- `tracer.py` — plant motion tracing (VM only; Lambda uses vendored copy)

Route handlers should be thin; put business logic in `odb.py`, `mailer.py`, `s3_presigned.py`, etc.

### Frontend (`src/app/static/`, `src/app/templates/`)
`$` is jQuery. Browser pages load jQuery globally, and ES modules import `$` from `utils.js`, which re-exports the global jQuery instance.

### Data Storage
- **S3**: movies, frames, ZIP files. The bucket is always **pre-existing** and **outlives the CloudFormation stack** as the long-term archive. Because the bucket outlives DynamoDB, research/attribution metadata must also be written **into the MP4 file** (see `src/app/mp4_metadata_lib.py`, `docs/Development/MOVIE_METADATA.rst`).
- **DynamoDB**: tables prefixed by `DYNAMODB_TABLE_PREFIX` (e.g. `demo-`). Schema in `src/app/schema.py`; creation in `src/app/odbmaint.py`. CLI: `src/dbutil.py` (`--createdb`, `--makelink`, etc.).
- Lambda is invoked via its HTTP API, **not** via S3 bucket notifications.

### Lambda (`lambda-resize/`)
A separate Poetry project. App code from the main package is vendored into `resize_app/src/app/` via `make -C lambda-resize vend-app` before linting/testing. Imports in Lambda code use `from .src.app import odb` style — do not change these to import the top-level `app` package.

## Testing Strategy

Tests run against **real local services** (DynamoDB Local + Minio), not mocks. Fixtures in `tests/conftest.py` and `tests/fixtures/` handle setup automatically.

- Use `make pytest` / `make check` rather than running `pytest` directly — the Makefile sets the correct environment.
- If running `pytest` directly, always set `AWS_REGION=local` and `PYTHONPATH="lambda-resize/src:src"`.
- When AWS credential errors appear in tests, **do not change code** — first verify the environment is set correctly.
- Tests must **fail** when prerequisites are missing. Do not make tests skip or pass silently — that is the project owner's decision.
- Write function-style tests only (`def test_*()`); no test classes.

## Coding Standards

### Python
- Python 3.12+; Pylint must pass at threshold 10.0 before committing (`poetry run pylint src/app/...`).
- No Python autoformatter target is configured; follow existing local style and keep Pylint clean.
- All imports at the **top level** of the file — never inside functions (except `if __name__ == "__main__":` blocks). Never add `# pylint: disable=import-outside-toplevel`.
- Prefix intentionally unused parameters with `_` (e.g. `_event`); do not use `# pylint: disable=unused-argument`.
- Logging: `logger.info("msg %s", var)` style, not f-strings.
- Prefer minimal, focused diffs. Avoid duplicating existing logic or large-scale rewrites when making a targeted fix.
- `pyproject.toml` uses PEP 621 `[project]` table — do not use deprecated `[tool.poetry]` keys for name/version/description/authors/scripts.

### JavaScript
- `src/app/static/utils.js` is a shim that re-exports the global jQuery instance for ES modules.
- `make eslint` lints `src/app/static/` and `src/app/templates/`.
- Jest tests live in `jstests/`; run with `NODE_PATH=src/app/static`.

## Key Environment Variables

See `docs/EnvironmentVariables.rst` for the full list.

| Variable | Purpose |
|---|---|
| `AWS_REGION=local` | Use Minio/DynamoDB Local instead of real AWS |
| `PLANTTRACER_S3_BUCKET` | S3 bucket name (required) |
| `DYNAMODB_TABLE_PREFIX` | Table prefix, e.g. `demo-` (required) |
| `AWS_ENDPOINT_URL_S3` | Override S3 endpoint (Minio in dev) |
| `AWS_ENDPOINT_URL_DYNAMODB` | Override DynamoDB endpoint (local in dev) |
| `DEMO_COURSE_ID` | Enable demo mode |
| `PLANTTRACER_CREDENTIALS` | Path to SMTP/IMAP credentials ini file |

## Adding Routes and DB Functionality

- New API/web routes: add to `flask_api.py` (API Blueprint) or via `flask_app.py`; add Jinja2 templates under `src/app/templates/`; add tests in `tests/`.
- New DB functionality: extend `src/app/odb.py` or `odb_movie_data.py`; update `schema.py` for new tables/attributes; add tests in `tests/` (e.g. `odb_test.py`, `db_object_test.py`).
- Email: templates in `src/app/templates/email_*.html`; sending in `mailer.py`.

## CI/CD

`.github/workflows/ci-cd.yml` runs lint, pytest, and JS tests on push/PR to main/dev, on both macOS and Ubuntu with Python 3.12. Local equivalent: `make check`.

## Prepare Milestone for Release

When asked to prepare a milestone for a new release, given a previous release tag (e.g. `ver-X.Y.Z`) and a new milestone name (e.g. `Version-X.Y.Z+1`):

1. **Create the milestone** (`gh` has no `milestone` subcommand; use the API):
   ```bash
   gh api repos/Plant-Tracer/webapp/milestones --method POST -f title="<new-milestone-name>"
   # Note the "number" field in the response.
   ```

2. **Get the previous tag's commit timestamp**:
   ```bash
   sha=$(gh api repos/Plant-Tracer/webapp/git/refs/tags/<prev-tag> --jq '.object.sha')
   gh api repos/Plant-Tracer/webapp/git/commits/$sha --jq '.committer.date'
   ```

3. **Find all issues/PRs closed strictly after that timestamp**:
   ```bash
   gh api "repos/Plant-Tracer/webapp/issues?state=closed&since=<timestamp>&per_page=100" \
     --jq '.[] | {number: .number, title: .title, closed_at: .closed_at, milestone: .milestone.title}'
   ```
   Filter results by `closed_at` > tag timestamp. Exclude the version-bump PR for the previous release (it closes at essentially the same instant as the tag).

4. **Assign all qualifying items to the new milestone** (this automatically clears any previous milestone):
   ```bash
   for num in <numbers>; do
     gh api repos/Plant-Tracer/webapp/issues/$num --method PATCH -f milestone=<milestone-number> --jq '.number'
   done
   ```

5. **Verify**:
   ```bash
   gh api repos/Plant-Tracer/webapp/milestones --jq '.[] | {title: .title, open: .open_issues, closed: .closed_issues}'
   ```

## Creating a GitHub Release

After tagging, create a GitHub release from the tagged commit. The release title is the date formatted as `Month-DD-YYYY` (e.g., `May-16-2026`).

**Release notes** are a single flat list of Issues and any PRs whose work is not fully captured by Issues. Generate them with:

```bash
python3 bin/make_release_notes.py [--since-tag <previous-tag>]
```

The script finds all PRs merged to `main` since the previous release tag, includes all referenced Issues and any standalone PRs (no issue references), silently omits version-bump PRs, and flags other PRs that reference issues with `# REVIEW:` lines for human inspection. Review the output and resolve any `# REVIEW:` items before proceeding.

1. Run the script and review its output.
2. Present the draft list to the user for approval before creating the release.
3. Create the release:
   ```bash
   gh release create <tag> --title "<Month-DD-YYYY>" --notes "<notes>"
   ```

**Release titles must be unique.** If more than one release is made on the same day, append a count starting at `-2` (e.g., `May-16-2026`, `May-16-2026-2`, `May-16-2026-3`). Check existing titles first:
   ```bash
   gh release list --repo Plant-Tracer/webapp
   ```

Each line in the release notes should be a Markdown link to the issue/PR, e.g.:
```
- [#930](https://github.com/Plant-Tracer/webapp/issues/930) Documentation: Update UserTutorial to current prod functionality
- [#966](https://github.com/Plant-Tracer/webapp/issues/966) Fix ESLint no-undef error: list_users called bare in users.js
```

## Updating ReleaseHistory After a Release

After creating the GitHub release, open a PR to update `docs/ReleaseHistory.rst`:

1. Add a row to the release table at the top of the file (Name, Version, Date, link to the GitHub release tag).
2. Add a summary section for the new release (above the previous release's summary), with a bullet per significant change derived from the release notes. The act of updating ReleaseHistory itself need not be mentioned in the summary.

This PR should reference the tagging Issue (e.g. `refs #N`) so the work is traceable. It does **not** need its own separate GitHub Issue.

## Tagging a Release

Before tagging, the version number **must** be updated via a normal feature branch + PR and merged to `main`. Once the version bump PR is merged:

1. **Bump the version number** (via feature branch + PR, merged before tagging). Update exactly these two files:
   - `src/app/constants.py` — `__version__ = 'X.Y.Z'`
   - `pyproject.toml` — `version = "X.Y.Z"`

2. **Run the full CI check** and confirm it passes:
   ```bash
   make check
   ```

3. **Create a GitHub Issue** for the tag (so the tag references an issue, per project convention):
   ```bash
   gh issue create --title "Tag main branch as <tag-name>" \
     --body "All PRs for <milestone> merged. Tag main with \`<tag-name>\`." \
     --milestone "<milestone-name>"
   ```

4. **Tag and push** the already-bumped main (always use an annotated tag):
   ```bash
   git tag -a <tag-name> -m "refs #<issue-number>: tag main as <tag-name>"
   git push origin <tag-name>
   ```

5. **Close the issue** referencing the tag:
   ```bash
   gh issue close <issue-number> --comment "Tagged as \`<tag-name>\`."
   ```

Tag names follow the pattern `ver-X.Y.Z`.
