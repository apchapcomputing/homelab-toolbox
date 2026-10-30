# homelab-toolbox

Config and starter kits I use for my homelab and AI-assisted development. Each folder is self-contained, with its own README.

| Folder | What it is | Status |
|---|---|---|
| [`apc-homelab/`](apc-homelab/) | Ansible roles and Podman Quadlet files for a RHEL-family laptop server: n8n, Postgres and Whisper in a rootless pod, Tailscale, and a sandboxed Claude Code agent that processes notes into an Obsidian vault. | First draft. Passes YAML and Ansible syntax checks only, not yet run on a real machine. |
| [`ai-dev-workflows/`](ai-dev-workflows/) | GitHub Actions, issue and PR templates, and a `CLAUDE.md` for a label-driven loop where Claude implements issues and reviews PRs. Copy the files into an app repo. | Workflows not yet run. Test with one trivial issue first. |

Hostnames, tailnet names and repo URLs in these files are placeholders (`your-tailnet.ts.net`, `youruser/your-vault.git`). Replace them with your own.

The workflows under `ai-dev-workflows/.github/` are templates and do not run in this repo. They only take effect once copied into a repo's own `.github/` folder.
