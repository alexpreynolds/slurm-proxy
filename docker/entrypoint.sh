#!/bin/sh
set -e

# Start WireGuard VPN connection
/app/start_wireguard.sh
sleep 5  # Wait for the VPN connection to establish
echo "Testing Slurm API connection..."
# Test Slurm API connection
if ! curl -s https://slurmapi.altius.org > /dev/null; then
    echo "Slurm API is not reachable. Exiting."
    traceroute -n slurmapi.altius.org
    exit 1
else
    echo "Slurm API is reachable, proceeding..."
fi

# Execute the provided command (should be supervisord)
exec "$@"