# Review rules

Used by the Claude PR review workflow. Flag real problems only.

## Always check
- **No private names.** No real tailnet name, vault URL, Tailscale IP or secret in any file. Placeholders only (`your-tailnet.ts.net`, `youruser/your-vault.git`). Treat a leak as important.
- **No secrets.** No tokens, keys, passwords or `.env` contents, including in examples and logs.
- **Ansible.** Tasks are idempotent and work in `--check` mode. Modules over `command`/`shell` where one exists. Handlers fire when a unit or config changes. Booleans are real booleans.
- **Quadlet and systemd.** Rootless, least privilege, no `--privileged`, sensible bind mounts and ACLs. Containers restart when their unit changes.
- **Agent sandbox.** Changes must not widen what the agent user can read, write or reach beyond the documented boundaries.
- **Runbooks and docs.** Pasted command blocks contain no `exit` and no interactive sub-shells. Hostname is `rhel10-dell`. Docs match the code they describe.
- **Workflows.** Anything under `ai-dev-workflows/` is a template and must not run in this repo. Workflows under `.github/` use least-privilege `permissions`.

## Skip
- Style nits that a linter would catch, unless they hide a bug.
