Release Process
===============

This page documents the end-to-end process for creating a Plant Tracer release. The process is designed to be carried out with Claude Code assistance. All steps assume you are working in the ``webapp`` repository root and are authenticated with ``gh``.

See `Issue #992 <https://github.com/Plant-Tracer/webapp/issues/992>`_ for known gaps and open questions in this process.

Overview
--------

1. Merge all feature PRs for the release
2. Bump the version number (PR)
3. Prepare the GitHub milestone
4. Tag the release
5. Generate release notes and create the GitHub release

Step 1 — Merge Feature PRs
----------------------------

Ensure all Issues and PRs intended for this release are merged to ``main`` and CI is green (``make check``).

Step 2 — Bump the Version Number
---------------------------------

The version number **must** be updated via a normal feature branch + PR and merged to ``main`` before the tag is created (Step 4). Do not skip this step — two releases shipped with a stale version number because it was omitted.

Update exactly **two files** (do not update ``lambda-resize``; its version is generated automatically):

- ``pyproject.toml`` — ``version = "X.Y.Z"``
- ``src/app/constants.py`` — ``__version__ = 'X.Y.Z'``

Create an Issue for the bump, branch off ``main``, commit the changes referencing the issue, open a PR, and merge it before proceeding to Step 4.

Step 3 — Prepare the GitHub Milestone
--------------------------------------

Create a milestone named ``Version-X.Y.Z`` and populate it with all Issues and PRs closed since the previous release tag.

.. note::
   ``gh`` has no ``milestone`` subcommand; use ``gh api`` directly.

.. code-block:: bash

   # 1. Create the milestone; note the "number" in the response
   gh api repos/Plant-Tracer/webapp/milestones \
     --method POST -f title="Version-X.Y.Z"

   # 2. Get the previous tag's commit timestamp
   sha=$(gh api repos/Plant-Tracer/webapp/git/refs/tags/ver-X.Y.Z-prev \
         --jq '.object.sha')
   gh api repos/Plant-Tracer/webapp/git/commits/$sha \
     --jq '.committer.date'

   # 3. Find all issues/PRs closed strictly after that timestamp
   gh api "repos/Plant-Tracer/webapp/issues?state=closed&since=<timestamp>&per_page=100" \
     --jq '.[] | {number: .number, title: .title, closed_at: .closed_at, milestone: .milestone.title}'

Filter the results by ``closed_at`` > tag timestamp. **Exclude** the version-bump PR for the *previous* release (it closes at essentially the same instant as the previous tag).

.. code-block:: bash

   # 4. Assign all qualifying items to the new milestone
   #    (this automatically removes them from any previous milestone)
   for num in <numbers>; do
     gh api repos/Plant-Tracer/webapp/issues/$num \
       --method PATCH -f milestone=<milestone-number> --jq '.number'
   done

   # 5. Verify
   gh api repos/Plant-Tracer/webapp/milestones \
     --jq '.[] | {title: .title, open: .open_issues, closed: .closed_issues}'

Step 4 — Tag the Release
--------------------------

Version tagging is done directly on ``main`` (not via a PR).

.. code-block:: bash

   # 1. Create a tracking Issue and add it to the milestone
   gh issue create \
     --title "Tag main branch as ver-X.Y.Z" \
     --body "All PRs for Version-X.Y.Z merged. Tag main with \`ver-X.Y.Z\`." \
     --milestone "Version-X.Y.Z"

   # 2. Switch to main and pull (version bump PR must already be merged)
   git checkout main && git pull

   # 3. Create an annotated tag on the already-bumped main (always use -a)
   git tag -a ver-X.Y.Z -m "refs #<issue-number>: tag main as ver-X.Y.Z"
   git push origin ver-X.Y.Z

   # 4. Close the tracking Issue
   gh issue close <issue-number> --comment "Tagged main as \`ver-X.Y.Z\`."

Tag names follow the pattern ``ver-X.Y.Z``.

Step 5 — Generate Release Notes and Create the Release
-------------------------------------------------------

Release notes are a single flat list of Issues and any PRs whose work is not fully captured by referenced Issues.

**Generating the list:**

1. Fetch all closed items in the milestone via ``gh api``.
2. **Include all Issues** in the milestone.
3. For each **PR** in the milestone:

   - Parse the PR body and title for issue references (``fixes #N``, ``closes #N``, ``resolves #N``, ``refs #N``, bare ``#N``, etc.).
   - **No issue references** → include the PR (standalone work).
   - **Has issue references** → read the PR body against the referenced issues' bodies/titles. If the PR describes changes not covered by any referenced issue, include it (or flag for human review if uncertain). If fully covered, omit it.

4. Present the draft list for approval before creating the release.

**Format:**

Each line should be a Markdown link::

   - [#930](https://github.com/Plant-Tracer/webapp/issues/930) Documentation: Update UserTutorial to current prod functionality

Add a short descriptive summary sentence at the top (not part of the list), followed by a blank line.

**Creating the release:**

.. code-block:: bash

   gh release create ver-X.Y.Z \
     --title "<Month-DD-YYYY>" \
     --notes "<notes>"

**Release title rules:**

- Format: ``Month-DD-YYYY`` (e.g., ``May-16-2026``)
- Titles must be unique. If more than one release is made on the same day, append a count starting at ``-2`` (e.g., ``May-16-2026-2``).
- Check existing titles before creating: ``gh release list --repo Plant-Tracer/webapp``

Known Gaps
----------

See `Issue #992 <https://github.com/Plant-Tracer/webapp/issues/992>`_ for the current list of known gaps in this process, including:

- Ensuring the version bump is never forgotten
- Updating ``ReleaseHistory.rst`` as part of each release
- Confirming CI is green before tagging
- Handling PRs that arrive after milestone prep
- Potential for scripting the release notes generation
