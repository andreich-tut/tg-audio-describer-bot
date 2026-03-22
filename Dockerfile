FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg tor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "tor 2>&1 | tee /tmp/tor.log &\nuntil grep -q 'Bootstrapped 100%' /tmp/tor.log 2>/dev/null; do sleep 1; done\nexec python bot.py"]
