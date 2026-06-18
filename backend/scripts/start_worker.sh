#!/usr/bin/env bash
set -euo pipefail

exec celery -A app.modules.automation.queue.celery_app:celery_app worker \
  --loglevel="${LOG_LEVEL:-INFO}" \
  --queues="${WORKER_QUEUES:-default,ai,documents,notifications}"
