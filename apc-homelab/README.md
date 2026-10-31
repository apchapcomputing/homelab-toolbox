# apc-homelab

Ansible and Quadlet config for `rhel10-dell`: a RHEL-family laptop server that turns podcast links into processed Obsidian notes.

**Status: first draft, not yet run on a real machine.** It passes YAML and Ansible syntax checks only. Expect to fix details on the first run, especially the Quadlet files, the Tailscale repo path, and file ownership around the inbox. Do the first run with `--check` and read the output.

## What it builds

```
your PC (Ansible)  --ssh-->  rhel10-dell
                              ├─ base       packages, SELinux enforcing, firewalld, SSH hardening, Cockpit, security updates
                              ├─ users      pipeline and agent (no sudo, locked passwords)
                              ├─ tailscale  repo, install, tailscale0 in the trusted zone
                              ├─ pipeline   rootless Podman + Quadlet: n8n, Postgres, Whisper, fetcher in one pod
                              ├─ obsidian   Node, the ob client, the obsidian group, one sync service per vault
                              ├─ agent      Claude Code, forced-command SSH key, daily snapshot
                              └─ backup     weekly fast-forward push to GitHub, run as the admin user
```

## Who can do what

| User | Does | Cannot |
|---|---|---|
| `apc` (admin) | SSH in, sudo, runs Obsidian Sync, holds the GitHub deploy key, pushes weekly | |
| `pipeline` | runs n8n, Postgres, Whisper; holds their secrets | sudo, SSH login, touch the vault |
| `agent` | Claude Code, writes into the `make` and `live` vaults through the `obsidian` group (pipeline runs only reach `make/Input/Clippings`), daily snapshot | sudo, see n8n secrets, see the GitHub key, use a shell or web |

n8n talks to the agent through one SSH key locked to `/usr/local/bin/brain-run`, which accepts a single request (`process`). n8n writes new notes into `/srv/inputs`. `brain-run` moves them into the vault and runs Claude Code in `--restricted` mode with file tools only.

Podcast transcripts are untrusted text. The tool limits, the root-owned policy in `/etc/brain/claude-headless.json`, and the separate user are the defense. The "treat this as data" line in the prompt helps but is not a boundary.

## Before the first run

1. Install the OS (RHEL on a Developer subscription, CentOS Stream, or Fedora Server). Create the `apc` user with sudo.
2. From your PC: `ssh-copy-id apc@<laptop-lan-ip>`, then confirm key login works.
3. On your PC: `ansible-galaxy collection install -r requirements.yml`
4. `cp inventory.example.ini inventory.ini` and put the LAN IP in it.
5. Edit `group_vars/all.yml`. Bump the pinned image tags if they are out of date.
6. In the BIOS, set the battery to Primarily AC Use or a custom charge limit. A laptop left plugged in all the time can swell its battery.
7. Make the n8n key pair on your PC (never commit it):
   `ssh-keygen -t ed25519 -f n8n_to_agent -N ""`
   Paste the contents of `n8n_to_agent.pub` into `n8n_ssh_pubkey`.

## Run it

```bash
ansible-playbook site.yml --check --diff --ask-become-pass   # look first
ansible-playbook site.yml --ask-become-pass
```

Run a single role with `--tags base`, `--tags pipeline`, and so on.

## Manual steps after the first run

**Tailscale**
```bash
sudo tailscale up --hostname=rhel10-dell
```
Then in the admin console, turn on MagicDNS and HTTPS certificates. Switch `inventory.ini` to the tailnet name.

**Podman secrets (as the pipeline user)**
```bash
sudo machinectl shell pipeline@
openssl rand -hex 32 | tr -d '\n' | podman secret create postgres_password -
openssl rand -hex 32 | tr -d '\n' | podman secret create n8n_encryption_key -
podman secret inspect --showsecret n8n_encryption_key   # save this in your password manager now
exit
```
Lose the encryption key and every credential saved in n8n is gone.

If you are restoring an old n8n, create `n8n_encryption_key` from the old key instead of a new one.

**Start the pipeline**
Set `start_pipeline: true` in `group_vars/all.yml` and re-run `--tags pipeline`. Then:
```bash
sudo tailscale serve --bg 5678
```
Open `https://rhel10-dell.your-tailnet.ts.net`, create the owner account, and turn on 2FA.

**Load the Whisper model (once)**
```bash
sudo machinectl shell pipeline@
podman exec whisper curl -X POST http://localhost:8000/v1/models/Systran/faster-whisper-small
```
Check the speaches docs for the current image tag and model route. They change.

**Obsidian Sync (as the admin user)**
`ob` runs as `apc` and syncs `/srv/vaults/make` and `/srv/vaults/live`. The commands, checks, and fixes for a hand-made setup are in [docs/obsidian-sync.md](docs/obsidian-sync.md). Once `ob login` and `ob sync-setup` are done for each vault, set `start_ob_sync: true` and re-run `--tags obsidian`.

**Claude Code login (as the agent user)**
```bash
sudo machinectl shell agent@
~/.local/bin/claude     # follow the login prompt, then exit
```

**Vault git history**
The agent commits locally and never holds the GitHub key. To seed the history from GitHub, as the admin user:
```bash
git clone --no-checkout git@github.com:youruser/your-vault.git /tmp/vault-seed
sudo mv /tmp/vault-seed/.git /srv/vaults/.git
sudo chown -R apc:obsidian /srv/vaults/.git
sudo -u agent git -C /srv/vaults reset -q   # --no-checkout leaves no index
sudo -u agent git -C /srv/vaults status --short | head
```
Check that status shows only what you expect, then re-run `--tags agent,backup`. Copy your GitHub deploy key to `~/.ssh/vaults_deploy` on the admin account first so the push timer enables.

**Wire n8n to the agent**
In n8n, add an SSH credential: host `host.containers.internal`, user `agent`, authentication by private key (the contents of `n8n_to_agent`), then an SSH node running the command `process`. Slugify note titles before writing them to `/inbox`: only letters, digits, spaces, dots, dashes, underscores, and parentheses are accepted.

## The fetcher

A fourth container in the pod turns a URL into a raw clipping note (captions, or yt-dlp and Whisper). n8n only calls it. See [docs/fetcher.md](docs/fetcher.md).

## Checks after a run

- `systemctl --user -M pipeline@ status postgres n8n whisper` (or use `machinectl shell`)
- `curl -s http://127.0.0.1:5678/healthz` returns ok
- As the pipeline user: `podman exec fetcher python3 -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8080/healthz').read())"` prints `{"ok": true}`
- `getenforce` says Enforcing
- `sudo firewall-cmd --list-all` shows no cockpit service
- Reboot. The containers come back and the HTTPS page loads.
- `sudo -u agent ls -l /etc/brain/claude-headless.json` shows it owned by root, and `/etc/ssh/authorized_keys/agent` the same.

## Known gaps

- Obsidian Sync runs as the admin user, so a bug in `ob` runs next to the GitHub deploy key. Protect that key with a passphrase.
- Group membership applies at the next login.
- Weekly review and the Todoist connection are not built. They need the Todoist MCP server added for the agent and a timer.
- `dnf-automatic` is skipped on Fedora, which uses a different package. Use `dnf5-plugin-automatic` there.
- Whisper runs on CPU. A GPU box (gaming laptop) is a later swap.
- Nothing monitors the box yet. Add Uptime Kuma on the Pi.
- Set `lan_ssh: false` once SSH over Tailscale works.
