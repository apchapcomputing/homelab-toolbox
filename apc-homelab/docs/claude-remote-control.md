# Claude Remote Control as a service

Remote Control lets claude.ai/code and the phone app drive a Claude Code session that runs on the Dell. The local process has to stay up: if it exits, the session is gone. Run in a bare terminal or tmux, it dies with the terminal, a crash, or a reboot, and nothing notices.

The `agent` role installs `claude-rc.service` to fix that. systemd starts it at boot, restarts it 10 seconds after any exit, and keeps a debug log. Per the Remote Control docs, a machine that cannot reach the network for about 10 minutes makes the session time out and the process exit. `Restart=always` turns that into a fresh session instead of a dead one.

It is a system unit that runs as `agent`, like `brain-run.service`, so it needs no linger setting. It starts `/usr/local/bin/claude-rc`, a root-owned wrapper, so SELinux does not have to allow systemd to run a binary out of the agent's home.

## Before you turn it on

Both of these are one-time and are done by hand as `agent`, because they are interactive:

1. `claude` is logged in (`/login`).
2. The workspace trust prompt has been accepted in `claude_rc_dir` (default `/home/agent/homelab-toolbox`). Run `claude` once in that folder and accept it.

## Turn it on

In `group_vars/all.yml` (or `local.yml`) set `start_claude_rc: true`, then from the PC:

```bash
ansible-playbook site.yml -e @local.yml --tags agent --ask-become-pass
```

The unit is installed even while `start_claude_rc` is false. The flag only controls whether it is enabled and started.

If you currently have Claude running under tmux for Remote Control, stop that one first or you will have two sessions with the same name.

## Check it

On the Dell, as `agent`:

```bash
systemctl status claude-rc.service
sudo /usr/local/bin/agent-diag journal claude-rc.service 50
tail -n 50 /var/log/claude-rc/remote-control.log
```

The session shows up in claude.ai/code under the name `claude_rc_name` (the host name by default).

## When it disconnects

`remote-control.log` is the record Claude does not keep otherwise. Look at the lines just before the time the session dropped. The log rotates weekly and keeps four copies.

If the service shows `activating (auto-restart)` over and over, run the log command above and the journal command and read the last error. A trust prompt that was never accepted, or an expired login, both make it exit at once.

## Limits

- Sessions started from the phone run with the default permission mode, so they ask before they run tools. The wrapper sets no `--permission-mode` on purpose.
- This runs `claude remote-control` as a server that starts sessions on demand. It does not bring back an interactive conversation you had open in tmux. To continue a past conversation, resume it by ID.
- `--spawn same-dir` puts every session in `claude_rc_dir`. Change `--spawn` in `templates/claude-rc.sh.j2` if you want worktrees.
- Not yet run on the Dell. First run: check `systemctl status` and the debug log before you rely on it.
