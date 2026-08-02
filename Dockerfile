# ==========================================
# Stage 1: Build .NET 8 CLI Renderer
# ==========================================
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS dotnet-builder
WORKDIR /src
COPY VideoDubberStudio.sln ./
COPY VideoDubber.Core/ VideoDubber.Core/
COPY VideoDubber.Core.Tests/ VideoDubber.Core.Tests/
COPY VideoDubber.UI/ VideoDubber.UI/
COPY VideoDubberRenderCLI/ VideoDubberRenderCLI/

RUN dotnet publish VideoDubberRenderCLI/VideoDubberRenderCLI.csproj -c Release -o /app/cli

# ==========================================
# Stage 2: Python 3.10 Runtime Environment
# ==========================================
FROM python:3.10-slim

# Install system dependencies & fonts for video processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fontconfig \
    libfontconfig1 \
    libfreetype6 \
    libharfbuzz0b \
    fonts-noto-core \
    fonts-noto-color-emoji \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy built .NET CLI binaries
COPY --from=dotnet-builder /app/cli ./bin/cli/

# Copy python dependencies and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/outputs /app/uploads

# Set environment variables for Cloud Run
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Start Gunicorn server binding to Cloud Run $PORT
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 app:app
