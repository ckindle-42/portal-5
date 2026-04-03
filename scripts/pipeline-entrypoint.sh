#!/bin/sh
# Fix mount ownership — Docker mounts tmpfs/volumes as root, but we run as portal.
if [ -d /tmp/portal_metrics ]; then
    chown portal:portal /tmp/portal_metrics
fi
if [ -d /app/data ]; then
    chown portal:portal /app/data
fi
exec python -m portal_pipeline "$@"
