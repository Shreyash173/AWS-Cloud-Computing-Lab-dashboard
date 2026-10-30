"""
AWS Cloud Computing Lab #2
Flask Frontend Application
--------------------------
A simple two-tier web app that tracks page visits using Redis.
"""

import os
import time
import logging
from flask import Flask, jsonify, render_template
import redis

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Basic logging so we can see what is happening in the container logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis connection
# ---------------------------------------------------------------------------
# The host is read from an environment variable so Docker Compose / Kubernetes
# can inject the right value without changing any code.
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

def get_redis():
    """Create and return a Redis client.  Returns None if Redis is unavailable."""
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,       # return strings instead of bytes
            socket_connect_timeout=2,    # fail fast if Redis is down
        )
        client.ping()                    # actually test the connection
        return client
    except Exception as exc:
        logger.warning("Redis not reachable at %s:%s — %s", REDIS_HOST, REDIS_PORT, exc)
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Main dashboard page."""
    redis_client = get_redis()

    if redis_client:
        # Atomically increment the visit counter stored in Redis
        visits = redis_client.incr("visit_count")
        redis_status = "healthy"
    else:
        visits = "N/A (Redis unreachable)"
        redis_status = "unavailable"

    logger.info("Dashboard visited — visits=%s", visits)

    return render_template(
        "index.html",
        visits=visits,
        redis_status=redis_status,
        redis_host=REDIS_HOST,
    )


@app.route("/health")
def health():
    """
    Health-check endpoint used by Docker / Kubernetes probes.
    Returns HTTP 200 when the app is running.
    Redis connectivity is reported but does NOT affect the status code —
    the Flask app itself is healthy even if Redis is temporarily down.
    """
    redis_client = get_redis()
    redis_ok = redis_client is not None

    payload = {
        "status": "healthy",
        "app": "AWS Cloud Computing Lab",
        "redis": "connected" if redis_ok else "unavailable",
    }
    return jsonify(payload), 200


@app.route("/api/visits")
def api_visits():
    """JSON endpoint that returns the current visit count from Redis."""
    redis_client = get_redis()

    if redis_client:
        count = redis_client.get("visit_count") or 0
        return jsonify({"visits": int(count), "redis": "connected"}), 200
    else:
        return jsonify({"visits": None, "redis": "unavailable", "error": "Redis not reachable"}), 503


# ---------------------------------------------------------------------------
# Entry point (local development only)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
