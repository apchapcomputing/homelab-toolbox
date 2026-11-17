# Async SaaS development plan

How to take a SaaS app from "here's what I want" to production with Claude doing most of the work in the background, and you as the only person who merges to `main`.

This plan builds on the existing kit in this folder (`claude-implement.yml`, `claude-review.yml`, `ci.yml`, `CLAUDE.md`). Section 7 lists what changes.

**Update:** refining and implementing now run on the homelab, not in GitHub Actions. The `devloop` service polls the Project every 30 minutes and uses the Status field instead of labels (`apc-homelab/docs/devloop.md`). GitHub Actions keeps CI and the Claude PR review. References: UI and landing pages come from ShipFast, and CI plus Claude PR review copy newsletter2paper (`tests.yml` with one required `Tests passed` check, `claude-pr-review.yml`, `REVIEW.md`).

## 1. Decision: GitHub Projects, not Todoist

Use **GitHub Issues + GitHub Projects** as the single source of truth.

| Need | GitHub Projects | Todoist |
|---|---|---|
| Task lives next to the code, branches and PRs | Yes. Issues link to PRs and commits | No. Links only |
| A task change can start an agent | Yes. Labels and issue events trigger Actions | No native trigger. Needs polling or n8n glue |
| Claude in CI can read and write tasks | Yes, with the built-in `GITHUB_TOKEN` | Needs a Todoist token stored in every repo |
| Tag you when something is unknown | `@you` mention → GitHub mobile notification | Comment, but you'd watch two apps |
| Epics, phases, tracks | Sub-issues, issue types, custom fields | Projects, sections, labels |
| Non-code tasks (marketing, ops) | Fine as issues with a `human` label | Better UX for personal todos |

Todoist only wins on personal, non-code to-dos. If you want those on your phone, an n8n flow can later mirror issues labeled `needs-human` or `human` into a Todoist project. GitHub stays the source of truth.

## 2. How work is organized

**One GitHub Project per app.** Every item is an issue in the app's repo.

**Hierarchy, using GitHub sub-issues:**
- **Epic**: a major feature, for example "Billing". It owns one long-lived branch, `feature/<epic-slug>`.
- **Story**: one behavior change, small enough for one PR into the epic's branch.
- **Task**: non-code work (DNS, Stripe account, launch post). Labeled `human` when only you can do it.

**Project fields:**

| Field | Values |
|---|---|
| Phase | MVP, v1, v2, Later |
| Track | Dev, Ops, Marketing, Design |
| Status | Inbox → Refining → Needs human → Ready → In progress → In review → Done |
| Size | S, M, L. Claude splits anything larger than M during refinement |
| Epic branch | `feature/<epic-slug>`, the PR target for the story |
| Blocked by | Issue links. Claude doesn't start a story while a blocker is open |

**Labels** drive automation, since Actions can't trigger on Project field changes:
`ai-refine`, `ai-ready`, `ai-working`, `needs-human`, `human`.

## 3. The lifecycle

```
 You describe the app
        │
 [1 Launch]   interactive session: PRD + epics + stories → Project (Status: Inbox)
        │
 [2 Refine]   autonomous, one Action run per story, label ai-refine
        │       ├─ everything known → fills the spec, label ai-ready (Status: Ready)
        │       └─ something unknown → comments with questions, @you, label needs-human
        │             you answer in the issue, re-add ai-refine
        │
 [3 Implement] fresh Action run per story (a new Claude context every time)
        │       branch claude/<issue>-<slug> off feature/<epic> → PR into feature/<epic>
        │
 [4 Verify]   CI tests + Vercel preview + Claude review on the PR
        │       ├─ green and no blocking findings → auto-merge into feature/<epic>, close the story
        │       └─ red → Claude gets 2 fix attempts, then needs-human
        │
 [5 Release]  every story in the epic done → PR feature/<epic> → main
                you test the epic's Vercel preview, read the diff, merge. Production deploys.
```

### Stage 1: Launch (you + Claude, interactive)

1. You describe everything you want.
2. Claude writes `docs/prd.md` in the repo: problem, users, MVP scope, v1 scope, out of scope, stack, pricing, launch plan. You edit it until it's right. It is the reference every later run reads.
3. Claude proposes epics and stories across Dev, Ops and Marketing, grouped by phase. You approve the breakdown.
4. Claude creates the issues, sub-issue links, field values and `feature/*` branches, and labels the MVP stories `ai-refine`.

This is the only stage where Claude waits for you.

### Stage 2: Refine (autonomous)

A `claude-refine.yml` workflow runs on the `ai-refine` label (and optionally nightly, with a cap). It fills in the issue's spec section:

- **Context**: why this story exists, with a link to the PRD section
- **Acceptance criteria**: testable bullet points
- **Implementation notes**: files and modules to touch, data model changes, API shape, UI states
- **Test plan**: which tests to add, and what to check on the preview
- **Dependencies**: `Blocked by` links, plus any env vars or third-party setup
- **Out of scope**
- **Size**: an L gets split into new sub-issues instead

**Rule for unknowns:** if a product decision, credential, copy, price, design choice or external account is needed and isn't in the PRD or the repo, Claude doesn't guess. It posts one comment with numbered questions, each with a suggested default, mentions `@you`, sets `needs-human` and moves on to the next story. You answer in the issue and re-add `ai-refine`.

When the spec is complete, Claude sets `ai-ready` itself, without asking you.

### Stage 3: Implement (fresh context per story)

`claude-implement.yml` triggers on `ai-ready`. Each Action run is a new Claude session, so context never carries over between stories: the issue spec plus `CLAUDE.md` plus the PRD has to be enough. If it isn't, that's a refinement bug: Claude sends the story back with `needs-human` rather than guessing.

- Before starting, Claude checks that no `Blocked by` issue is still open. If one is, it relabels the story and stops.
- It branches `claude/<issue>-<slug>` from the current head of `feature/<epic>`.
- It runs lint, typecheck, tests and build, then opens a PR into `feature/<epic>` with `Refs #<issue>`.
- Concurrency: at most 2–3 stories in progress at once (subscription limits, merge conflicts). Use an Actions `concurrency` group per epic so stories in one epic run in sequence.

### Stage 4: Verify and merge into the epic branch

- `ci.yml` runs on every PR, including PRs into `feature/*`.
- Vercel builds a preview for the story branch.
- `claude-review.yml` posts a review and marks findings as blocking or not.
- If CI is green and there are no blocking findings, the PR auto-merges into `feature/<epic>`.
- If CI fails, Claude gets two fix attempts on the same branch. After that, `needs-human`.

**Gotcha:** `Closes #12` only closes issues when a PR merges into the default branch. Merges into `feature/*` won't close the story, so the auto-merge workflow must close the issue and set Status to Done itself.

### Stage 5: Release to main (you only)

- When every story under an epic is Done, a workflow opens (or updates) the PR `feature/<epic>` → `main`, with the list of stories and the epic's Vercel preview URL.
- `feature/<epic>` gets its own stable Vercel preview, so you can test the whole feature in one place.
- You review and merge. Vercel deploys production from `main`.
- Long epics: a scheduled job merges `main` into each open `feature/*` branch weekly to keep conflicts small. If there is a conflict, it opens a PR and tags you instead of resolving it.

## 4. Making "only I merge to main" real

Set this up with repository **rulesets**:

- **`main`**: PR required. `ci` must pass. 1 approval from a code owner (you). Since the epic PR is opened by the bot, you can approve it, and the bot can't approve its own PR. No bypass for apps or Actions. No force pushes or deletions.
- **`feature/*`**: PR required. `ci` must pass. 0 approvals, so auto-merge works. No force pushes.
- **`claude/*`**: unprotected. These are agent working branches.
- Repo settings: allow auto-merge, delete head branches after merge.

Check one thing on the first trial: if the Claude GitHub App ends up with a bypass on `main`, remove it.

## 5. Where you get pulled in

You're notified only when:
1. A story needs a decision (`needs-human`, `@you` in a comment).
2. A story failed twice in CI.
3. An epic is ready to ship (PR into `main`).
4. A `human` task is assigned to you (accounts, payments, DNS, legal).

Turn on GitHub mobile notifications for mentions and review requests. Saved Project views:
- **My queue**: `label:needs-human OR label:human` plus open PRs into `main`
- **Board**: by Status, grouped by Epic
- **Roadmap**: by Phase

## 6. Ops and Marketing tracks

These run through the same board:
- **Ops** stories that are code (CI, monitoring, Supabase migrations as files, Vercel config) flow through refine and implement normally. Applying production migrations, secrets and paid accounts are `human` tasks.
- **Marketing** stories Claude can do produce files in the repo: landing page copy, `docs/marketing/launch-posts.md`, email drafts in Resend templates, SEO metadata. They go through PR review like code. Posting, ad spend and outreach are `human` tasks. Claude drafts them and never posts.

## 7. Changes to this kit

| # | Change | File |
|---|---|---|
| 1 | Add Stage 1 instructions: write the PRD, create the issues, set fields and branches | new `docs/launch-playbook.md` |
| 2 | Refinement workflow and prompt: fill the spec, ask `@you` on unknowns, set `ai-ready` | new `.github/workflows/claude-refine.yml` |
| 3 | Issue template: add the spec sections and an Epic branch field | `.github/ISSUE_TEMPLATE/ai-task.yml` |
| 4 | Implementation: read the epic branch from the issue, branch from it, open the PR itself, check blockers, concurrency per epic | `.github/workflows/claude-implement.yml` |
| 5 | Review: emit a machine-readable "blocking: yes/no" verdict | `.github/workflows/claude-review.yml` |
| 6 | Auto-merge into `feature/*`, close the story, set Status Done, 2 fix attempts | new `.github/workflows/story-merge.yml` |
| 7 | Open or update the epic → `main` PR when all sub-issues are done | new `.github/workflows/epic-release.yml` |
| 8 | Weekly sync of `main` into `feature/*` | new `.github/workflows/epic-sync.yml` |
| 9 | Agent rules: PRD is the source of truth, how to ask, the branch rules | `CLAUDE.md` |
| 10 | Rulesets, labels, Project fields and views | README setup section |

Rollout: build 1–4 first and run it on one throwaway app with a single tiny epic. Add auto-merge (6) only after you've watched about 10 story PRs and trust the review verdicts.

## 8. Defaults I picked (change any of them)

- Story PRs merge into the epic branch automatically when CI and review pass. You review at the epic level. If you want to approve each story too, drop auto-merge and keep everything else.
- Claude sets `ai-ready` after refinement without you reviewing the spec.
- At most 3 stories in progress across the repo at once.
- Runs use your subscription token (`CLAUDE_CODE_OAUTH_TOKEN`). If you hit limits, switch to an API key with a monthly cap.
- Unknowns get a suggested default in the question, so answering can be as short as "default is fine".

## 9. Not verified

None of the new workflows exist yet, and the existing ones haven't been run. Sub-issue and Project field updates from Actions need a token with Projects access: the default `GITHUB_TOKEN` can't write to user-owned Projects v2, so this likely needs a fine-grained PAT or a GitHub App token stored as a secret. Check this on the first trial.
