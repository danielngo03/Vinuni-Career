# G3 - Production-ready

Ngày chốt hồ sơ: 2026-06-27

## Trạng Thái Deliverables

| Deliverable | Trạng thái | File/link |
| --- | --- | --- |
| Deployed production URL | Xong | https://c2-app-037-production.up.railway.app/vi |
| Evaluation Metrics | Xong bản nháp | [evaluation-metrics.md](evaluation-metrics.md) |
| Guardrails | Xong | [guardrails.md](guardrails.md) |
| Demo video draft | Xong | [demo-video-draft.md](demo-video-draft.md) |
| Cost report | Xong bản nháp | [cost-report.md](cost-report.md) |

## Nội Dung Nộp

### 1. Production URL

```text
https://c2-app-037-production.up.railway.app/vi
```

### 2. Evaluation Metrics

| Metric | Baseline |
| --- | ---: |
| Production landing availability | 100% |
| Production landing median latency | 172 ms |
| Manual/API evidence pass rate | 7/7, 100% |
| Backend automated tests | 38 passed |
| Frontend production build | PASS |
| AI offline fallback token usage | 49 total tokens |
| Local demo AI usage cost | $0.01685 |
| Local demo cost per seeded user | $0.0042/user/month |

Chi tiết: [evaluation-metrics.md](evaluation-metrics.md)

### 3. Guardrails

| Nhóm | Guardrails |
| --- | --- |
| Access/session | RBAC, organization-scoped identity, HttpOnly cookies, refresh token rotation, rate limiting |
| AI safety | PII masking, prompt-injection checks, moderation, provider fallback, bounded agent runtime |
| Documents/data | Signed URLs, scan state machine, internal scan callback token, audit logs |

Chi tiết: [guardrails.md](guardrails.md)

### 4. Demo Video Draft

```text
https://www.youtube.com/watch?v=ofoAz2XVnHo
```

Trạng thái: chờ nhóm cung cấp link video.

Chi tiết kịch bản quay: [demo-video-draft.md](demo-video-draft.md)

### 5. Cost Report

| Metric | Giá trị |
| --- | ---: |
| AI usage rows | 6 |
| Input tokens | 9.744 |
| Output tokens | 3.508 |
| Total tokens | 13.252 |
| Tracked estimated cost | $0.01685 |
| Seeded users | 4 |
| Estimated cost/user/month | $0.0042 |

Chi tiết: [cost-report.md](cost-report.md)

## Cần Cập Nhật Trước Khi Nộp Cuối

| Mục | Việc cần làm |
| --- | --- |
| Demo video | Thay `TODO_VIDEO_URL` bằng link video thật |
| Cost report | Cập nhật lại nếu có billing export từ Railway hoặc AI provider |
| Evaluation metrics | Cập nhật lại nếu có thêm load test hoặc production API probe |
