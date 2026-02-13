FROM python:3.11-slim

# System deps needed for Playwright Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxshmfence1 \
    libxkbcommon0 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libexpat1 \
    libxcb1 \
    libxfixes3 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# Install python deps
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN python -m playwright install chromium

EXPOSE 8501

CMD ["streamlit", "run", "update.py", "--server.port=8501", "--server.address=0.0.0.0"]
