# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Phạm Minh Hiếu
- **MSSV:** 2A202602630
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/hieulovecat/K4-L3-DAY13-PhamMinhHieu-2A202602630-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602630`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu field bắt buộc, 0 correlation ID, thiếu enrichment) | | |
| `validate_dashboard.py` | 6/6 panel | | |
| `pytest` | 22 passed | | |
| Số traces hợp lệ | 0 (chưa cấu hình Langfuse key) | | |
| Số PII leak | 0 (validator) | | |
| Latency P95 / TTFT P95 | | | |
| Retrieval success rate | | | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` ([app/middleware.py](../app/middleware.py)) chạy đầu mỗi request: (1) `clear_contextvars()` để xóa context còn sót từ request trước trên cùng worker; (2) đọc header `x-request-id`, chỉ chấp nhận nếu khớp `^[A-Za-z0-9._-]{1,64}$`, ngược lại sinh `req-<8-hex>` từ `uuid4`; (3) `bind_contextvars(correlation_id=...)` nên mọi log line sau đó tự có `correlation_id`, đồng thời lưu vào `request.state` để truyền sang `agent.run()` (dùng cho trace metadata ở CP2); (4) trả lại `x-request-id` và `x-response-time-ms` trong response header để client/người báo lỗi đưa lại đúng ID.
- **Các metadata được ghi vào structured log:** ngoài `ts`, `level`, `service`, `event`, `correlation_id`, handler `/chat` ([app/main.py](../app/main.py)) bind `user_id_hash` (SHA-256 cắt 12 ký tự, không log `user_id` gốc), `session_id`, `feature`, `model`, `env` trước log `request_received`. Log `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`; log `request_failed` có `error_type`. Nội dung người dùng chỉ ghi dạng preview đã scrub (`message_preview`, `answer_preview`, tối đa 80 ký tự).
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` ([app/logging_config.py](../app/logging_config.py)) được đăng ký sau `format_exc_info` và **trước** `JsonlFileProcessor`/`JSONRenderer`, nên cả nội dung exception cũng được scrub và không có dữ liệu thô nào chạm tới file hay stdout. `scrub_event` duyệt đệ quy mọi field (string, dict, list lồng nhau), không chỉ `payload`/`event`. Regex trong [app/pii.py](../app/pii.py) gồm email, thẻ thanh toán, CCCD 12 số, điện thoại VN (`0`/`+84`, có hoặc không dấu cách/chấm/gạch) và hộ chiếu VN (`[A-Z]\d{7}`); thẻ và CCCD chạy trước điện thoại để số thẻ không bị redact nhầm một phần thành `PHONE_VN` rồi lộ phần còn lại.
- **Cách kiểm chứng kết quả:**
  - `python scripts/validate_logs.py`: từ 30/100 (baseline) lên **100/100** — 0 record thiếu field, 0 thiếu enrichment, nhiều correlation ID khác nhau, 0 PII leak ([evidence/02-log-validator.txt](evidence/02-log-validator.txt)).
  - Structured log của một request: `request_received` và `response_sent` cùng `correlation_id` và metadata ([evidence/04-structured-log.txt](evidence/04-structured-log.txt)).
  - Gửi request chứa email, SĐT, CCCD, số thẻ test và hộ chiếu **giả** với `x-request-id: pii-demo-01`: log chỉ còn `[REDACTED_*]`, đếm giá trị thô trong `data/logs.jsonl` đều bằng 0 ([evidence/05-pii-redaction.txt](evidence/05-pii-redaction.txt)).
  - Header: gửi `x-request-id: my-test-123` → trả lại nguyên ID; không gửi → sinh `req-xxxxxxxx`; gửi ID bẩn `bad id<script>` → bị thay bằng ID mới.
  - Unit test trong [tests/test_pii.py](../tests/test_pii.py): email, 5 định dạng SĐT, CCCD, 3 định dạng thẻ, hộ chiếu, text thường không bị redact nhầm, và `scrub_event` scrub cả field lồng nhau/exception; `pytest` 27 passed.
  - Trước khi đo lại đã chuyển `data/logs.jsonl` baseline ra ngoài repo, vì validator đọc toàn bộ file và sẽ tính cả log chưa scrub từ trước khi sửa code.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** key trong `.env` là key của project `day13-k4-l3b-2A202602630`, và `/health` trả `tracing_enabled: true`. Mọi trace do tôi tự chạy `scripts/load_test.py` và `curl` tạo ra. Mỗi trace có `correlation_id` trùng với một dòng trong `data/logs.jsonl` của tôi (ví dụ `req-cp2test1` → trace `35f3d9824e70e9576b8c5d553012416a`).
- **Cấu trúc root/retrieval/generation observations:** [app/agent.py](../app/agent.py) dùng decorator `@observe` của Langfuse SDK v4:
  ```text
  day13-agent-request (trace)
  └── lab-agent-run            (agent)      metadata: correlation_id, feature, model, prompt_name/label/version/source, doc_count
      ├── retrieval            (retriever)  input: query_preview đã scrub; output: doc_count, docs_preview; metadata: retrieval_hit
      └── llm-generation       (generation) model, usage_details {input, output, total}, cost_details {input, output, total}, prompt (link tới prompt version), ttft_ms
  ```
  `capture_input/capture_output=False` trên cả ba observation nên không có raw prompt/answer trên Langfuse, chỉ có preview đã qua `scrub_text`. Cost tính theo giá 3 USD/1M input token và 15 USD/1M output token, khớp với `cost_usd` trong log. Khi retrieval lỗi, `@observe` tự đánh dấu observation `retrieval` và root là `ERROR` kèm status message (đã thử với practice `tool_fail`: trace `7065bf3cc97e2d3911f590d8ad7bf4cd`, `Vector store timeout`).
- **Cách nối trace với log:** middleware tạo `correlation_id` và truyền vào `agent.run()`. `propagate_attributes(metadata={"correlation_id": ...})` gắn ID đó cho mọi observation trong trace, còn structlog contextvars gắn cùng ID cho mọi dòng log. Từ log lấy `correlation_id`, lên Langfuse lọc metadata `correlation_id` là ra đúng trace (và ngược lại). `user_id` trên trace là cùng `user_id_hash` với log.
- **Prompt name:**
- **Version/label baseline:**
- **Version/label candidate:**
- **Trace ID của mỗi version:**
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [scripts/dashboard.py](../scripts/dashboard.py) là dashboard local, chỉ dùng thư viện chuẩn và PyYAML. Chạy `python scripts/dashboard.py` rồi mở `http://localhost:8501`. Mỗi lần tải trang, script đọc `data/logs.jsonl` và `config/dashboard.yaml`, vẽ đúng 6 panel theo contract: Latency P50/P95/P99 + TTFT P95 (ms), Traffic (requests/phút), Error rate + breakdown `error_type` + retrieval success (%), Cost theo phút + tổng (USD), Tokens in/out (tokens), Quality proxy mean (0–1). Time range mặc định 60 phút, tự refresh 30 giây, mỗi panel có đơn vị, đường threshold nét đứt và dòng trạng thái `OK`/`BREACHED` so với threshold trong contract. `validate_dashboard.py` đạt 6/6.
- **SLO và lý do chọn:** giữ SLO trong [config/slo.yaml](../config/slo.yaml): **99.5% request thành công và `latency_ms <= 3000` trong cửa sổ 28 ngày**. SLI = số `response_sent` có latency ≤ 3000 ms / số `request_received`. Baseline khi prompt đã cache là khoảng 160–600 ms (generation khoảng 150 ms, TTFT khoảng 50 ms), nên 3000 ms vẫn còn đủ khoảng cho lúc network/Langfuse chậm mà vẫn bắt được `rag_slow` (+2.5 s ở retrieval). Lý do chi tiết ghi ở mục `explanation` trong file.
- **Cách tính error budget:** error budget = 100% − 99.5% = **0.5%**. Với 10,000 request/28 ngày thì tối đa 50 request được phép lỗi hoặc chậm hơn 3000 ms. Burn rate = tỉ lệ request xấu / 0.005; ví dụ 5% request xấu trong 1 giờ là đốt nhanh gấp 10 lần. Chính sách: còn dưới 50% budget thì dừng promote prompt/model mới; hết budget thì freeze thay đổi.
- **Ba alert và runbook tương ứng:** [config/alert_rules.yaml](../config/alert_rules.yaml) và [docs/alerts.md](../docs/alerts.md). Cả ba đều symptom-based, gửi Slack `#k4-l3b-alerts`, owner `student-2A202602630`:
  | Alert | Severity | Điều kiện | Duration | Runbook |
  |---|---|---|---|---|
  | `HighLatencyP95` | warning | `p95(latency_ms) > 3000` | 5m | [alert-1](../docs/alerts.md#alert-1) |
  | `HighErrorRateOrRetrievalFailure` | critical | error rate > 2% **hoặc** retrieval success < 90% | 3m | [alert-2](../docs/alerts.md#alert-2) |
  | `CostOrTokenSpike` | warning | avg cost/request > 2× baseline **hoặc** avg `tokens_out` > 400 | 10m | [alert-3](../docs/alerts.md#alert-3) |

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
