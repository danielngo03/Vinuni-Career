# Evaluation Metrics

## Tóm Tắt Baseline

Ngày chốt baseline: 2026-06-27.

| Metric | Baseline number | Nguồn bằng chứng |
| --- | ---: | --- |
| Production landing availability | 5/5 request thành công, 100% | Kiểm tra live production URL |
| Production landing median latency | 172 ms | 5 mẫu GET tới `/vi` |
| Production landing average latency | 216 ms | 5 mẫu GET tới `/vi` |
| Manual/API evidence pass rate | 7/7, 100% | `eval/README.md` |
| Backend automated tests | 38 passed | `README.md` và `eval/README.md` |
| Frontend production build | PASS, tạo 26 routes | `eval/README.md` |
| AI offline fallback token baseline | 8 input, 41 output, 49 total tokens | `eval/README.md` TC-05 |
| Local demo AI usage cost | $0.01685 trên 13.252 tokens | `backend/vinuni_career.db` |
| Local demo cost per seeded user | $0.0042/user/month | 4 seeded users, lát cắt usage demo local |

## Kiểm Tra Production URL

Production URL:

```text
https://c2-app-037-production.up.railway.app/vi
```

Các mẫu quan sát:

| Lần đo | HTTP status | Thời gian ms |
| --- | ---: | ---: |
| 1 | 200 | 403 |
| 2 | 200 | 167 |
| 3 | 200 | 174 |
| 4 | 200 | 172 |
| 5 | 200 | 162 |

Baseline:

- Availability: 100% trong spot check 5 requests.
- Median latency: 172 ms.
- Average latency: 216 ms.
- Max latency: 403 ms.

## Functional Evaluation

Evaluation evidence hiện có ghi nhận các test case sau đều PASS:

1. Health endpoint.
2. Student login và identity resolution.
3. Student dashboard.
4. Approved jobs pagination.
5. AI offline fallback.
6. Document upload session.
7. RBAC denial khi Student truy cập University dashboard.

Baseline:

```text
7/7 manual/API evidence cases pass = 100%
```

## Automated Evaluation

Baseline đã ghi nhận:

```text
Backend test suite: 38 passed
Frontend TypeScript check: PASS
Frontend production build: PASS
Generated frontend routes: 26
```

## AI Evaluation Baseline

Case offline fallback xác nhận AI path vẫn có thể trả lời khi không có external
provider key:

```text
provider: offline
model: offline-deterministic
input_tokens: 8
output_tokens: 41
total_tokens: 49
```

## Khoảng Trống Còn Lại

- Chưa có báo cáo production load test chính thức.
- Chưa có model-quality evaluation dataset cho CV extraction, matching, ranking
  hoặc interview report.
- Chưa có billing export từ provider. Số cost hiện tại lấy từ usage log local.
