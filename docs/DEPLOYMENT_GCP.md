# Google Cloud Deployment Guide

Production deployment of the VinUni Career Platform on Google Cloud, driven
from GitHub. This is the operational companion to the code shipped in
`backend/Dockerfile`, `frontend/Dockerfile`, and `cloudbuild.yaml`.

## 1. Architecture (what runs where)

One Google Cloud project runs everything:

| Piece | Google Cloud service | Why |
|---|---|---|
| Frontend (Next.js 15) | Cloud Run service `vinuni-career-web` | Autoscaling container; the ONLY public entry point |
| Backend (FastAPI) | Cloud Run service `vinuni-career-api` | Autoscaling container |
| Background scheduler | Cloud Run service `vinuni-career-scheduler` (`python -m app.worker`, min=max=1 instance, CPU always-on) | Outbox email drain, deadline close, sweeps — designed to run exactly once |
| DB migrations | Cloud Run job `vinuni-career-migrate` (`alembic upgrade head`) | Migrations are a release step, never at app startup |
| PostgreSQL 16 | Cloud SQL for PostgreSQL | Managed, backed up |
| Redis | Memorystore for Redis (or Upstash for low cost) | Token revocation, fit cache; some opportunities endpoints 503 without it |
| Files (CVs, photos, logos, banners) | Cloud Storage bucket + `STORAGE_BACKEND=gcs` | Cloud Run's disk is ephemeral; local files vanish on restart |
| Secrets | Secret Manager | Never bake secrets into images or triggers |
| Images | Artifact Registry repo `vinuni-career` | Stores built Docker images |
| CI/CD | Cloud Build GitHub trigger → `cloudbuild.yaml` | Push to branch = build + migrate + deploy |

**Origin model (important):** the browser only ever talks to the frontend
origin. The Next.js server proxies `/api/v1/*` to the backend
(`next.config.ts` rewrites, target = `NEXT_PUBLIC_API_URL`). This keeps the
httpOnly refresh cookie same-origin (`SameSite=Lax`) — do NOT point browsers
directly at the API service. The API service can therefore stay
ingress-restricted ("internal + load balancing" or all-ingress but only
reached via the proxy).

## 2. One-time project setup

```bash
gcloud auth login
gcloud projects create vinuni-career-prod        # or use an existing project
gcloud config set project vinuni-career-prod
# Billing must be linked in the console before the next steps.

gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com redis.googleapis.com compute.googleapis.com

gcloud artifacts repositories create vinuni-career \
  --repository-format=docker --location=asia-southeast1
```

Region default in this guide: `asia-southeast1` (Singapore — closest to Vietnam).

### 2.1 Cloud SQL (PostgreSQL)

```bash
gcloud sql instances create vinuni-career-pg \
  --database-version=POSTGRES_16 --region=asia-southeast1 \
  --tier=db-g1-small --storage-size=20GB --storage-auto-increase
gcloud sql databases create vinuni_career --instance=vinuni-career-pg
gcloud sql users create app --instance=vinuni-career-pg --password='<STRONG_PW>'
```

`DATABASE_URL` for Cloud Run (asyncpg over the Cloud SQL unix socket):

```
postgresql+asyncpg://app:<STRONG_PW>@/vinuni_career?host=/cloudsql/vinuni-career-prod:asia-southeast1:vinuni-career-pg
```

Attach the instance to every backend workload with
`--add-cloudsql-instances=vinuni-career-prod:asia-southeast1:vinuni-career-pg`
(services) / `--set-cloudsql-instances=...` (jobs).

Note: pgvector — run `CREATE EXTENSION IF NOT EXISTS vector;` once via
`gcloud sql connect` if `PGVECTOR_ENABLED=true`.

### 2.2 Cloud Storage (uploaded CVs, photos, logos, banners)

```bash
gcloud storage buckets create gs://vinuni-career-media \
  --location=asia-southeast1 --uniform-bucket-level-access \
  --public-access-prevention
```

The bucket stays **private**: every download flows through the app's RBAC +
signed-token endpoints (`/api/v1/cv-files/{token}` etc.), which is how CV
watermarking and access audit keep working. Backend env:
`STORAGE_BACKEND=gcs`, `GCS_BUCKET_NAME=vinuni-career-media`.

### 2.3 Redis

```bash
gcloud redis instances create vinuni-career-redis \
  --region=asia-southeast1 --size=1 --redis-version=redis_7_0
```

Memorystore is VPC-only: create a Serverless VPC Access connector and attach
it (`--vpc-connector`) to the api + scheduler services. Cost-saving
alternative: a TLS Redis from Upstash — then `REDIS_URL=rediss://...` and no
connector is needed.

### 2.4 Secrets

```bash
printf '%s' '<value>' | gcloud secrets create JWT_SECRET_KEY --data-file=-
# Repeat for: DATABASE_URL, GOOGLE_OAUTH_CLIENT_SECRET, OPENROUTER_API_KEY,
# GEMINI_API_KEY, SMTP_PASSWORD, AI_PROVIDER_KEY_ENCRYPTION_KEYS, TOTP_ENCRYPTION_KEY
```

Generate the two Fernet keys (both REQUIRED when `APP_ENV != local` — startup
fails without them):

```bash
cd backend && uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Grant the Cloud Run runtime service account
`roles/secretmanager.secretAccessor`, `roles/cloudsql.client`, and
`roles/storage.objectAdmin` on the media bucket.

## 3. Backend environment (Cloud Run)

Non-secret env vars for `vinuni-career-api`, `vinuni-career-scheduler`, and
the migrate job (secrets are attached with `--set-secrets`):

```
APP_ENV=production
APP_URL=https://career.example.com        # public origin (see §5 OAuth)
FRONTEND_URL=https://career.example.com
CORS_ALLOW_ORIGINS=https://career.example.com
STORAGE_BACKEND=gcs
GCS_BUCKET_NAME=vinuni-career-media
REDIS_URL=redis://10.x.x.x:6379/0
EMAIL_PROVIDER=smtp
SMTP_HOST=... SMTP_PORT=587 SMTP_USERNAME=...   # + SMTP_PASSWORD secret
EMAIL_FROM_ADDRESS=career@vinuni.edu.vn
BACKGROUND_WORKER_MODE=inline             # scheduler service overrides to `scheduler`
GOOGLE_OAUTH_CLIENT_ID=xxxx.apps.googleusercontent.com   # + secret for the client secret
OAUTH_REDIRECT_BASE_URL=https://career.example.com
AI_DEFAULT_PROVIDER=openrouter            # + OPENROUTER_API_KEY / GEMINI_API_KEY secrets
```

Only the scheduler service sets `BACKGROUND_WORKER_MODE=scheduler`. Never set
it on the autoscaled api service — the design assumes exactly one scheduler
instance (`min-instances=1 --max-instances=1 --no-cpu-throttling`).

## 4. First deploy (manual), then CI/CD

### 4.1 Manual bootstrap

```bash
# Backend image
cd backend
gcloud builds submit --tag asia-southeast1-docker.pkg.dev/$PROJECT/vinuni-career/api:boot .

# Migration job (creates schema)
gcloud run jobs create vinuni-career-migrate \
  --image=asia-southeast1-docker.pkg.dev/$PROJECT/vinuni-career/api:boot \
  --region=asia-southeast1 --command=alembic --args=upgrade,head \
  --set-cloudsql-instances=... --set-secrets=DATABASE_URL=DATABASE_URL:latest \
  --set-env-vars=APP_ENV=production,...
gcloud run jobs execute vinuni-career-migrate --wait

# API service
gcloud run deploy vinuni-career-api \
  --image=asia-southeast1-docker.pkg.dev/$PROJECT/vinuni-career/api:boot \
  --region=asia-southeast1 --allow-unauthenticated \
  --add-cloudsql-instances=... --vpc-connector=... \
  --set-env-vars=... --set-secrets=... \
  --cpu=1 --memory=1Gi --min-instances=0 --max-instances=4
# → note the printed URL: https://vinuni-career-api-xxxx.a.run.app

# Scheduler (exactly one instance, CPU always on)
gcloud run deploy vinuni-career-scheduler \
  --image=asia-southeast1-docker.pkg.dev/$PROJECT/vinuni-career/api:boot \
  --region=asia-southeast1 --no-allow-unauthenticated \
  --command=python --args=-m,app.worker \
  --min-instances=1 --max-instances=1 --no-cpu-throttling \
  --set-env-vars=BACKGROUND_WORKER_MODE=scheduler,... --set-secrets=...

# Frontend image — NEXT_PUBLIC_* are BUILD args (baked into the JS bundle)
cd ../frontend
gcloud builds submit --config=- . <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: [build,
      --build-arg=NEXT_PUBLIC_APP_URL=https://career.example.com,
      --build-arg=NEXT_PUBLIC_API_URL=https://vinuni-career-api-xxxx.a.run.app,
      -t, asia-southeast1-docker.pkg.dev/$PROJECT_ID/vinuni-career/web:boot, .]
images: [asia-southeast1-docker.pkg.dev/$PROJECT_ID/vinuni-career/web:boot]
EOF

gcloud run deploy vinuni-career-web \
  --image=asia-southeast1-docker.pkg.dev/$PROJECT/vinuni-career/web:boot \
  --region=asia-southeast1 --allow-unauthenticated \
  --cpu=1 --memory=512Mi --min-instances=0 --max-instances=4
```

Custom domain: Cloud Run → Manage custom domains → map
`career.example.com` to `vinuni-career-web` (or put a global HTTPS load
balancer in front later). After the domain is live, rebuild the web image
with the final `NEXT_PUBLIC_APP_URL` and update `APP_URL`/`FRONTEND_URL`/
`CORS_ALLOW_ORIGINS`/`OAUTH_REDIRECT_BASE_URL` on the backend.

### 4.2 CI/CD from GitHub

1. Push the repository to GitHub.
2. Console → Cloud Build → Triggers → Connect repository (GitHub app).
3. Create a trigger on the production branch pointing at `cloudbuild.yaml`,
   and set the substitutions (`_PUBLIC_ORIGIN`, `_API_ORIGIN`, `_REGION`, …).
4. Every push now: builds api+web images → runs the migration job → deploys
   api, scheduler, web.

The pipeline deploys by updating only the image; env vars and secrets set in
§4.1 are preserved by `gcloud run deploy`.

## 5. Google OAuth ("Sign in with Google")

The code is fully implemented (backend `auth` module: start/callback/
exchange/link-confirm; `oidc_accounts` table; frontend buttons + callback
pages). It activates when credentials exist — no schema or code changes.

Register in **Google Cloud Console → APIs & Services**:

1. **OAuth consent screen**: External → app name "VinUni Career", support
   email, authorized domain (`example.com`), scopes `openid`, `email`,
   `profile`. While in *Testing* mode only listed test users can sign in —
   click **Publish app** for production.
2. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized JavaScript origins:
     `https://career.example.com` (+ `http://localhost:3000` for dev)
   - Authorized redirect URIs (the backend callback, reached THROUGH the
     frontend proxy so the nonce cookie stays same-origin):
     `https://career.example.com/api/v1/auth/oauth/google/callback`
     (+ `http://localhost:3000/api/v1/auth/oauth/google/callback` for dev)
3. Copy the Client ID / Client secret into backend env:
   `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (secret), and set
   `OAUTH_REDIRECT_BASE_URL=https://career.example.com`.

Flow sanity check: login page button → `/api/v1/auth/oauth/google/start` →
Google → redirect URI above → backend issues a one-time ticket → frontend
`/auth/oauth/callback` exchanges it → tokens issued. Google-verified emails
skip email verification; accounts with the same email get a link-confirm
step; `password_hash` is nullable so Google-only accounts are supported.

## 6. Production gaps this pack closed (and what's still open)

Shipped in this change-set:

- `GcsStorageBackend` + `STORAGE_BACKEND=gcs` factory branch (was hardcoded
  local; Cloud Run would lose every upload).
- knowledge_base upload now actually persists bytes (pre-existing bug: the
  file was never written, so ingestion always read a missing file).
- knowledge_base ingestion + onboarding doc-verification read via the storage
  backend instead of raw `open()` on a storage key (the onboarding OCR path
  was silently broken even locally).
- `backend/Dockerfile` (uv, `$PORT`, non-root, optional OCR layer),
  `frontend/Dockerfile` (pnpm, Next standalone), `.dockerignore`s,
  `output: "standalone"` in `next.config.ts`, `cloudbuild.yaml`.
- `.env.example` gaps: `CORS_ALLOW_ORIGINS`, GCS vars, Google OAuth vars,
  `NEXT_PUBLIC_API_URL`, required-in-prod Fernet keys.

Still open (deliberate, not blockers for first deploy):

- GCS-native signed URLs / streaming (today files stream through the app —
  fine at current scale, and required for watermarking anyway).
- `chat_export_files` stores CSV bytes in Postgres (small, acceptable).
- Celery stays inert (inline queue + asyncio scheduler cover current load);
  when task volume grows, add a Celery worker service + Memorystore broker.
- Observability: wire Langfuse env vars; Cloud Run gives logs/metrics out of
  the box.
