FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg tor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "tor &\nsleep 5\nexec python bot.py"]
