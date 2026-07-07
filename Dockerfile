FROM python:3.11-slim-bookworm

WORKDIR /app

# 1. 替换 Debian 的 apt 官方源为腾讯云镜像源 (加速系统依赖下载)
# 注：python:3.11-slim 基于 Debian 12，使用的是 deb.debian.org
RUN sed -i 's/deb.debian.org/mirrors.tencent.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.tencent.com/g' /etc/apt/sources.list 2>/dev/null || true

# Install system dependencies (libpq for asyncpg, Playwright browser deps)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 2. pip 依然使用腾讯云源 (你已经改好的，保持不变)
RUN pip install -i https://mirrors.tencent.com/pypi/simple/ --no-cache-dir -r requirements.txt

# 3. 设置 Playwright 下载内核的国内镜像源 (加速 Chromium 下载)
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/

# Install Playwright's Chromium browser (used by crawler)
RUN playwright install --with-deps chromium

COPY . .

COPY entrypoint.sh /entrypoint.sh
# 兼容 Windows CRLF 换行符
RUN sed -i 's/\r//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]