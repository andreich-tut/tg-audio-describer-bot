# Mini App HTTPS Setup with Caddy

Caddy automatically provisions Let's Encrypt certificates when given a real domain name. The project already has Caddy configured — you only need a DNS record and one env var.

## Prerequisites

- [ ] VPS with public IP, ports 80 and 443 open
- [ ] Domain with DNS access
- [ ] Bot running with Docker Compose

---

## Steps

### 1. DNS A Record — *DNS provider panel*

Point your domain to the VPS:

```
Type: A
Name: @ (root domain) or a subdomain like "miniapp"
Value: <your VPS public IP>
TTL: Auto
```

Verify propagation:

```bash
dig +short yourdomain.com
# Should return your VPS IP
```

---

### 2. Open Firewall Ports — *VPS*

```bash
# If using ufw
sudo ufw allow 80,443/tcp

# If using firewalld
sudo firewall-cmd --permanent --add-service={http,https}
sudo firewall-cmd --reload
```

Port 80 is required for ACME challenge (certificate issuance). Port 443 serves HTTPS traffic.

---

### 3. Set `DOMAIN` in `.env` — *VPS*

```bash
# Add to your .env file
echo 'DOMAIN=yourdomain.com' >> /path/to/bot/.env
```

The `Caddyfile` already reads `{$DOMAIN:localhost}`. When set to a real hostname, Caddy auto-provisions a certificate on first request.

---

### 4. Restart the Stack — *VPS*

```bash
cd /path/to/bot/docker
docker compose up -d
```

Caddy will:
1. Listen on ports 80 and 443
2. Request a Let's Encrypt certificate for your domain
3. Serve the Mini App SPA and proxy `/api/*` to the bot

---

### 5. Verify — *VPS or local machine*

```bash
curl -I https://yourdomain.com
# Should return HTTP/2 200 with valid certificate
```

---

### 6. Set Menu Button — *Telegram*

Send to your bot:

```
/setmenu https://yourdomain.com
```

The menu button should appear in Telegram.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Certificate not issued | Check ports 80/443 are open; check DNS resolves to VPS IP |
| `ERR_CONNECTION_REFUSED` | Caddy not running — check `docker logs caddy` |
| 502 Bad Gateway | Bot container not running — check `docker logs bot` |
| 404 Not Found | Frontend not built — check `docker logs frontend` and that `/srv/webapp/index.html` exists |
| Menu button missing | Restart Telegram app; verify URL starts with `https://` |
| Cert renewal fails | Ensure port 80 stays open (ACME HTTP-01 challenge) |

---

## How It Works

```
User -> Telegram Mini App -> https://yourdomain.com
                                |
                          Caddy (ports 80/443)
                          - Auto SSL via Let's Encrypt
                          - Serves SPA from /srv/webapp
                          - Proxies /api/* to bot:8080
                                |
                          Bot container (internal port 8080)
```

Key files:
- `Caddyfile` — routing rules (SPA + API proxy)
- `docker/docker-compose.yml` — Caddy service with ports 80/443
- `.env` — `DOMAIN` variable

---

## For Servers Behind NAT/Firewall

If your server has no public IP or cannot open ports 80/443, consider [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) as an alternative.
