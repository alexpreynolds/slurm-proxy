#!/bin/sh
set -e

# Determine which configuration to use based on environment variable
if [ "$ENVIRONMENT" = "production" ] || [ "$ENVIRONMENT" = "prod" ]; then
  echo "Using production WireGuard configuration"
  CONFIG_TEMPLATE="/etc/wireguard/prod.conf.template"
  CONFIG_FILE="/etc/wireguard/wg0.conf"
else
  echo "Using development WireGuard configuration"
  CONFIG_TEMPLATE="/etc/wireguard/dev.conf.template"
  CONFIG_FILE="/etc/wireguard/wg0.conf"
fi

# Process the template file and substitute environment variables
envsubst < "$CONFIG_TEMPLATE" > "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"

# Start WireGuard
wg-quick up wg0

# Set up routing for 10.0.0.0/8 network through WireGuard
ip route replace 10.0.0.0/8 dev wg0

# Make sure DNS settings are applied
echo "Configuring DNS settings..."
cat > /etc/resolv.conf << EOF
nameserver 10.129.16.3
nameserver 10.129.16.4
search altius.org
EOF

echo "WireGuard VPN is now connected"