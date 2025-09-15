FROM python:3.12-slim

# Install any Python dependencies your application needs, e.g.:
RUN pip install --no-cache-dir requests

RUN mkdir /sealed && chmod 777 /sealed

WORKDIR /app

COPY . /app

# Create data directory for database with proper permissions
# This ensures data directory exists even if not mounted from host
RUN mkdir -p /app/data && chmod 777 /app/data

# Create input/output directories as fallback
RUN mkdir -p /app/input /app/output && chmod 777 /app/input /app/output

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for Docker container
ENV DOCKER_CONTAINER=true
ENV DB_PATH=/app/data/registry.db
ENV INPUT_DIR=/app/input
ENV OUTPUT_DIR=/app/output

# Ensure compatibility with pydantic settings
ENV PYTHONPATH=/app

# Create volume mount point for persistent database storage
VOLUME ["/app/data"]

CMD ["python", "-m", "my_proof"]
