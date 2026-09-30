# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: `primary_slo.fast_successful_requests` (good event = `response_sent` với `latency_ms <= 3000`); panel **Latency percentiles and TTFT**.
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 3000ms` liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng chờ hơn 3 giây mới có câu trả lời, và mỗi request chậm đều đốt error budget 0.5%.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard: xác nhận P95/P99 tăng từ lúc nào; so với **TTFT P95**. Nếu TTFT vẫn khoảng 50 ms còn tổng latency tăng thì phần chậm nằm ngoài LLM (retrieval, prompt fetch, network).
  2. Log: lọc request chậm trong khoảng đó rồi lấy `correlation_id`:
     `python -c "import json;[print(r['correlation_id'],r['latency_ms']) for r in map(json.loads,open('data/logs.jsonl',encoding='utf-8')) if r.get('event')=='response_sent' and r['latency_ms']>3000]"`
  3. Trace: trên Langfuse, lọc metadata `correlation_id` = ID vừa lấy và mở waterfall. So thời lượng `retrieval` với `llm-generation` và với khoảng trống trong root `lab-agent-run` (khoảng trống này là lúc fetch prompt `day13-chat` từ Langfuse).
- Mitigation tạm thời: nếu `retrieval` chậm thì tắt practice incident (`python scripts/inject_incident.py --scenario <scenario> --disable`) hoặc chuyển sang fallback docs. Nếu `llm-generation` chậm sau khi đổi prompt thì rollback label `production` về version cũ. Nếu chậm vì fetch prompt thì kiểm tra network/Langfuse; SDK sẽ dùng cache hoặc fallback local.
- Owner: `student-2A202602630`

## Alert 2

- Tên: `HighErrorRateOrRetrievalFailure`
- Severity: `critical`
- Duration: `3m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: `guardrails.error_rate_pct_max = 2` và `guardrails.retrieval_success_rate_pct_min = 90`; panel **Error rate and retrieval success**. Mọi request lỗi đều tính là bad event của SLO chính.
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2%` **hoặc** retrieval success (`tool_success == true`) `< 90%`, liên tục 3 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 và không có câu trả lời. Lỗi thẳng thì đốt error budget rất nhanh, nên severity là critical và duration ngắn hơn.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard: xem error rate, breakdown `error_type` (ví dụ `RuntimeError`) và retrieval success % bắt đầu giảm từ phút nào.
  2. Log: lọc `event == "request_failed"`, đọc `error_type`, `tool_name`, `payload.detail` (đã scrub) và lấy `correlation_id`.
  3. Trace: mở trace cùng `correlation_id`; observation `retrieval` sẽ có level `ERROR` kèm status message (ví dụ `Vector store timeout`), còn `llm-generation` không chạy tới.
- Mitigation tạm thời: tắt practice incident hoặc khôi phục vector store/cấu hình retrieval. Nếu lỗi do thay đổi gần nhất thì rollback thay đổi đó. Tạm thời có thể trả lời bằng fallback docs thay vì trả 500.
- Owner: `student-2A202602630`

## Alert 3

- Tên: `CostOrTokenSpike`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: `guardrails.daily_cost_usd_max = 2.5`; panel **Cost over time** và **Input and output tokens**.
- Điều kiện và thời gian duy trì: chi phí trung bình mỗi request `> 2 ×` baseline (khoảng 0.0024 USD/request) **hoặc** `avg(tokens_out) > 400` (baseline 80–180), liên tục 10 phút.
- Ảnh hưởng tới người dùng: chưa gây lỗi ngay, nhưng câu trả lời dài bất thường làm tăng latency, tốn ngân sách và có thể hết budget ngày trước giờ. Đây thường là dấu hiệu prompt hoặc model mới có vấn đề.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard: xem cost/phút và `tokens_out` tăng từ lúc nào, so với thời điểm promote prompt hoặc deploy gần nhất.
  2. Log: lọc `response_sent` có `tokens_out` hoặc `cost_usd` cao, lấy `correlation_id`; so `tokens_in` (prompt dài hơn?) với `tokens_out` (output dài hơn?).
  3. Trace: mở trace; trong `llm-generation` xem `usage`, `cost` và `prompt_version`/`prompt_label` để biết request dùng prompt version nào.
- Mitigation tạm thời: nếu tăng sau khi đổi prompt thì rollback label `production` về version trước trên Langfuse (không cần deploy). Nếu không liên quan prompt thì tắt practice incident hoặc giới hạn `max_tokens`.
- Owner: `student-2A202602630`
