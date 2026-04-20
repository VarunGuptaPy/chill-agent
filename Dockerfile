FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/
COPY assets/ assets/

# Install Python dependencies
RUN pip install --no-cache-dir -e "."

# Create output and secrets directories
RUN mkdir -p outputs secrets

# Default command: run the scheduler
CMD ["chill-agent", "run"]
