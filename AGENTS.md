# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

Every PR body must include an Issue keyword for each related Issue. Use `fixes #N`, `closes #N`, or `resolves #N` when the PR completely implements the Issue, so GitHub automatically closes it when merged into the default branch. Use `refs #N` only when the Issue intentionally remains open; it creates a cross-reference but does not auto-close the Issue. This is the canonical place GitHub uses to auto-close Issues on merge and that release note tooling uses to associate PRs with Issues.

## GitHub Identities

Use `@simsong-codex` for all GitHub activity: commits, pushes, issues, pull requests, comments, reviews, labels, and repository administration. The sole exception is requesting or re-requesting GitHub Copilot review, which must be performed as `@simsong` because that account has the required Copilot entitlement.

For that exception only, switch the active GitHub CLI account to `simsong`, request exactly `copilot-pull-request-reviewer[bot]` for the specified Plant-Tracer pull request, and switch immediately back to `simsong-codex`. Restore `simsong-codex` even if the request fails. Verify the resulting review-request event only after restoring `simsong-codex`; do not perform any other GitHub action while `simsong` is active.

### Codex commits and Codex-to-Done lifecycle

GitHub activity authored by Codex must use `@simsong-codex`; do not use the
personal `@simsong` account for writes, pushes, issues, pull requests, reviews,
or comments.

Before creating or amending a Codex-authored commit, configure and verify the
author and committer as `Codex AI Assistant <simsong+codex@acm.org>` and verify
the configured signing key belongs to that identity. SSH remote authentication
controls push access only; it does not set commit metadata. Verify each result
with `git log --format='%G? %GS %an <%ae> %cn <%ce>'`. When correcting an
existing commit, use `git commit --amend --reset-author -S` rather than only
amending the signature.

For every Codex-authored issue implementation, follow the **Codex-to-Done
lifecycle** in order:

1. Investigate the issue and current code, write an implementation-ready
   proposal, and ask the user to review it. Do not implement while proposal
   approval is pending.
2. After the user approves the proposal, implement it on a feature branch,
   including substantive tests and required documentation.
3. Fetch `origin/main` before committing and merge it into the feature branch,
   resolving and validating any conflicts. Create a signed Codex commit, push
   the branch, and open the pull request as a draft.
4. Request the Copilot bot with the exact GitHub API reviewer value
   `copilot-pull-request-reviewer[bot]`; do not use the incomplete value
   `copilot-pull-request-reviewer`. GitHub's UI Request control for Copilot is
   an equivalent fallback when the API response is ambiguous. Verify a Copilot
   pending-review entry or a `REVIEW_REQUESTED_EVENT`, not merely an HTTP
   success response.
5. Keep the pull request a draft while monitoring until a Copilot review or
   review thread actually appears. Do not report a request or response based
   only on a CLI command or an `@copilot` comment.
6. Address every actionable Copilot finding. For each pushed fix, reply on the
   exact Copilot thread with the commit and validation evidence, then request
   and monitor Copilot's re-review of that new commit. Do not manually resolve
   the thread; if GitHub resolves it automatically, report that fact.
7. While the pull request is open, repeatedly fetch `origin/main`: after each
   review or CI waiting interval, before pushing review fixes, and immediately
   before marking the pull request ready. Merge new mainline commits into the
   feature branch, resolve conflicts, rerun proportionate validation, and push
   the merge before continuing.
8. Keep Codecov passing when practical by testing substantive logic, but do not
   add pro-forma tests or distort the implementation merely to raise coverage.
   Treat Codecov as a completion blocker only when repository rules make it a
   required check.
9. After Copilot is feedback-free, required CI checks are green, and the branch
   contains current `origin/main`, mark the pull request ready for review and
   assign it to `@simsong`.

The lifecycle completes only after the current head's Copilot review and
required CI are clear, the feature branch contains current `origin/main`, the
pull request is ready for review, and `@simsong` is assigned. If validation or
feedback remains, retain draft status and report the exact blocker.

When the Codex-to-Done timer is active, wake every 20 minutes and reconcile
live GitHub state. For the current release milestone, scan its open issues
assigned to `@simsong-codex`, then resume the highest-priority unblocked work or
pending pull-request review/CI follow-through. Verify milestone, assignment, PR
head, Copilot state, and checks live; do not rely on an earlier heartbeat. Do
not change issue assignments or milestones, approve, merge, or close anything
without explicit user instruction. If there is no in-scope work or nothing has
changed, return a quiet heartbeat; otherwise report the exact next action or
blocker.

Do not approve or merge a pull request unless explicitly asked. Do not close
GitHub issues unless the repository owner explicitly instructs you to do so.

Delete a local branch once it has merged into `main`, but first verify it is an
ancestor of the current `main`; preserve unmerged branches and linked-worktree
files.

Update `docs/ReleaseHistory.rst` in the same pull request for every
user-visible behavior, build or platform-support, packaging, or documentation
change. Do not add release-history entries for test-only or purely internal
refactors.

## Beads Workflow

This repository uses Beads for local/agent task tracking. Beads issue data is stored in a Dolt database and syncs separately from normal Git commits.

- Before starting issue work, run `bd ready` or `bd list`, then inspect the relevant issue with `bd show <id>`.
- For the lambda-only migration, use epic `webapp-cgr` and its child issues (`webapp-cgr.1`, etc.) as the Beads work breakdown. Keep GitHub references (`gh-450`, `gh-699`, `gh-1110`) in Beads `external_ref` or metadata.
- Claim work with `bd update <id> --claim`; update status/comments as work progresses.
- Pull and push Beads data with `bd dolt pull` and `bd dolt push`. A normal `git push` is not enough unless the installed Beads hook successfully auto-pushes Dolt data; when in doubt, run `bd dolt push` explicitly.
- Commit only lightweight Beads project files such as `.beads/config.yaml`, `.beads/metadata.json`, `.beads/README.md`, `.beads/hooks/*`, `.beads/.gitignore`, `.beads/interactions.jsonl`, and optionally `.beads/issues.jsonl`.
- Do **not** commit live/runtime Beads data such as `.beads/embeddeddolt/`, `.beads/dolt/`, `.beads/backup/`, lock files, sockets, `export-state.json`, `last-touched`, or `.beadso/`.
- Beads issues complement GitHub Issues; commit messages and PR bodies must still reference GitHub Issue or PR numbers per the Git workflow above.

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
make lambda-web-check     # Lambda-web adapter lint/tests; does not replace Flask local tests
make lambda-resize-check  # Lambda-resize lint/tests
make template-lint        # SAM/cfn-lint validation
make jscoverage    # JavaScript Jest tests with coverage
npm test           # JS tests directly
npm run test-debug # JS tests with verbose output

# Run a single Python test module
env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE AWS_REGION=local PYTHONPATH=".:src:lambda-web/src:lambda-resize/src" poetry run pytest tests/endpoint_test.py -v

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
- **DynamoDB**: tables prefixed by `DYNAMODB_TABLE_PREFIX` (e.g. `demo-`). Schema in `src/app/schema.py`; creation in `src/app/odbmaint.py`. CLI: `poetry run dbutil` (`createdb`, `makelink`, etc.).
- Lambda is invoked through its HTTP API and SQS. S3 Object Created events also
  reach lambda-resize through EventBridge rules filtered to each stack's
  ``uploads/{stack}/`` prefix; do not attach direct Lambda notifications to the
  shared bucket.

### Lambda (`lambda-resize/`)
A separate Poetry project. App code from the main package is vendored into `resize_app/src/app/` via `make -C lambda-resize vend-app` before linting/testing. Imports in Lambda code use `from .src.app import odb` style — do not change these to import the top-level `app` package.

### Lambda-only Migration

The accepted migration goal for #450/#699 is a lambda-only distribution with no virtual machine in the SAM deployment path:

- Add a separate `lambda-web` function for Flask HTML pages and Flask `/api/*` metadata/application routes.
- Keep the existing `lambda-resize` function as the vision/video/SQS tracing service; do not merge web traffic into the vision package.
- Expose the application through one public HTTPS hostname/front door. The two Lambda functions do not require separate product domain names; route HTML, Flask `/api/*`, and `/static/*` to `lambda-web`, and `/resize-api/*` to `lambda-resize`.
- Remove VM resources and parameters from the SAM path, including EC2, VPC/subnet/route-table resources, security groups, EIP, instance profile, SSH/reload workflows, `GitRepoUrl`, and `GitBranch`.
- Deploy current built artifacts from the current checkout/branch; do not rely on instance boot-time `git clone` or branch checkout.
- Keep application static assets served by `lambda-web` for the initial migration, as Flask serves them now. Do not move static assets to S3/CloudFront until there is a versioned filename or asset-manifest plan.
- Keep the movie S3 bucket pre-existing and long-lived. Keep DynamoDB tables external to CloudFormation and created through `poetry run dbutil` from `etc/dynamodb_tables.json`.
- Keep path routing explicit on that single front door: `/resize-api/*` goes to `lambda-resize`; HTML, Flask `/api/*`, and `/static/*` go to `lambda-web`. Movie-data is resize-owned and lives at `/resize-api/v1/movie-data`; do not reintroduce `/api/v1/movie-data` compatibility.
- `lambda-web` uses SnapStart on the published `live` alias. `lambda-resize` does not use SnapStart unless measured and deliberately enabled later.
- `make sam-deploy` and `make sam-deploy-guided` refuse redeploying the same app version to the same stack; bump `pyproject.toml` before deploying again.
- All build, test, local service, static publish, SAM validation, deployment, and smoke workflows should be Makefile targets.
- Local Flask development and testing remain required. `make run-local-debug`, `make run-local-demo-debug`, and `make pytest` are still the primary local workflow.
- Lambda-web handler tests and SAM local tests are additive checks for API Gateway/Lambda event shape. They do not replace normal Flask route tests.

## Testing Strategy

Tests run against **real local services** (DynamoDB Local + Minio), not mocks. Fixtures in `tests/conftest.py` and `tests/fixtures/` handle setup automatically.

- Use `make pytest` / `make check` rather than running `pytest` directly — the Makefile sets the correct environment.
- If running `pytest` directly, always unset `AWS_PROFILE`/`AWS_DEFAULT_PROFILE`, set `AWS_REGION=local`, and use `PYTHONPATH=".:src:lambda-web/src:lambda-resize/src"`.
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
| `DYNAMODB_TABLE_PREFIX` | Table prefix, e.g. `demo-` (required). `DDBO` normalizes `prefix` and `prefix-` to exactly one trailing hyphen before constructing table names. |
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

**Release notes** are a single flat list of Issues and any PRs whose work is not fully captured by Issues. To generate them:

1. Fetch all closed items in the milestone via `gh api`.
2. **Include all Issues** in the milestone.
3. For each **PR** in the milestone:
   - Parse the PR body and title for issue references (`fixes #N`, `closes #N`, `resolves #N`, `refs #N`, bare `#N`, etc.).
   - **No issue references** → include the PR (standalone work).
   - **Has issue references** → read the PR body against the referenced issues' bodies/titles. If the PR describes changes not covered by any referenced issue, include it (or flag it for human review if uncertain). If fully covered, omit it.
4. Present the draft list to the user for approval before creating the release.
5. Create the release:
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

## Tagging a Release

Before tagging, the version number **must** be updated via a normal feature branch + PR and merged to `main`. Once the version bump PR is merged:

1. **Bump the version number** (via feature branch + PR, merged before tagging). Update exactly this file:
   - `pyproject.toml` — `version = "X.Y.Z"`

2. **Create a GitHub Issue** for the tag (so the tag references an issue, per project convention):
   ```bash
   gh issue create --title "Tag main branch as <tag-name>" \
     --body "All PRs for <milestone> merged. Tag main with \`<tag-name>\`." \
     --milestone "<milestone-name>"
   ```

3. **Tag and push** the already-bumped main (always use an annotated tag):
   ```bash
   git tag -a <tag-name> -m "refs #<issue-number>: tag main as <tag-name>"
   git push origin <tag-name>
   ```

4. **Close the issue** referencing the tag:
   ```bash
   gh issue close <issue-number> --comment "Tagged as \`<tag-name>\`."
   ```

Tag names follow the pattern `ver-X.Y.Z`.
