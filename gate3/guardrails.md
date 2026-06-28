# Guardrails

## Guardrails Về Access Và Session

| Guardrail | Bằng chứng hiện có |
| --- | --- |
| RBAC và identity theo organization | `ENFORCE_RBAC=true` mặc định, API routes có permission checks |
| Cookie session HttpOnly | Frontend BFF lưu access/refresh token trong cookie |
| Refresh token rotation | Backend access service xoay vòng refresh token và từ chối token reuse |
| Rate limiting | Mặc định: 120 requests trong 60 giây |
| Secret key chỉ nằm server-side | Provider keys là backend environment variables |

## Guardrails Cho AI

| Guardrail | Bằng chứng hiện có |
| --- | --- |
| Guardrails bật mặc định | `GUARDRAILS_ENABLED=true` |
| Provider fallback | Provider chain hỗ trợ fallback sang offline deterministic provider |
| PII masking | CV và AI services redact email, phone, profile URL và possible names |
| Prompt-injection checks | `detect_prompt_injection` scan untrusted text |
| Moderation path | JD/content moderation phát hiện banned terms và injection hits |
| Safety model route | Có setting safety model riêng cho moderation |
| Bounded agent runtime | ReAct runtime dùng allow-listed tools và step budget hữu hạn |
| Human-review boundary | Auto-approval bị giới hạn; không dùng auto-rejection |
| Token/cost accounting | AI usage logs lưu input tokens, output tokens, provider/model và cost |

## Guardrails Cho Document Và Data

| Guardrail | Bằng chứng hiện có |
| --- | --- |
| Signed URLs | Document upload/download dùng signed URL contracts |
| Scan state machine | Document có scan status trước khi được download |
| Internal scan callback token | Callback yêu cầu `X-Internal-Service-Token` |
| Constant-time token comparison | Callback dùng `hmac.compare_digest` |
| Audit trail | AI runs, usage logs và dashboard activity được persist |

## File Bằng Chứng Trong Repo

- `backend/app/shared/config.py`
- `backend/app/shared/security.py`
- `backend/app/bootstrap/middleware/rate_limit.py`
- `backend/app/modules/access/application/service.py`
- `backend/app/modules/access/api/rbac.py`
- `backend/app/ai/safety/pii.py`
- `backend/app/ai/safety/prompt_injection.py`
- `backend/app/ai/agents/react.py`
- `backend/app/ai/agents/workforce.py`
- `backend/app/modules/documents/api/__init__.py`
- `backend/app/modules/ai_operations/application/legacy_ai_service.py`