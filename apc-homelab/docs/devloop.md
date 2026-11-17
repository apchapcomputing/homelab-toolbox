# devloop

Every 30 minutes, `devloop` checks one GitHub Project and runs Claude Code on stories that need work. You plan with Claude in a normal chat, it creates the issues, and devloop takes it from there. You only step in when a story asks you a question and when a feature is ready to merge into `main`.

## What it does each run

```
Status:  Needs refinement ──refine──▶ Ready ──implement──▶ In progress ──▶ In review ──PR merged──▶ Done
                 │                      │                                      │
                 └──── question ───▶ Needs human ◀──── question / 2 failures ──┘
                       (@mentions you; you answer, then set Status back)
```

1. **Sync.** For each story In review, find the PR from `claude/issue-<n>`. Merged → Done, and the issue is closed. GitHub only closes issues for merges into the default branch, so devloop does it. Closed without merging → Needs human.
2. **Implement** (1 per run). Ready stories whose `## Dependencies` are all closed. devloop makes a fresh worktree from the story's epic branch and runs Claude, which edits code and runs tests. devloop then commits, pushes `claude/issue-<n>` and opens a PR into the epic branch. The PR opening starts your CI and Claude review workflows, the same as newsletter2paper's.
3. **Refine** (up to 3 per run). Claude reads the repo read-only and writes the spec: context, acceptance criteria, implementation notes, test plan, dependencies, out of scope, size. devloop puts the spec in the issue body and keeps your original text in a collapsed section. Fully specified → Ready. Something unknown → a comment that @mentions you with numbered questions, each with a suggested default → Needs human.

Each Claude run is a new session, so the issue has to carry everything. If a run fails, the story goes back to its previous status and devloop stops for that half hour, which keeps usage limits from draining. After 2 failures, the story goes to Needs human with the error.

Stories with no **Epic branch** value get PRs into the default branch. You merge those yourself. If the epic branch doesn't exist yet, devloop creates it from the default branch.

## Boundaries

- Runs as its own `builder` user. It has no sudo and no access to the vaults.
- Claude never gets the GitHub token. The token is a root-only file that systemd passes to the service. devloop uses it for git and API calls and starts Claude with a clean environment. Claude writes `result.json`, and devloop does the GitHub writes.
- Refine runs have no shell: read, search, and write `result.json` only. Implement runs can edit the worktree and run a fixed list of build and test commands (`allowed_bash` in `devloop.py`). devloop refuses any change to `.github/`, `CLAUDE.md`, `CODEOWNERS` or `.env*`.
- Only issues opened by `devloop_trusted_authors`, and only comments from them, reach Claude. That matters for public repos, where anyone can comment.
- **Not a boundary:** an implement run executes the app's npm scripts as `builder`. A Claude run could read anything `builder` can read, and in principle that includes the running service's copy of the token. Keep the token scoped to the app repos, and rely on the rules on `main` (below) as the real gate.

## Setup

### 1. A bot account (recommended)

Create a second GitHub account, for example `youruser-bot`. Add it as a collaborator with write access on each app repo and on the Project.

Why: GitHub doesn't notify you about mentions in your own comments, and it doesn't let you approve your own PRs. With your own token, you'd never get pinged, and a rule requiring your approval on `main` would block every epic PR.

### 2. Token

On the bot account, create a **classic** personal access token with the `repo` and `project` scopes. Fine-grained tokens can't write to Projects owned by a personal account. For a Project owned by an organization, a fine-grained token with the repos plus Projects read and write works.

On the server:
```bash
read -rsp 'GitHub token: ' T && printf '%s' "$T" | sudo install -m 600 -o root -g root /dev/stdin /etc/devloop/github-token; unset T; echo
```

### 3. Project fields

In the GitHub Project:
- **Status** (single select) needs these options: `Needs refinement`, `Needs human`, `Ready`, `In progress`, `In review`, `Done`. Rename them in `devloop_status` if you prefer other names.
- **Epic branch** (text), for example `feature/billing`.

Phase, Track and Size fields are for you and the planning chat. devloop ignores them.

### 4. Vars and run

Edit the `devloop_*` lines in `group_vars/all.yml`: project owner and number, your login, trusted authors, git identity. Then:
```bash
ansible-playbook site.yml --tags users,devloop --ask-become-pass
```

### 5. Log Claude in as the devloop user

```bash
sudo -iu builder ~/.local/bin/claude
```
Follow the login prompt, then type `/exit`.

### 6. Dry run, then turn it on

```bash
sudo systemd-run --wait --pipe -p User=builder -p StateDirectory=devloop \
  -p LoadCredential=github-token:/etc/devloop/github-token \
  /usr/local/bin/devloop --dry-run
```
It prints the counts per status and what it would run. Then set `start_devloop: true` and re-run `--tags devloop`.

## Day to day

- Start a run now: `sudo systemctl start devloop.service`
- Log: `journalctl -u devloop -n 100`
- Each Claude run's prompt, output and result: `/var/lib/devloop/runs/` (kept 30 days)
- Pause: `sudo systemctl stop devloop.timer`
- Answering a question: reply in the issue, then set Status to `Needs refinement`. The next refine reads your reply.
- Throughput: at most 1 implement and 3 refines per 30 minutes (`devloop_max_*`). Raise slowly; the usage limits are shared with your own Claude use.

## Not verified

The test in this session ran devloop against a fake GitHub, a local git remote and a stand-in `claude` binary. It has not run against real GitHub or real Claude Code. Check these on the first real run:
- The `claude` flags: `--tools`, `--allowedTools`, `--disallowedTools`, `--permission-mode dontAsk`, `--strict-mcp-config`. They match the flags `brain-run` uses.
- That a classic token on the bot account can update the Project's Status field.
- That `npm ci` and the test commands in `allowed_bash` are enough for your apps. Add patterns to `DEFAULTS["allowed_bash"]` in `devloop.py` if Claude reports a blocked command.
