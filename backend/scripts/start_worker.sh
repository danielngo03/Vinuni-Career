#!/usr/bin/env bash
set -euo pipefail

exec celery -A app.queue.celery_app:celery_app worker --loglevel="${LOG_LEVEL:-INFO}"
