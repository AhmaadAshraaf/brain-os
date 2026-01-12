# Ingest Service Dockerfile
FROM python:3.11-slim

# Install system dependencies required for PDF processing
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set PYTHONPATH to allow imports from ingest package
ENV PYTHONPATH=/app

# Default command (can be overridden)
CMD ["python", "-m", "src.main"]
