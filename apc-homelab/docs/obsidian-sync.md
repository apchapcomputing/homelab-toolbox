# Obsidian Headless sync

How the server keeps the vaults in step with Obsidian Sync, using the official headless client (`ob`).

## How it fits together

```
Obsidian Sync (cloud)
   │  one service per vault
   ▼
obsidian-sync-make.service ──►  /srv/vaults/make   (apc:obsidian, 2775)  ◄── agent writes notes here
obsidian-sync-live.service ──►  /srv/vaults/live   (apc:obsidian, 2775)      agent can read and write
```

- `ob` runs as the admin user (`apc`). Its Obsidian login is stored in that account's home.
- `/srv/vaults` is one git repo with the vault folders inside it. `live` is listed in its `.gitignore` (the obsidian role writes `live/` there from `vault_git_ignore`, because the agent can read `live` and would otherwise commit it).
- The `obsidian` group holds `apc` and `agent`. The `make` vault is group-writable, so the agent can write summaries into it. New directories are setgid, so new files stay in the group. The sync service sets `UMask=0002` for `make`, so files `ob` creates are group-writable too.
- `live` is shared the same way (`2775`, `UMask=0002`). Pipeline runs still cannot reach it: the policy only lets them edit `make/Input/Clippings` and the tag guide. Unlike `make`, `live` is not in the git snapshots, so Obsidian Sync's version history is its only undo layer. Set `agent_access: false` on it in `group_vars/all.yml` to close it again (`2700`, `UMask=0077`).
- Config sync is off (`--configs ""`). The server never pulls or changes your `.obsidian` settings. They come from git.

Run every `ob` command as `apc`. Never as root and never as `agent`: the login belongs to the account that runs the services.

## Setting up a new machine

1. Create the users, group, folders and service files without starting anything:
   ```bash
   ansible-playbook site.yml --tags users,obsidian --ask-become-pass
   ```
2. As `apc`, log in once and list your remote vaults to get their exact names:
   ```bash
   ob login
   ob sync-list-remote
   ```
3. Link each folder to its remote vault. Use the remote name that `sync-list-remote` printed. Turn config sync off **before** the first sync:
   ```bash
   ob sync-setup  --vault "<remote name of make>" --path /srv/vaults/make --device-name rhel10-dell
   ob sync-config --path /srv/vaults/make --configs ""
   ob sync        --path /srv/vaults/make

   ob sync-setup  --vault "<remote name of live>" --path /srv/vaults/live --device-name rhel10-dell
   ob sync-config --path /srv/vaults/live --configs ""
   ob sync        --path /srv/vaults/live
   ```
   `ob sync` without `--continuous` pulls once and exits. If you set an end-to-end encryption password, `sync-setup` asks for it.
4. Start the services. Set `start_ob_sync: true` in `group_vars/all.yml`, then:
   ```bash
   ansible-playbook site.yml --tags obsidian --ask-become-pass
   ```

If you would rather not use Ansible for step 4, the units are plain systemd files: `sudo systemctl enable --now obsidian-sync-make obsidian-sync-live`.

## Checking that it works

```bash
systemctl is-active obsidian-sync-make obsidian-sync-live        # both: active
ob sync-status --path /srv/vaults/make
sudo journalctl -u obsidian-sync-make -n 20 --no-pager

# the agent can write in both vaults:
sudo -u agent sh -c 'touch /srv/vaults/make/Input/Clippings/.perm-test && rm /srv/vaults/make/Input/Clippings/.perm-test && echo OK'
sudo -u agent sh -c 'touch /srv/vaults/live/.perm-test && rm /srv/vaults/live/.perm-test && echo OK'
```

After you edit a note on another device, check that the file synced down with group write:
```bash
ls -l /srv/vaults/make/<the note>      # expect -rw-rw-r-- apc obsidian
```
If it shows `-rw-r--r--`, `ob` is not honouring the umask. Tell whoever maintains this, because the agent would then be unable to edit synced notes.

## Adopting a setup you made by hand

If the vaults were set up manually before this role existed, running `--tags obsidian` replaces the two service files with equivalent ones (it adds the `UMask` line) and restarts them if `start_ob_sync` is true. These one-time fixes cover what Ansible does not touch recursively:

```bash
# let the group write to the vault and the git directory, keeping new directories setgid
cd /srv/vaults
sudo chgrp -R obsidian make .git
sudo chmod -R g+rwX make .git
sudo find make .git -type d -exec chmod g+s {} +

# share live the same way
sudo chgrp -R obsidian live
sudo chmod -R g+rwX live
sudo find live -type d -exec chmod g+s {} +

# keep live out of the repo the agent snapshots and apc pushes (the role does this too)
grep -qx 'live/' /srv/vaults/.gitignore 2>/dev/null || echo 'live/' | sudo tee -a /srv/vaults/.gitignore
# if live was ever committed, drop it from the index (the files stay on disk):
sudo -u apc git -C /srv/vaults rm -r --cached --ignore-unmatch live

# .git/config must belong to the sync user, not root (a root-run `git config` leaves it root-owned)
sudo chown apc:obsidian .git/config

# as apc, without sudo:
git -C /srv/vaults config core.sharedRepository group

# restart so the services pick up the group membership and UMask
sudo systemctl restart obsidian-sync-make obsidian-sync-live
```

Group membership only applies to new logins. Log out and in as `apc`, or use `sudo -u agent` to test as the agent.

## Things to avoid

- **Do not run `git` as root in `/srv/vaults`.** Objects created by root cannot be written by the agent's daily snapshot. If it happens: `sudo chown -R apc:obsidian /srv/vaults/.git`.
- **Do not edit vault files on the server as `agent` outside the pipeline.** Sync is bidirectional, so a deletion on the server is a deletion everywhere. Obsidian Sync keeps version history, and the daily git snapshots are the second undo layer.
- **`ob` has a `--mode pull-only` option** for `sync-config`. It does not fit `make`, because the pipeline writes notes there that must go back up to your devices.

## Not verified

- The unit files match the two that were running when this was written, plus `UMask`. Hardening options such as `NoNewPrivileges` and `ProtectSystem` have not been tried against `ob` and are left out on purpose.
- Whether `ob` creates files with group write under `UMask=0002` has not been tested against a real sync. Use the check above.
