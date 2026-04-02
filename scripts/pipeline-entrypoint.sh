#!/bin/sh
# Fix tmpfs mount ownership — Docker mounts tmpfs as root, but we run as portal.
if [ -d /tmp/portal_metrics ]; then
    chown portal:portal /tmp/portal_metrics
fi
exec python -m portal_pipeline "$@"
