#!/bin/sh
set -e

# Start WireGuard VPN connection
/app/start_wireguard.sh

# Execute the provided command (should be supervisord)
exec "$@"