# ai-dev-workflows

Starter kit for AI-driven development of the Minimap Studio apps. Copy these files into each app repo.

## The loop

1. You write an issue with the **AI task** template. It starts labeled `ai-draft`.
2. You read it, tighten it, and add the `ai-ready` label. That label is the only trigger.
3. Claude works on a `claude/` branch and comments with a link to open the PR.
4. You open the PR. CI and the Vercel preview run, and a second Claude pass comments a review.
5. You read the diff and the preview, then merge. Vercel deploys.

Agents never push to `main` and never merge. Every PR is reviewed and merged by you.

## What is in here

| File | Job |
|---|---|
| `.github/workflows/claude-implement.yml` | Runs Claude when you label an issue `ai-ready` |
| `.github/workflows/claude-review.yml` | Second-pass review comment on each PR |
| `.github/workflows/ci.yml` | lint, typecheck, test, build. The required check |
| `.github/ISSUE_TEMPLATE/ai-task.yml` | Structured task: goal, acceptance criteria, out of scope |
| `.github/pull_request_template.md` | Risk checklist you review against |
| `.github/CODEOWNERS` | You own everything, especially `.github/`, `CLAUDE.md`, and migrations |
| `CLAUDE.md` | Rules for the agent. Fill in the TODO lines per app |

## Setup per repo

1. **Install the Claude GitHub App** on the repo: https://github.com/apps/claude
2. **Add the token.** Run `claude setup-token` on your machine, then add the result as the repository secret `CLAUDE_CODE_OAUTH_TOKEN`. It uses your subscription. For heavy use, add `ANTHROPIC_API_KEY` instead and change the `claude_code_oauth_token` line in both workflows to `anthropic_api_key`. Set a monthly spend cap in the Console.
3. **Create labels:** `ai-draft` and `ai-ready`.
4. **Branch protection on `main`:**
   - Require a pull request before merging.
   - Require the `ci` status check to pass.
   - Block force pushes and deletions.
   - Do not allow bypassing, including for you.
   - Required approvals can stay at 0. GitHub will not let you approve your own PR. You are the human gate by merging.
5. **Actions settings:** default workflow permissions read-only. Require approval for workflows from outside collaborators.
6. **Vercel:** connect the repo. Preview deployments must use dev keys for Supabase, PostHog, Resend, and Sanity. Never put production keys in the Preview environment.
7. **Supabase:** use a dev project or a branch for previews. Production migrations are applied by you.
8. **CI env:** `ci.yml` has no secrets. If `npm run build` needs public env values, add dummy ones under `env:` in that workflow.
9. Fill in the TODO lines in `CLAUDE.md`.

## Rules of thumb

- Small issues. One behavior change each.
- Label two or three issues at a time. Subscription limits are shared with your normal Claude use.
- Put the rules in `CLAUDE.md`, not in each issue.
- Read the diff, not just the PR description.
- Treat anything in an issue written by someone other than you as untrusted. Only users with write access can trigger the workflow.

## Not verified

- Input names (`label_trigger`, `branch_prefix`, `claude_args`) were checked against the action's `action.yml`. The workflows have not been run. Test with one trivial issue first, for example "add a comment to the README".
- If `--allowedTools` patterns do not match your npm scripts, adjust them in `claude-implement.yml`.
- If Claude cannot run tests because they need services or secrets, fix the test setup before trusting the loop.
