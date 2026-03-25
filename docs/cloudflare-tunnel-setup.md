# Cloudflare Tunnel Setup for Mini App HTTPS

This guide walks you through setting up **Cloudflare Tunnel** to get free HTTPS for your Telegram Mini App.

## Prerequisites

- [x] Cloudflare account (free tier)
- [x] Domain added to Cloudflare DNS
- [x] Bot running with webapp backend (port 8080)
- [x] Docker installed (recommended) or ability to install `cloudflared`

---

## Overview

```
User → Telegram Mini App → https://miniapp.yourdomain.com
                              ↓
                    Cloudflare Edge (SSL termination)
                              ↓
                    Cloudflare Tunnel (encrypted)
                              ↓
                    Your server:8080 (Caddy/FastAPI)
```

**Benefits:**
- ✅ Free SSL/HTTPS (no certificate management)
- ✅ No port forwarding needed (works behind NAT/firewall)
- ✅ DDoS protection via Cloudflare
- ✅ Automatic failover and retries
- ✅ No need to expose server ports publicly

---

## Step 1: Create Tunnel & Get Token

### Option A: Docker (Recommended)

```bash
# 1. Login to Cloudflare (opens browser)
docker run --rm -it -v ~/.cloudflared:/etc/cloudflared \
  cloudflare/cloudflared:latest tunnel login

# 2. Create a named tunnel
docker run --rm -it -v ~/.cloudflared:/etc/cloudflared \
  cloudflare/cloudflared:latest tunnel create miniapp

# Output: Created tunnel miniapp with ID <uuid>
# Credentials saved to ~/.cloudflared/<uuid>.json
```

### Option B: Native Binary

```bash
# Install cloudflared (Ubuntu/Debian)
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared

# Login & create tunnel
cloudflared tunnel login
cloudflared tunnel create --name miniapp
```

---

## Step 2: Add Tunnel to Docker Compose

Add the `cloudflared` service to `docker-compose.yml`:

```yaml
services:
  bot:
    # ... your existing bot config ...

  caddy:
    # ... your existing Caddy config ...

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel run
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      - caddy
    networks:
      - bot-network
```

---

## Step 3: Configure Tunnel Token

```bash
# On your local machine, encode credentials
cat ~/.cloudflared/*.json | base64 -w 0

# Copy output and add to server .env:
# CLOUDFLARE_TUNNEL_TOKEN=<paste-base64-here>

# Copy credentials to server
scp ~/.cloudflared/*.json user@yourserver:~/.cloudflared/
```

---

## Step 4: Add DNS Record

```bash
# Route DNS to tunnel (automatic)
docker run --rm -it -v ~/.cloudflared:/etc/cloudflared \
  cloudflare/cloudflared:latest tunnel route dns \
  miniapp miniapp.yourdomain.com
```

Or manually in Cloudflare dashboard:
- Type: `CNAME`
- Name: `miniapp`
- Target: `<tunnel-id>.cfargotunnel.com`
- Proxy: **Proxied** (orange cloud ON)

---

## Step 5: Start & Test

```bash
# Start tunnel
docker compose up -d cloudflared

# Check logs
docker logs -f cloudflared

# Test URL (from anywhere)
curl https://miniapp.yourdomain.com
```

Expected: Returns your React app's index.html

---

## Step 6: Set Mini App URL in Bot

Send to your bot in Telegram:

```
/setmenu https://miniapp.yourdomain.com
```

**Done!** The "Settings" menu button should now appear in Telegram.

---

## Configuration Reference

### Tunnel Config (if using native binary)

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: miniapp
credentials-file: /root/.cloudflared/<uuid>.json

ingress:
  - hostname: miniapp.yourdomain.com
    service: http://localhost:8080
  - service: http_status:404
```

### Environment Variables

Add to `.env`:

```env
CLOUDFLARE_TUNNEL_TOKEN=<base64-encoded-credentials-json>
DOMAIN=miniapp.yourdomain.com
WEBAPP_URL=https://miniapp.yourdomain.com
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Tunnel won't connect | Check `TUNNEL_TOKEN` is valid base64; verify outbound port 443 allowed |
| 404 Not Found | Check Caddy `root` path; verify webapp files exist in `/srv/webapp` |
| 502 Bad Gateway | Ensure bot container is running; check Caddy can reach `bot:8080` |
| SSL errors | Wait 1-2 minutes for Cloudflare to provision certificate |
| Menu button not showing | Restart Telegram app; verify URL starts with `https://` |

---

## Maintenance

### Update Tunnel

```bash
# Docker
docker pull cloudflare/cloudflared:latest
docker compose restart cloudflared

# Native
sudo apt-get install --only-upgrade cloudflared
```

### View Logs

```bash
# Docker
docker logs cloudflared

# Native (systemd)
journalctl -u cloudflared -f
```

### Delete Tunnel

```bash
cloudflared tunnel delete miniapp
```

---

## Cost

**Free Tier:**
- ✅ 50 GB/month bandwidth
- ✅ Unlimited HTTPS requests
- ✅ 3 tunnels per account
- ✅ Basic DDoS protection

---

## References

- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [cloudflared CLI Reference](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)
- [Telegram Mini App Guidelines](https://core.telegram.org/bots/webapps)
