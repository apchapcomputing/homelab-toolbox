# Runbook: clipping automation, end to end

From a Todoist link to a summarized note in the `make` vault. Written for the state of
rhel10-dell on 2026-11-01: Tailscale is up, Obsidian Sync runs as `apc`, `/srv/vaults` is a git
repo, and Claude Code is logged in as `agent`. Nothing has gone through Ansible yet.

`PC` means manjaro-pc. `Dell` means rhel10-dell. Each block says where to run it.

## 1. Get the repo and Ansible on the PC

```bash
# PC
git clone git@github.com:apchapcomputing/homelab-toolbox.git   # or: git pull
cd homelab-toolbox/apc-homelab
sudo pacman -S ansible                                          # skip if installed
ansible-galaxy collection install -r requirements.yml
```

## 2. Let the PC log in to the Dell

```bash
# PC
ssh-copy-id apc@rhel10-dell.your-tailnet.ts.net
ssh apc@rhel10-dell.your-tailnet.ts.net 'hostname; sudo -n true 2>&1 | head -1'   # no password prompt
cp inventory.example.ini inventory.ini
ansible -i inventory.ini homelab -m ping                        # expect: pong
```

If the tailnet name does not resolve, put the Dell's Tailscale IP (`tailscale ip -4` on the Dell) in `inventory.ini`.

## 3. The key n8n uses to reach the agent

```bash
# PC, inside apc-homelab/ (both files are git-ignored)
ssh-keygen -t ed25519 -f n8n_to_agent -N ""
printf 'n8n_ssh_pubkey: "%s"\n' "$(cat n8n_to_agent.pub)" > local.yml
# your real names live only here, never in the repo (it is public):
cat >> local.yml <<'YML'
ts_fqdn: rhel10-dell.<your-tailnet>.ts.net
github_backup_url: git@github.com:<you>/<your-vault-repo>.git
YML
```
Edit those two lines to your real values. In the commands below, replace `your-tailnet` with your tailnet name as well.

## 4. One-time fixes on the Dell (it was set up by hand)

```bash
# Dell, as apc
cd /srv/vaults
sudo chgrp -R obsidian make live .git
sudo chmod -R g+rwX make live .git
sudo find make live .git -type d -exec chmod g+s {} +
sudo chown apc:obsidian .git/config
git -C /srv/vaults config core.sharedRepository group      # no sudo
sudo grep pipeline /etc/subuid                              # should be ONE line; delete the extra one by hand
```

Then check the vault repo before anything else touches it:

```bash
git -C /srv/vaults status --short | head      # the old Make/ -> make rename shows up here
```

Commit or discard those changes yourself. Do not run `git` as root in `/srv/vaults`.

## 5. Run Ansible (pipeline still off)

```bash
# PC, inside apc-homelab/
ansible-playbook site.yml -e @local.yml --check --diff --ask-become-pass   # read it
ansible-playbook site.yml -e @local.yml --ask-become-pass
```

Keep a second SSH session open to the Dell during the real run. If a task fails, paste me the
task name and the error.

Check:

```bash
# Dell
getenforce                                                   # Enforcing
sudo ls -l /etc/brain/claude-headless.json /etc/ssh/authorized_keys/agent   # both root-owned
systemctl list-timers | grep -E 'brain-run|vault-snapshot'
ls -ld /srv/inputs
```

## 6. Podman secrets

```bash
# Dell
sudo machinectl shell pipeline@ /bin/bash -c "openssl rand -hex 32 | tr -d '\n' | podman secret create postgres_password -"
sudo machinectl shell pipeline@ /bin/bash -c "openssl rand -hex 32 | tr -d '\n' | podman secret create n8n_encryption_key -"
sudo machinectl shell pipeline@ /bin/bash -c "podman secret inspect --showsecret n8n_encryption_key"     # save this in your password manager NOW
```

## 7. Start the pipeline

Set `start_pipeline: true` in `group_vars/all.yml` on the PC, then:

```bash
# PC
ansible-playbook site.yml -e @local.yml --tags pipeline,agent --ask-become-pass
```

The first start builds the fetcher image on the Dell. That takes a few minutes. Check:

```bash
# Dell
sudo machinectl shell pipeline@ /bin/bash -c "systemctl --user status postgres n8n whisper fetcher --no-pager | grep -E 'Active|●'"
curl -s http://127.0.0.1:5678/healthz
sudo machinectl shell pipeline@ /bin/bash -c "podman exec fetcher python3 -c \"import urllib.request as u; print(u.urlopen('http://127.0.0.1:8080/healthz').read())\""
```

## 8. Load the Whisper model (once)

```bash
# Dell
sudo machinectl shell pipeline@ /bin/bash -c "podman exec fetcher python3 -c \"import urllib.request as u; print(u.urlopen(u.Request('http://127.0.0.1:8000/v1/models/Systran/faster-whisper-small', method='POST')).read())\""
```

If that route is rejected, use `speaches-cli model download Systran/faster-whisper-small`
(see the speaches docs for your image version).

## 9. Reach n8n over Tailscale

In the Tailscale admin console, turn on MagicDNS and HTTPS certificates. Then:

```bash
# Dell
sudo tailscale serve --bg 5678
```

Open `https://rhel10-dell.your-tailnet.ts.net`, create the owner account, turn on 2FA.

## 10. Credentials and workflow in n8n

1. **Todoist token.** Todoist: Settings, Integrations, Developer, copy the API token.
   n8n: Credentials, Add, Header Auth. Name `Todoist API token`, header `Authorization`,
   value `Bearer <token>`.
2. **SSH.** Credentials, Add, SSH, private key. Name `brain-run on rhel10-dell`, host
   `host.containers.internal`, port 22, user `agent`. Paste the output of
   `cat n8n_to_agent` (PC). Then delete the private key file from the PC if you do not want it.
3. **Import.** Workflows, Import from file: `apc-homelab/workflows/todoist-to-inbox.json`.
   Open each node with a warning and pick the credentials above.
4. **Save the key backup.** Confirm the n8n encryption key is in your password manager.

## 11. First real test: the YouTube task

1. Leave the other Todoist tasks alone (or move them out of the project for now).
2. In n8n, open the workflow and press Execute Workflow.
3. Watch the nodes. Expect: Get open tasks, Pick links, Fetch transcript (seconds, captions),
   Make file, Write to inbox, Process (SSH), then the Todoist comment and completion.
4. On the Dell:

```bash
ls -l /srv/inputs /srv/vaults/make/Input/Clippings | tail
sudo journalctl -u brain-run --no-pager -n 20
```

5. In Obsidian on another device, the clipping should appear after sync with a summary and tags.

If a step fails, open the failed node in n8n and paste me its error. A failed fetch leaves the
Todoist task open with a `failed` label. A failed summary is retried by the hourly timer.

## 12. Then switch it on and test the hard ones

1. Activate the workflow (toggle, top right).
2. Add the Pivot episode (about 1 hour). It needs Whisper, so this is the first speed test.
3. Add the Acquired episode (3 h 18 min) last. If the fetch times out, raise `MAX_DURATION_S`
   and the HTTP node timeout.

## 13. Only after the above works

- Test SSH from n8n to the agent again after setting `lan_ssh: false`. Traffic from the pod to
  the host may arrive on an address the firewall treats as LAN, so closing LAN SSH can break
  `brain-run`. Close it, run a note through, and reopen it if it breaks.
- Protect `main`, replace the account-level GitHub key on the agent with a per-repo deploy key.
- Set `start_ob_sync: true` if the sync units are not under Ansible's control yet.
