#!/bin/bash

# Vdatadao Proof Production Deployment Script

set -e

echo "🚀 Starting Vdatadao Proof Production Deployment..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if required environment variables are set
if [ -z "$DLP_ID" ]; then
    echo "❌ DLP_ID environment variable is required"
    exit 1
fi

if [ -z "$INPUT_DIR" ]; then
    echo "❌ INPUT_DIR environment variable is required"
    exit 1
fi

if [ -z "$OUTPUT_DIR" ]; then
    echo "❌ OUTPUT_DIR environment variable is required"
    exit 1
fi

echo "📋 Configuration:"
echo "  DLP_ID: $DLP_ID"
echo "  INPUT_DIR: $INPUT_DIR"
echo "  OUTPUT_DIR: $OUTPUT_DIR"
echo "  DATABASE_PATH: ${DATABASE_PATH:-/app/data/registry.db}"

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p "$INPUT_DIR"
mkdir -p "$OUTPUT_DIR"
mkdir -p "$(dirname "${DATABASE_PATH:-/app/data/registry.db}")"

# Set proper permissions
echo "🔐 Setting permissions..."
chmod 755 "$INPUT_DIR"
chmod 755 "$OUTPUT_DIR"
chmod 755 "$(dirname "${DATABASE_PATH:-/app/data/registry.db}")"

# Build Docker image
echo "🔨 Building Docker image..."
docker build -t vdatadao-proof-v2:latest .

# Run container
echo "🏃 Running container..."
docker run --rm \
    -e DLP_ID="$DLP_ID" \
    -e INPUT_DIR="$INPUT_DIR" \
    -e OUTPUT_DIR="$OUTPUT_DIR" \
    -e DATABASE_PATH="${DATABASE_PATH:-/app/data/registry.db}" \
    -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    -e GOOGLE_TOKEN="${GOOGLE_TOKEN:-}" \
    -e FILE_ID="${FILE_ID:-0}" \
    -e OWNER_ADDRESS="${OWNER_ADDRESS:-}" \
    -v "$INPUT_DIR:/input:ro" \
    -v "$OUTPUT_DIR:/output" \
    -v "$(dirname "${DATABASE_PATH:-/app/data/registry.db}"):/app/data" \
    vdatadao-proof-v2:latest

echo "✅ Deployment completed successfully!"
echo "📊 Check results in: $OUTPUT_DIR/results.json"
