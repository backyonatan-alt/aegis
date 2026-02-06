#!/usr/bin/env bash
# One-time setup script for the GCP VM (aegis-worker).
# Run as root or with sudo.
set -euo pipefail

echo "=== Aegis Backend - VM Setup ==="

# 1. Install PostgreSQL
echo "Installing PostgreSQL..."
apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib

# 2. Install Caddy
echo "Installing Caddy..."
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq
apt-get install -y -qq caddy

# 3. Create aegis system user
echo "Creating aegis user..."
id -u aegis &>/dev/null || useradd --system --shell /usr/sbin/nologin aegis

# 4. Set up PostgreSQL database
echo "Setting up database..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='aegis'" | grep -q 1 || \
  sudo -u postgres createuser aegis
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='aegis'" | grep -q 1 || \
  sudo -u postgres createdb -O aegis aegis

PG_PASS=$(openssl rand -hex 16)
sudo -u postgres psql -c "ALTER USER aegis WITH PASSWORD '${PG_PASS}';"

# 5. Create env file
echo "Creating environment file..."
mkdir -p /etc/aegis
cat > /etc/aegis/env <<ENVEOF
DATABASE_URL=postgres://aegis:${PG_PASS}@localhost:5432/aegis?sslmode=disable
OPENWEATHER_API_KEY=REPLACE_ME
CLOUDFLARE_RADAR_TOKEN=REPLACE_ME
PORT=8080
ALLOWED_ORIGINS=https://usstrikeradar.com
ENVEOF
chmod 600 /etc/aegis/env
chown aegis:aegis /etc/aegis/env

# 6. Configure Caddy (simple reverse proxy, Cloudflare handles TLS)
echo "Configuring Caddy..."
cat > /etc/caddy/Caddyfile <<'CADDYEOF'
:80 {
    reverse_proxy localhost:8080
}
CADDYEOF

# 7. Enable services
echo "Enabling services..."
systemctl enable --now postgresql
systemctl enable --now caddy

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Edit /etc/aegis/env and fill in:"
echo "  - OPENWEATHER_API_KEY"
echo "  - CLOUDFLARE_RADAR_TOKEN"
echo ""
echo "Cloudflare DNS setup:"
echo "  1. Add A record: api.usstrikeradar.com -> $(curl -s ifconfig.me)"
echo "  2. Enable Proxied (orange cloud)"
echo "  3. SSL/TLS mode: Full (not Full Strict, since Caddy uses HTTP)"
echo ""
echo "GCP Firewall:"
echo "  gcloud compute firewall-rules create allow-http --allow tcp:80"
echo ""
