FROM pulumi/pulumi-python-3.12:latest

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY Pulumi.yaml .
COPY main.py .
COPY app/ app/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Allow extra time on first start — Pulumi downloads provider plugins on the
# initial stack_up call, which can take 30-60 seconds.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
