# Read-only diagnostics for the agent

The `agent` user has no general `sudo`. It does have one narrow rule so it can look at logs and status
when something breaks, without you having to paste them:

```
sudo /usr/local/bin/agent-diag <command>
```

`/etc/sudoers.d/agent-diag` allows that one script and nothing else. The script is root-owned and takes a
fixed set of commands. Run `sudo agent-diag help` to list them:

| Command | Shows |
|---|---|
| `failed` | failed units, all timers |
| `status <unit>`, `journal <unit> [N]` | system units on an allowlist (`agent-diag units`) |
| `user-status <unit>`, `user-journal <unit> [N]` | the pipeline user's Quadlet units: pod, postgres, n8n, whisper, fetcher |
| `containers` | `podman ps -a` for the pipeline user |
| `denials [N]` | today's SELinux denials |
| `selinux`, `firewall`, `ports`, `tailscale` | enforcing mode, firewalld zones, listening sockets, Tailscale and serve status |
| `show <name>` | one of a fixed list of config files (Claude policy, subuid, subgid, logind, sshd hardening, dnf-automatic, this sudoers file) |
| `ls <path>` | `ls -laZ` of a path under `/srv`, `/etc/brain`, `/etc/ssh/authorized_keys`, `/etc/sudoers.d`, `/usr/local/bin` |

## What it cannot do

- Change anything: no restart, no write, no package or Ansible command.
- Read Podman secrets, the pipeline user's home, other users' SSH keys or `/etc/shadow`. Unit names come
  from an allowlist, line counts are checked, and `ls` resolves symlinks and `..` before checking the path.
- Open a shell or an editor. There is no pager (`journalctl --no-pager`) and no wildcard in sudoers.

## What it can see

Service logs. n8n and fetcher logs contain URLs and note titles, and could contain whatever a workflow prints.
Do not make a workflow log secrets. If you ever need to remove access, delete `/etc/sudoers.d/agent-diag`.

## Not verified

Written and checked on the PC with the allow and deny logic only. `user-status`, `user-journal`,
`containers`, `denials` and `firewall` need root, and have not run on the Dell yet. First test on the
Dell: `sudo /usr/local/bin/agent-diag failed`.
