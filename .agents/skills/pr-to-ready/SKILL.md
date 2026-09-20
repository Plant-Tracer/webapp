---
name: pr-to-ready
description: Carry an authorized issue or pull request through implementation, validation, Copilot review fixes, and verified human-review handoff. Also use for codex-to-complete and codex-to-ready; merging is separate.
---

<!-- Generated from ~/.agents/skills/pr-to-ready/SKILL.md; do not edit. -->

# pr-to-ready

`pr-to-ready` is the canonical name. `codex-to-complete` and `codex-to-ready`
are equivalent aliases. Recognize the older names `Copilot-to-Ready`,
`copilot-to-complete`, and `Codex-to-Done` as the same workflow.

Read the repository's `AGENTS.md` for project-specific validation, identity,
proposal, review-channel, and handoff requirements. Those explicit local
requirements supplement this shared procedure and control documented exceptions.

## Authorization and roles

An explicit request to perform this workflow authorizes the task's fixes,
validation, signed commits, branch pushes, draft PR creation or updates, review
requests, exact-thread replies, and final ready state, human-review request,
and assignment, plus the verified local cleanup below. The active-work approval
gate still applies; invoking this workflow alone does not approve an identified
conflict. Continue already-authorized work without repeated permission questions. Merely loading these instructions does not authorize publication.
Do not approve or merge a PR, close an issue or superseded PR, deploy, or change
remote services unless separately authorized. Do not expand a single-PR task
into unrelated repository work.

- **Implementer (Codex, Claude, or Copilot coding agent):** own the fix and the
  complete validation/review/handoff cycle. Use the repository-authorized
  account and honest author identity; Claude and Copilot must not claim to be
  Codex or use its signing identity. Codex uses `simsong-codex` and its verified
  Codex signing key. Honor explicit repository account exceptions. If the
  required identity or signing facility is unavailable, preserve the work and
  report that concrete blocker; never silently use a personal identity.
- **Reviewer (Copilot code review, or another agent assigned only to review):**
  review the current diff against intended behavior, project requirements,
  substantive tests, and regression risks. Give actionable findings with file
  locations and evidence. Reassess fixes and exact-thread explanations; do not
  repeat a disproved finding without new evidence. Do not invent defects,
  require coverage-only tests, or modify, publish, assign, approve, or merge as
  part of a review-only role. The implementer owns the lifecycle; a review-only
  agent does not request a review of itself.
- **Human (`simsong` here):** receives the ready PR, judges disputed findings,
  and decides approval and merge. Neither an automated review nor a ready
  state substitutes for that decision.

## Procedure

Maintain a concise task ledger covering every explicit user request, including
follow-up changes and cleanup. Record completed items with evidence, pending
items with their next action, and blockers with the exact missing prerequisite.
Reconcile this ledger before every handoff; do not silently drop an item when
the conversation continues or context is compacted.

1. Verify the repository, remote, base, current PR head, all open PRs, active
   tasks, linked checkouts, and working-tree state. Complete the active-work
   approval gate below before creating a branch or editing. Preserve unrelated
   or dirty work; reuse the task's existing checkout, or create one project-local
   `.tmp` worktree only when isolation is needed and approved overlaps are
   addressed. Investigate producers, consumers, tests, generated artifacts,
   and documentation. Respect the repository's explicit proposal requirement.
2. Implement and update relevant documentation. Before each commit and push,
   re-read the requested invariant and review the complete intended diff and
   status. Run proportionate validation through the repository's Makefile;
   exercise actual behavior and inspect relevant artifacts. Preserve meaningful
   test assertions and fix causes instead of weakening checks.
3. Verify author, committer, signing key, and push authentication separately.
   Sign commits with the implementing agent's authorized identity and verify
   the resulting signature. Publish only intended changes to the correct branch
   with a matching draft PR; reuse an existing PR. Verify its head equals the
   pushed SHA. Keep it draft while validation or actionable feedback remains.
4. Immediately after publishing a draft PR or pushing a new head, request
   Copilot review before entering the waiting phase. This is a required action,
   not an optional suggestion or a substitute for scheduling a monitor. Use the
   repository's required channel; otherwise prefer
   `gh pr edit <number> --add-reviewer '@copilot'`. This reviewer argument is not
   an `@copilot` comment mention; never request review through a comment mention.
   Verify a pending Copilot reviewer or review-request timeline event and record
   the requested head SHA and time; command success alone is not evidence.
   If a request fails, verify authentication and the explicitly authorized
   account fallback. When the user or repository authorizes `simsong` solely
   for Copilot review requests, use that account only for the request, then
   restore `simsong-codex` even on failure. Keep commits, pushes, other PR edits,
   and thread replies under `simsong-codex`. Never infer permission to use a
   personal account for other actions or switch to browser control against the
   user's preference. If authorized authentication is unavailable, report the
   exact missing login action. Keep the PR draft and report review as **not
   requested** until verified; do not describe that state as waiting for Copilot.
5. Wait for the review and required CI on the current head. Address every valid
   actionable finding; explain incorrect findings with evidence. Reply in each
   finding's exact review thread with the fixing SHA and Makefile validation.
   Do not manually resolve reviewer threads. After every push, request and
   verify another review; an earlier-head review does not clear the new head.
   A submitted review without remaining actionable findings is sufficient;
   Copilot need not issue an approval verdict.
6. Continue through CI failures and re-review. Use the repository's interval
   when specified, otherwise ten-minute checks. If continuing across turns
   requires scheduling, use an available task-scoped heartbeat, avoid duplicate
   monitors and stay quiet on unchanged state. After human-review handoff,
   switch the monitor to post-merge cleanup as described below. Do not
   claim monitoring is active unless it was actually created. If scheduling or
   another external prerequisite is unavailable, report the exact next step.
7. When current-head review is clear and required CI and local checks pass,
   mark ready, request human review from `simsong`, and assign the PR to
   `simsong`. Verify all three actions and the final head live. Report the PR,
   SHA, validation, review outcome, and limitations. An explicit local review-loop
   exception can permit a disputed human handoff, but never call Copilot clear
   in that case. Missing reviews, failed required checks, and valid unfixed
   defects are blockers, not a successful review loop.
8. Perform the checkout cleanup below before reporting handoff: reconcile all
   task work, remove eligible clean and fully published checkouts, and report
   each retained path with its reason and next action. Keep unmerged branch
   refs and the PR; finish branch cleanup after the human merges.

## Active-work approval gate

Compare the proposed scope with every open PR's base, head, diff, and commits;
inspect local staged, unstaged, untracked, and unpublished work, and available
active-task status. Include tasks awaiting review or merge. Check overlapping
files and behavior, shared dependencies, generated outputs, build resources,
and instruction/configuration changes. A clean textual merge or separate
worktree does not establish independence. If required status is unavailable,
report the gap; do not claim the conflict check passed.

If the task potentially conflicts with active work, list each affected PR/task
by number or exact title, branch and checkout, the overlapping files or behavior,
and the likely interference. Distinguish observed overlap from uncertainty.
Present a concrete proposal to wait, reuse/consolidate the existing work, or
coordinate isolated changes, then obtain explicit user approval before the
conflicting edits, branch creation, integration, publication, or cleanup.
A warning alone is insufficient. Continue read-only investigation and clearly
independent work while waiting; silence is not approval. Explain that this
section requires the approval and link to this SKILL.md.

Record the approved scope and coordination plan in the task ledger. Recheck
before integration/push and whenever the scope or active work changes. Reuse
approval for the same disclosed overlap; seek new approval only for a materially
new conflict or changed plan. If no potential conflict is found, record the
evidence and proceed without an extra approval question.

## Completion and continuity

Do not leave task work stranded in `.tmp` checkouts. Before handoff, inventory
every checkout used by the task, including staged, unstaged, and untracked
source changes and local-only commits. Reconcile intended work into the
delivery branch, resolve conflicts without overwriting newer fixes, validate,
sign, and publish it in the matching PR. Record each checkout's disposition
and the delivery commit or concrete evidence that its changes are already
included or superseded. A clean checkout can still contain unpublished commits;
a merged checkout HEAD does not account for its uncommitted changes.

Moving a checkout, saving a patch or stash, making a local backup commit, or
merely reporting that it is dirty does not integrate its work and does not
complete the task. If related work is recoverable within the authorized scope,
finish integrating it. Preserve genuinely unrelated, ambiguous, or actively
edited work and ask for the specific decision needed; do not silently bundle
it into the PR or discard it. Never commit credentials, private evidence, or
generated caches merely to make a checkout clean.

While authorized work can proceed, continue it: fix failures, rerun validation,
publish the fix, and obtain current-head re-review. Do not stop after a partial
milestone or replace feasible work with instructions for the user to do it.
Before reporting success, verify the final head, required checks, review
findings, ready state, human reviewer/assignee, and every item in the task ledger.
Never claim a queued action, attempted click, earlier-head result, or proposed
automation is completed work.

If waiting is the only remaining action, establish and verify the quiet
heartbeat before ending the turn, with the PR, head, pending items, next check,
and completion conditions in its prompt. A scheduled continuation is still
pending work, not success. If no continuation mechanism is available or the
next step requires user authority or login, report the concrete blocker and
ask only for that missing action. Do not describe blocked work as complete.

Completion of review means verified human-review handoff. A push, review
request, or thread reply alone is incomplete. Merge remains a separate human
decision; never merge merely to trigger cleanup.
Ready-for-review completes only the review phase. Post-merge cleanup remains
pending for retained checkouts and branch refs until the human merges and the
cleanup checks below finish, or a specific preservation blocker is reported. Keep those outcomes distinct.

## Checkout cleanup at handoff

After validation and publication, inventory every task-owned checkout. Fetch
remote refs and record each path, branch, local HEAD, remote branch SHA, and PR.
A checkout is eligible for removal only when its intended work is reconciled,
all local commits are reachable from the verified remote branch, the matching
open PR head equals that remote SHA, and no task or process still needs it.
Check staged, unstaged, untracked, and ignored files. Preserve private evidence,
source data, and non-rebuildable artifacts outside the checkout, with recorded
paths and verified hashes, before removal; caches alone are rebuildable.
Never treat a stash or backup as publication of intended source work.

From another checkout, remove eligible linked worktrees with non-force
`git worktree remove <exact-path>`. Do not remove the primary/shared checkout.
Keep local branches and remote PRs until merge is verified. If a repository
requires keeping an unmerged checkout, retain it and report that requirement
unless the user explicitly authorizes earlier removal. Preserve dirty,
unpublished, active, or uncertain checkouts and report each concrete blocker;
integrate recoverable task work rather than ending with an unexplained dirty
checkout. Do not reset or broadly clean files to satisfy this step.

Remove retired checkout entries from the shared-skill distribution inventory.
Recheck the worktree list, path absence, and surviving branch/PR refs; record
removed paths, retained paths, and artifact locations in the final handoff.
If review later requires edits, resume from the verified PR head and repeat
validation, publication, review, and cleanup. Post-merge branch cleanup still
applies when the checkout was already removed at handoff.

## Post-merge checkout cleanup

After handoff, retain a quiet ten-minute task heartbeat (or update the existing
one) to detect the human's merge and finish local cleanup. If scheduling is
unavailable, report that cleanup is pending and must be resumed after merge.
Do not claim that a ready, closed, or superseded PR was merged.

Once GitHub confirms the PR is merged, fetch and prune `origin`. Before removing
each task-owned `.tmp` checkout, record its path, branch, and HEAD; verify its
commits are in current `origin/main`, or prove patch equivalence for squash or
rebase merges. Check tracked changes, untracked files, and ignored artifacts:
private evidence, source data, and other non-rebuildable files must be retained.
Do not infer safety from an empty ordinary `git status` alone.

From a different checkout, use `git worktree remove` on the exact verified path,
then delete only its fully represented local branch. If the checkout was already
removed at handoff, verify the surviving branch against current main before
deleting that ref. Do not use force removal,
recursive deletion of `.tmp`, or reset/checkout commands to erase dirty work.
Preserve and report dirty, unmerged, active, or uncertain checkouts with their
specific blockers; a request to clean all checkouts does not make their work
disposable. Related stranded work must go through the integration and review
steps above before cleanup; if discovered after merge, use a follow-up PR rather
than silently dropping it. Never merge unrelated branches just to make cleanup possible.
If the shared-skill distribution inventory names a retired checkout, remove
that exact entry so the next sync neither recreates it nor fails on its absence.

Recheck `git worktree list`, the removed path, and branch refs; report exactly
what was removed or retained and stop the cleanup heartbeat when finished or
blocked on a user decision. Leave unrelated caches, logs, and archives alone.

## Maintaining this shared skill

The manually edited source on Simson's machine is
`~/.agents/skills/pr-to-ready/SKILL.md`. Repository copies are generated for
remote agents; edit the source and run `make sync` in its directory. `make check`
checks generated content and discovery links without modifying repositories.
The installation inventory is `CHANGE_LOCATIONS.md` beside the source.
