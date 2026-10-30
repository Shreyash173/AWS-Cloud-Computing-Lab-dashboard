# ================================================================
# AWS Cloud Computing Lab #2  —  Dockerfile
# Multi-stage build to keep the final image small and secure
# ================================================================

# -------------------------------------------------------------------
# Stage 1 — "builder"
# Install Python dependencies into a separate layer.
# We only copy the compiled packages into the final stage.
# -------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /install

# Copy only the requirements file first.
# Docker caches this layer, so re-builds are fast when code changes.
COPY app/requirements.txt .

# Install packages into /install/packages (not the system Python).
RUN pip install --no-cache-dir --prefix=/install/packages -r requirements.txt


# -------------------------------------------------------------------
# Stage 2 — "runtime"
# Lean final image that contains only what is needed to run the app.
# -------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Good practice: run as a non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /install/packages /usr/local

# Copy application source code
COPY app/ .

# Hand ownership to the non-root user
RUN chown -R appuser:appgroup /app

USER appuser

# Expose the port Gunicorn will listen on
EXPOSE 5000

# Health check — Docker will mark the container unhealthy if this fails
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

# Start with Gunicorn (production WSGI server, NOT the Flask dev server)
# --workers 2  : two worker processes to handle concurrent requests
# --bind       : listen on all interfaces at port 5000
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
