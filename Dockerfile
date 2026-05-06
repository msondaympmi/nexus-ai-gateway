# 1. Base Image: Use official lightweight Python slim image
FROM python:3.11-slim

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8100

# 3. Set working directory in container
WORKDIR /app

# 4. Install essential system dependencies (for building passlib/bcrypt if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 6. Fix #16: Create a non-root user for security
RUN adduser --disabled-password --gecos "" nexus \
    && chown -R nexus:nexus /app

# 7. Copy the rest of the application files
COPY --chown=nexus:nexus . /app/

# 8. Switch to non-root user
USER nexus

# 9. Expose the API port
EXPOSE 8100

# 10. Default runtime command: Starts the FastAPI ASGI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]
