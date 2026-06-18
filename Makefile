.PHONY: help env install-local check-local-ports dev-local dev-all dev-up dev-down dev-logs dev-foreground stop-local backend-env backend-install backend-init-db backend-infra-up backend-compose-up backend-compose-down backend-compose-logs backend-api backend-test frontend-install frontend-dev frontend-build frontend-typecheck check

help:
	@echo "C2 Career Platform"
	@echo "  make env                  Create backend/frontend local env files if missing"
	@echo "  make install-local        Install backend venv and frontend dependencies"
	@echo "  make backend-init-db      Create schema and seed demo data"
	@echo "  make dev-all              Start local backend + frontend in background"
	@echo "  make dev-foreground       Run backend + frontend in foreground"
	@echo "  make dev-logs             Tail local backend/frontend logs"
	@echo "  make dev-down             Stop local dev processes"
	@echo "  make stop-local           Stop local dev processes on ports 8000 and 3000"
	@echo "  make backend-infra-up     Start Postgres + Redis only"
	@echo "  make backend-api          Run FastAPI locally on http://127.0.0.1:8000"
	@echo "  make backend-compose-up   Run backend API + worker + infra with Docker Compose"
	@echo "  make frontend-dev         Run the Next.js web app"
	@echo "  make check                Run backend tests and frontend typecheck/build"

env: backend-env
	@test -f frontend/.env.local || touch frontend/.env.local

backend-env:
	@test -f backend/.env || cp backend/.env.example backend/.env

install-local: env backend-install backend-init-db frontend-install

check-local-ports:
	@busy=0; \
	for port in 8000 3000; do \
		pids=$$(lsof -ti tcp:$$port 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "Port $$port is already in use by PID(s): $$pids"; \
			busy=1; \
		fi; \
	done; \
	if [ "$$busy" -ne 0 ]; then \
		echo "Run 'make dev-down' to stop stale local dev processes, or close the app using those ports."; \
		exit 1; \
	fi

dev-local: dev-all

dev-all: dev-up

dev-up: env check-local-ports backend-init-db
	@test -x backend/.venv/bin/uvicorn || (echo "Missing backend/.venv. Run: make install-local" && exit 1)
	@test -d frontend/node_modules || (echo "Missing frontend/node_modules. Run: make install-local" && exit 1)
	@mkdir -p .dev/logs .dev/pids
	@echo "Starting backend and frontend in background..."
	@nohup sh -c 'cd backend && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload' > .dev/logs/backend.log 2>&1 & echo $$! > .dev/pids/backend.pid
	@nohup sh -c 'cd frontend && exec pnpm dev' > .dev/logs/frontend.log 2>&1 & echo $$! > .dev/pids/frontend.pid
	@echo "Backend:   http://127.0.0.1:8000/docs  (Scalar: http://127.0.0.1:8000/scalar)"
	@echo "Frontend:  http://localhost:3000"
	@echo "Logs:      make dev-logs"
	@echo "Stop:      make dev-down"

dev-foreground: env check-local-ports backend-init-db
	@test -x backend/.venv/bin/uvicorn || (echo "Missing backend/.venv. Run: make install-local" && exit 1)
	@test -d frontend/node_modules || (echo "Missing frontend/node_modules. Run: make install-local" && exit 1)
	@echo "Starting backend at http://127.0.0.1:8000 and frontend at http://localhost:3000"
	@backend_pid=; frontend_pid=; \
	cleanup() { \
		test -n "$$backend_pid" && kill "$$backend_pid" 2>/dev/null || true; \
		test -n "$$frontend_pid" && kill "$$frontend_pid" 2>/dev/null || true; \
		sleep 1; \
		for port in 8000 3000; do \
			pids=$$(lsof -ti tcp:$$port 2>/dev/null || true); \
			test -n "$$pids" && kill $$pids 2>/dev/null || true; \
		done; \
	}; \
	trap cleanup INT TERM EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) & backend_pid=$$!; \
	(cd frontend && pnpm dev) & frontend_pid=$$!; \
	wait "$$backend_pid" "$$frontend_pid" || true

dev-logs:
	@test -d .dev/logs || (echo "No local dev logs yet. Run: make dev-all" && exit 1)
	@tail -f .dev/logs/backend.log .dev/logs/frontend.log

dev-down: stop-local

stop-local:
	@for pidfile in .dev/pids/*.pid; do \
		test -f "$$pidfile" || continue; \
		pid=$$(cat "$$pidfile"); \
		if [ -n "$$pid" ]; then \
			echo "Stopping PID $$pid from $$pidfile"; \
			kill "$$pid" 2>/dev/null || true; \
		fi; \
	done
	@for port in 8000 3000; do \
		pids=$$(lsof -ti tcp:$$port 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "Stopping PID(s) $$pids on port $$port"; \
			kill $$pids 2>/dev/null || true; \
		fi; \
	done; \
	sleep 1; \
	for port in 8000 3000; do \
		pids=$$(lsof -ti tcp:$$port 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "Force stopping PID(s) $$pids on port $$port"; \
			kill -9 $$pids 2>/dev/null || true; \
		fi; \
	done
	@rm -f .dev/pids/*.pid 2>/dev/null || true

backend-install:
	cd backend && make install

backend-init-db: backend-env
	cd backend && make init-db

backend-infra-up: backend-env
	cd backend && docker compose -f deploy/compose/docker-compose.yml up -d postgres redis

backend-compose-up: backend-env
	cd backend && docker compose -f deploy/compose/docker-compose.yml up --build

backend-compose-down:
	cd backend && docker compose -f deploy/compose/docker-compose.yml down

backend-compose-logs:
	cd backend && docker compose -f deploy/compose/docker-compose.yml logs -f --tail=100

backend-api: backend-env
	cd backend && make run

backend-test:
	cd backend && make test

frontend-install:
	cd frontend && pnpm install

frontend-dev:
	cd frontend && pnpm dev

frontend-build:
	cd frontend && pnpm build

frontend-typecheck:
	cd frontend && pnpm check-types

check: backend-test frontend-typecheck frontend-build
