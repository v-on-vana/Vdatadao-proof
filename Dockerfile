FROM python:3.12-slim

# Install any Python dependencies your application needs, e.g.:
RUN pip install --no-cache-dir requests

RUN mkdir /sealed && chmod 777 /sealed

WORKDIR /app

COPY . /app

# PostgreSQL only - no local data directory needed

# Create input/output directories as fallback (TEE production standard)
RUN mkdir -p /input /output && chmod 777 /input /output
# Also create /app versions for backward compatibility
RUN mkdir -p /app/input /app/output && chmod 777 /app/input /app/output

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for Docker container
ENV DOCKER_CONTAINER=true
ENV INPUT_DIR=/input
ENV OUTPUT_DIR=/output

# Ensure compatibility with pydantic settings
ENV PYTHONPATH=/app

CMD ["python", "-m", "my_proof"]
