# Báo Cáo Chi Phí

## Cách Hệ Thống Ghi Nhận Cost

Ứng dụng ghi AI usage trong bảng `ai_usage_logs` với các trường:

- input tokens
- output tokens
- provider
- model
- estimated cost theo USD

Với legacy AI usage không có raw provider usage, code ước tính cost bằng công
thức:

```text
cost_usd = round((input_tokens + output_tokens) * 0.0000002, 6)
```

Các dòng seeded OpenRouter demo dashboard dùng:

```text
input_tokens = 2400
output_tokens = 850
cost_usd = 0.0042
```

## Usage Baseline Hiện Có

Từ `backend/vinuni_career.db`:

| Metric | Giá trị |
| --- | ---: |
| Số dòng AI usage | 6 |
| Input tokens | 9.744 |
| Output tokens | 3.508 |
| Total tokens | 13.252 |
| Tracked estimated cost | $0.01685 |
| Seeded users | 4 |
| Seeded organizations | 5 |

## Cost Per User Per Month

Nếu xem usage demo local hiện có là một lát cắt usage theo tháng:

```text
$0.01685 / 4 users = $0.0042125 per user per month
```

Làm tròn:

```text
Estimated cost/user/month = $0.0042
```

## Usage Theo Feature

| Feature | Rows | Input tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: |
| cv_job_match | 2 | 144 | 108 | $0.00005 |
| demo_dashboard_seed | 4 | 9.600 | 3.400 | $0.01680 |

## Usage Theo Provider

| Provider | Model | Rows | Total tokens | Estimated cost |
| --- | --- | ---: | ---: | ---: |
| local/unspecified | local estimate | 2 | 252 | $0.00005 |
| openrouter | nvidia/nemotron-3-ultra-550b-a55b:free | 4 | 13.000 | $0.01680 |

## AI Runs

Bảng `ai_runs` hiện có:

| Status | Rows | Prompt tokens | Completion tokens | Cost |
| --- | ---: | ---: | ---: | ---: |
| DONE | 1 | 38 | 572 | $0.00 |

Cost report ưu tiên bảng `ai_usage_logs` vì bảng đó lưu tracked estimated
costs.

## Ước Tính Khi Scale Đơn Giản

Dùng baseline hiện tại là `$0.0042125/user/month`:

| Monthly active users | Estimated monthly AI cost |
| ---: | ---: |
| 100 | $0.42 |
| 1.000 | $4.21 |
| 10.000 | $42.13 |

## Caveats

- Các con số là demo/local estimates, chưa phải production billing.
- Cost thực tế phụ thuộc vào provider, model, prompt length, output length,
  retry count, cache hit rate và hành vi người dùng thật.
- Một số model cấu hình có thể thuộc free tier, nhưng app vẫn ghi estimated
  cost để có kỷ luật theo dõi chi phí.
