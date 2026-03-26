
Complete instructions for deploying the bot on a fresh VPS with proper security practices and Docker best practices.

---

## Table of Contents

- [Table of Contents](#table-of-contents)
- [1. Server Preparation](#1-server-preparation)
- [2. Create Dedicated User](#2-create-dedicated-user)
- [3. Clone \& Configure](#3-clone--configure)
- [4. Deploy with Docker](#4-deploy-with-docker)
- [5. Maintenance \& Monitoring](#5-maintenance--monitoring)
  - [Common Commands](#common-commands)
  - [Safe Backup Data](#safe-backup-data)
- [6. Troubleshooting](#6-troubleshooting)
  - [Container won't start](#container-wont-start)
  - [Bot doesn't respond](#bot-doesnt-respond)
  - [Database locked](#database-locked)
- [Security Checklist](#security-checklist)
- [Optional: Setup HTTPS for Mini App](#optional-setup-https-for-mini-app)

---

## 1. Server Preparation

**Why first?** We need to install Docker *before* we create our dedicated user so the `docker` group exists.

```bash
# SSH into your VPS as root or your main sudo user
ssh user@your-vps-ip

# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL [https://get.docker.com](https://get.docker.com) -o get-docker.sh
sudo sh get-docker.sh

# Install Git
sudo apt install -y git

# Install fail2ban (brute-force protection)
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Configure UFW firewall (allow only SSH to start)
sudo apt install -y ufw
sudo ufw allow ssh
sudo ufw enable
```

---

## 2. Create Dedicated User

**Why?** Security isolation — the bot runs with minimal privileges, separate from your main root user.

```bash
# Create dedicated user (no password, no shell access by default)
sudo useradd -m -s /bin/bash botuser

# Add to docker group (allows running docker without sudo)
sudo usermod -aG docker botuser

# Switch to botuser for the rest of the setup
sudo su - botuser
```

> **Security Note:** For production servers, it is highly recommended to disable SSH password authentication entirely and rely solely on SSH keys. You can do this by setting `PasswordAuthentication no` in `/etc/ssh/sshd_config` (using your sudo user).

---

## 3. Clone & Configure

```bash
# Ensure you are logged in as botuser
cd ~

# Clone repository
git clone <your-repo-url> tg-audio-describer
cd tg-audio-describer

# Create data directory manually BEFORE Docker does (prevents root ownership issues)
mkdir -p data

# Create .env from template
cp .env.example .env

# Generate a secure encryption key using a temporary, isolated Docker container
docker run --rm python:3.9-slim python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Edit `.env` with your values:**
```bash
nano .env
```

**Minimum required in `.env`:**
```env
# Telegram Bot Token (from @BotFather)
BOT_TOKEN=123456:ABC-DefGhIjKlMnOpQrStUvWxYz

# LLM API Key (OpenRouter or other provider)
LLM_API_KEY=sk-or-your-key-here
LLM_BASE_URL=[https://openrouter.ai/api/v1](https://openrouter.ai/api/v1)
LLM_MODEL=qwen/qwen3-235b-a22b:free

# Database Encryption (paste the key generated in the previous step)
ENCRYPTION_KEY=<paste-generated-key-here>

# Restrict access to your Telegram user ID only
ALLOWED_USERS=<your-telegram-id>

# Use cloud STT (no GPU required)
WHISPER_BACKEND=groq
GROQ_API_KEY=<your-groq-key>

# Default language
DEFAULT_LANGUAGE=en
```

**Save:** `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 4. Deploy with Docker

Because Docker handles process management natively, you do **not** need `systemd`. Just ensure your `docker-compose.yml` includes `restart: unless-stopped` under your bot service, and Docker will automatically start it on boot.

```bash
# Make scripts executable
chmod +x docker/start.sh docker/update.sh

# Start the bot
./docker/start.sh

# View logs to ensure it started properly
docker logs -f tg-audio

# Check container is running
docker ps
```

**Expected output:**
```text
CONTAINER ID   IMAGE                 STATUS
abc123def456   tg-audio:latest       Up 30 seconds
```

**Test bot:**
* Open Telegram
* Send `/start` to your bot
* You should see the welcome/help message

---

## 5. Maintenance & Monitoring

### Common Commands

```bash
# View live logs
docker logs -f tg-audio

# View last 50 lines
docker logs --tail 50 tg-audio

# Restart bot
docker restart tg-audio

# Stop bot
docker stop tg-audio

# Update bot (rebuild + prune old images)
cd ~/tg-audio-describer
./docker/update.sh
```

### Safe Backup Data

Because SQLite uses Write-Ahead Logging (`-wal`), backing up a live database can cause corruption. **Always stop the container first.**

```bash
# 1. Stop the bot safely
docker stop tg-audio

# 2. Backup database and encryption key
tar -czvf bot-data-backup-$(date +%Y%m%d).tar.gz ~/tg-audio-describer/data/ ~/tg-audio-describer/.env

# 3. Restart the bot
docker start tg-audio

# 4. (Optional) Download backup to local machine from a new terminal
scp botuser@vps-ip:~/bot-data-backup-*.tar.gz ~/backups/
```

---

## 6. Troubleshooting

### Container won't start
```bash
# Check logs for Python/Application errors
docker logs tg-audio

# Check .env file exists and has correct values
cat ~/tg-audio-describer/.env | grep -E "BOT_TOKEN|LLM_API_KEY|ENCRYPTION_KEY"
```

### Bot doesn't respond
```bash
# Check bot token is valid
docker exec tg-audio python -c "from shared.config import BOT_TOKEN; print('OK' if BOT_TOKEN else 'MISSING')"

# Test LLM connectivity
docker exec tg-audio python -c "from infrastructure.external_api.llm_client import ping_llm; print(ping_llm())"
```

### Database locked
```bash
# Stop container safely
docker stop tg-audio

# Remove lock files
rm ~/tg-audio-describer/data/bot.db-shm ~/tg-audio-describer/data/bot.db-wal

# Restart
docker start tg-audio
```

---

## Security Checklist

* [x] Docker installed before user creation
* [x] Dedicated user created (`botuser`)
* [x] No sudo privileges for `botuser`
* [x] UFW firewall enabled (SSH only default)
* [x] fail2ban installed and active
* [x] `ALLOWED_USERS` set to your Telegram ID
* [x] Encryption key generated in isolated environment
* [x] **Recommended:** SSH password authentication disabled

---

## Optional: Setup HTTPS for Mini App

If using the web-based settings UI (Mini App), you need to open web ports and set up a reverse proxy.

1. **Open Web Ports in Firewall:**
   ```bash
   # Run this as your main sudo user, NOT botuser
   sudo ufw allow http
   sudo ufw allow https
   ```

2. **Install Caddy (reverse proxy with auto-SSL):**
   ```bash
   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
   curl -1sLf '[https://dl.cloudsmith.io/public/caddy/stable/gpg.key](https://dl.cloudsmith.io/public/caddy/stable/gpg.key)' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLf '[https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt](https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt)' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt update
   sudo apt install caddy
   ```

3. **Configure Caddy:**
   ```bash
   sudo nano /etc/caddy/Caddyfile
   ```
   ```text
   yourdomain.com {
       reverse_proxy localhost:8080
   }
   ```

4. **Point domain to VPS IP** and restart Caddy:
   ```bash
   sudo systemctl restart caddy
   ```

5. **Set DOMAIN in `.env` (as botuser):**
   ```env
   DOMAIN=yourdomain.com
   ```