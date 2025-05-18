FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock /app/
RUN pip install --no-cache-dir -e .

# Copy application files
COPY . /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default configuration
ENV POLL_INTERVAL=15
ENV OPT_IN_ONLY=false
ENV NO_DEFAULT_LABELS=false
ENV LABEL_MAPPINGS="{}"
ENV LOG_LEVEL=INFO
ENV DEBUG=false

# Expose port for the web interface
EXPOSE 5000

# Start the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--reuse-port", "--reload", "main:app"]
