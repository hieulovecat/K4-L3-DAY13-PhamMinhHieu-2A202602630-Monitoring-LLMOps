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

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
- **Cấu trúc root/retrieval/generation observations:**
- **Cách nối trace với log:**
- **Prompt name:**
- **Version/label baseline:**
- **Version/label candidate:**
- **Trace ID của mỗi version:**
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
- **SLO và lý do chọn:**
- **Cách tính error budget:**
- **Ba alert và runbook tương ứng:**

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
