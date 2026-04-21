#!/bin/sh
set -e
# Fix volume mount ownership — Docker named volumes initialize as root:root,
# overriding the chown set during image build. Runs as root before dropping privileges.
if [ -d /app/data/hf_cache ]; then
    chown -R portal:portal /app/data/hf_cache
fi
if [ -d /app/data/generated ]; then
    chown -R portal:portal /app/data/generated
fi
# Drop to portal user and exec the service command
exec su -s /bin/sh -c 'exec "$0" "$@"' portal -- "$@"
