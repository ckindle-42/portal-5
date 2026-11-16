# Root dispatcher (`portal5-root`)

`/usr/local/sbin/portal5-root` is the only root path the platform's automation
uses. It exists so that an agent or an `up` warning can run a root action
without stopping for a sudo password: the sudoers entry grants this one binary
`NOPASSWD`, nothing else, and the binary runs only the actions below.

| Action | Runs |
| --- | --- |
| `install-powermetrics` | `cd /Users/chris/projects/portal-5 && ./launch.sh install-powermetrics` |
| `uninstall-powermetrics` | same, `uninstall-powermetrics` |
| `launchctl-system <com.portal5.label>` | `/bin/launchctl kickstart -k system/<label>` (label must match `com.portal5.*`) |

Usage from anywhere:

```bash
sudo -n /usr/local/sbin/portal5-root install-powermetrics
sudo -n /usr/local/sbin/portal5-root launchctl-system com.portal5.powermetrics
```

## Install / reinstall

The repo copy is the source of truth; the installed binary is a copy of it and
must stay root-owned (an operator-writable root tool is not a gate).

```bash
# 1. dispatcher: root-owned, not group/other-writable
sudo install -o root -g wheel -m 0755 deploy/root/portal5-root /usr/local/sbin/portal5-root

# 2. sudoers grant: one line, the dispatcher only, 0440 (drop a .tmp in place, visudo checks it)
sudo install -o root -g wheel -m 0440 deploy/root/sudoers-portal5-root \
  /etc/sudoers.d/portal5-claude-root
sudo visudo -c

# 3. prove it: the rule is listed, and the action runs without a prompt
sudo -n -l | grep portal5-root
sudo -n /usr/local/sbin/portal5-root
```

Notes:

- `REPO` in the script is this host's main checkout (`/Users/chris/projects/portal-5`).
  A worktree must never be the target: a root install has to run the reviewed
  checkout, not a lane's working tree. Change it here and reinstall if the main
  checkout moves.
- sudo on this host keeps `HOME` (`env_keep`), so the installer's
  `$HOME/Library/LaunchAgents` still resolves to the operator's home when it runs
  under `sudo -n`; without that the legacy user-agent cleanup would look in
  `/var/root`.
- Nothing else is granted: `launchctl`, `plutil` and this dispatcher are separate
  `NOPASSWD` entries in `/etc/sudoers.d/` (`portal5-claude`, `portal5-ollama`,
  `portal5-claude-root`).
