#!/bin/sh
set -e
# Fix volume mount ownership — Docker named volumes initialize as root:root,
# overriding the chown set during image build. Runs as root before dropping privileges.
if [ -d /app/data/hf_cache ]; then
    chown -R portal:portal /app/data/hf_cache 2>/dev/null || true
fi
if [ -d /app/data/generated ]; then
    chown -R portal:portal /app/data/generated 2>/dev/null || true
fi

# Stage the proxmox SSH key/known_hosts (bind-mounted read-only, host permission
# bits that the non-root `portal` user usually can't read) into portal's own
# $HOME with correct ownership + mode before dropping privileges. No-op when
# the proxmox MCP's secrets aren't mounted (every other MCP service).
if [ -f /run/secrets/proxmox_ssh_key ]; then
    cp /run/secrets/proxmox_ssh_key /home/portal/.ssh/id_ed25519
    chown portal:portal /home/portal/.ssh/id_ed25519
    chmod 600 /home/portal/.ssh/id_ed25519
    export PROXMOX_SSH_KEY=/home/portal/.ssh/id_ed25519
fi
if [ -f /run/secrets/proxmox_known_hosts ]; then
    cp /run/secrets/proxmox_known_hosts /home/portal/.ssh/known_hosts
    chown portal:portal /home/portal/.ssh/known_hosts
    chmod 644 /home/portal/.ssh/known_hosts
    export PROXMOX_SSH_KNOWN_HOSTS=/home/portal/.ssh/known_hosts
fi

# Drop to portal user and exec the service command. Non-login `su -s ... -c`
# preserves the current environment (incl. the PROXMOX_SSH_KEY/KNOWN_HOSTS
# overrides exported above) — only HOME/SHELL/USER get reset for the target user.
exec su -s /bin/sh -c 'exec "$0" "$@"' portal -- "$@"
