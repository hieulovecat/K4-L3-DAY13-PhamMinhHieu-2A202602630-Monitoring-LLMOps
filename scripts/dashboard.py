"""Local runtime dashboard for the six panels defined in config/dashboard.yaml.

Reads data/logs.jsonl on every page load (no extra dependencies) and renders inline SVG
charts with units, the 60-minute time range and each panel's threshold line.

    python scripts/dashboard.py                 # serve on http://localhost:8501 (auto-refresh)
    python scripts/dashboard.py --once out.html # write a static snapshot and exit
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
COLORS = ["#2563eb", "#d97706", "#dc2626", "#059669"]
OPS = {"lte": "≤", "gte": "≥"}


# ---------- data ----------

def load_records(path: Path, start: datetime, end: datetime) -> list[dict]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError):
            continue
        if start <= ts <= end:
            rec["_ts"] = ts
            records.append(rec)
    return records


def by_minute(records: list[dict], event: str) -> dict[datetime, list[dict]]:
    buckets: dict[datetime, list[dict]] = defaultdict(list)
    for rec in records:
        if rec.get("event") == event:
            buckets[rec["_ts"].replace(second=0, microsecond=0)].append(rec)
    return buckets


def compute(records: list[dict], minutes: list[datetime]) -> dict:
    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]
    tool = [r for r in records if r.get("tool_success") is not None]
    sent_m, recv_m, fail_m = by_minute(records, "response_sent"), by_minute(records, "request_received"), by_minute(records, "request_failed")

    def series(buckets, fn):
        return [fn(buckets[m]) if buckets.get(m) else None for m in minutes]

    lat = lambda rs, p: percentile([r["latency_ms"] for r in rs], p)
    return {
        "latency": {
            "stats": {
                "P50": percentile([r["latency_ms"] for r in sent], 50),
                "P95": percentile([r["latency_ms"] for r in sent], 95),
                "P99": percentile([r["latency_ms"] for r in sent], 99),
                "TTFT P95": percentile([r["ttft_ms"] for r in sent], 95),
            },
            "series": {
                "P50": series(sent_m, lambda rs: lat(rs, 50)),
                "P95": series(sent_m, lambda rs: lat(rs, 95)),
                "P99": series(sent_m, lambda rs: lat(rs, 99)),
                "TTFT P95": series(sent_m, lambda rs: percentile([r["ttft_ms"] for r in rs], 95)),
            },
            "check": percentile([r["latency_ms"] for r in sent], 95),
        },
        "traffic": {
            "stats": {"total requests": len(received), "req/min (avg)": round(len(received) / max(1, len(minutes)), 2)},
            "series": {"requests/min": [len(recv_m.get(m, [])) for m in minutes]},
            "check": round(len(received) / max(1, len(minutes)), 2),
        },
        "errors": {
            "stats": {
                "error rate %": round(len(failed) / len(received) * 100, 2) if received else 0.0,
                "retrieval success %": round(sum(1 for r in tool if r["tool_success"]) / len(tool) * 100, 2) if tool else 100.0,
                "by type": ", ".join(f"{k}={v}" for k, v in Counter(r.get("error_type") for r in failed).items()) or "none",
            },
            "series": {
                "error rate %": [
                    round(len(fail_m.get(m, [])) / len(recv_m[m]) * 100, 2) if recv_m.get(m) else None for m in minutes
                ],
            },
            "check": round(len(failed) / len(received) * 100, 2) if received else 0.0,
        },
        "cost": {
            "stats": {"total USD": round(sum(r["cost_usd"] for r in sent), 4), "avg USD/request": round(sum(r["cost_usd"] for r in sent) / len(sent), 6) if sent else 0.0},
            "series": {"USD/min": series(sent_m, lambda rs: round(sum(r["cost_usd"] for r in rs), 6))},
            "check": round(sum(r["cost_usd"] for r in sent), 4),
        },
        "tokens": {
            "stats": {"tokens_in": sum(r["tokens_in"] for r in sent), "tokens_out": sum(r["tokens_out"] for r in sent)},
            "series": {
                "tokens_in/min": series(sent_m, lambda rs: sum(r["tokens_in"] for r in rs)),
                "tokens_out/min": series(sent_m, lambda rs: sum(r["tokens_out"] for r in rs)),
            },
            "check": max(sum(r["tokens_in"] for r in sent), sum(r["tokens_out"] for r in sent)),
        },
        "quality": {
            "stats": {"mean": round(sum(r["quality_score"] for r in sent) / len(sent), 3) if sent else 0.0},
            "series": {"mean/min": series(sent_m, lambda rs: round(sum(r["quality_score"] for r in rs) / len(rs), 3))},
            "check": round(sum(r["quality_score"] for r in sent) / len(sent), 3) if sent else None,
        },
    }


# ---------- rendering ----------

def svg_chart(minutes: list[datetime], series: dict[str, list], threshold: float | None, unit: str, per_minute_threshold: bool) -> str:
    w, h, pl, pr, pt, pb = 560, 200, 56, 12, 12, 26
    values = [v for s in series.values() for v in s if v is not None]
    top = max(values + ([threshold] if threshold is not None and per_minute_threshold else []) + [1e-9]) * 1.15
    n = len(minutes)
    x = lambda i: pl + (w - pl - pr) * i / max(1, n - 1)
    y = lambda v: pt + (h - pt - pb) * (1 - v / top)
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(unit)} chart">']
    for frac in (0, 0.5, 1):
        v = top * frac
        parts.append(f'<line x1="{pl}" x2="{w - pr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        label = f"{v:,.0f}" if v >= 100 else f"{v:.3g}"
        parts.append(f'<text x="{pl - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{label}</text>')
    for i in (0, n // 2, n - 1):
        parts.append(f'<text x="{x(i):.1f}" y="{h - 6}" text-anchor="middle" class="axis">{minutes[i].strftime("%H:%M")}</text>')
    for idx, (name, vals) in enumerate(series.items()):
        color = COLORS[idx % len(COLORS)]
        pts = [(x(i), y(v)) for i, v in enumerate(vals) if v is not None]
        if len(pts) > 1:
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
        for a, b in pts:
            parts.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="2.5" fill="{color}"/>')
    if threshold is not None and per_minute_threshold:
        parts.append(f'<line x1="{pl}" x2="{w - pr}" y1="{y(threshold):.1f}" y2="{y(threshold):.1f}" class="threshold"/>')
    parts.append("</svg>")
    return "".join(parts)


def render(minutes_window: int = 60) -> str:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["dashboard"]
    end = datetime.now(timezone.utc).replace(second=59, microsecond=999999)
    start = (end - timedelta(minutes=minutes_window - 1)).replace(second=0, microsecond=0)
    minutes = [start + timedelta(minutes=i) for i in range(minutes_window)]
    data = compute(load_records(LOG_PATH, start, end), minutes)

    cards = []
    # Thresholds on per-request / per-minute aggregations are drawn as a line; window totals are checked as a stat.
    line_thresholds = {"latency", "traffic", "errors", "quality"}
    for panel in config["panels"]:
        pid, th = panel["id"], panel["threshold"]
        d = data[pid]
        check = d["check"]
        ok = check is None or (check <= th["value"] if th["operator"] == "lte" else check >= th["value"])
        stats = "".join(f"<div class='stat'><span>{html.escape(k)}</span><b>{v if isinstance(v, str) else f'{v:,}'}</b></div>" for k, v in d["stats"].items())
        legend = "".join(f"<span><i style='background:{COLORS[i % len(COLORS)]}'></i>{html.escape(n)}</span>" for i, n in enumerate(d["series"]))
        cards.append(
            f"<section class='card'><header><h2>{html.escape(panel['title'])}</h2><span class='unit'>unit: {html.escape(panel['unit'])}</span></header>"
            f"<div class='stats'>{stats}</div>"
            f"{svg_chart(minutes, d['series'], th['value'], panel['unit'], pid in line_thresholds)}"
            f"<div class='legend'>{legend}<span><i class='dash'></i>threshold</span></div>"
            f"<p class='th {'ok' if ok else 'bad'}'>Threshold: {th['aggregation']} {OPS[th['operator']]} {th['value']:,} {html.escape(panel['unit'])} → "
            f"current {check if check is not None else 'n/a'} {'OK' if ok else 'BREACHED'}</p></section>"
        )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(config['title'])}</title>
<style>
:root{{--bg:#f8fafc;--card:#fff;--fg:#0f172a;--muted:#64748b;--grid:#e2e8f0;--ok:#047857;--bad:#b91c1c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b1120;--card:#111827;--fg:#e5e7eb;--muted:#94a3b8;--grid:#1f2937;--ok:#34d399;--bad:#f87171}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}}
.top{{padding:14px 16px;border-bottom:1px solid var(--grid)}} h1{{font-size:18px;margin:0}} .meta{{color:var(--muted);font-size:12px}}
.grid6{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px;padding:16px}}
.card{{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:12px 14px}}
.card header{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}} h2{{font-size:15px;margin:0}}
.unit,.axis{{color:var(--muted);fill:var(--muted);font-size:11px}} .grid{{stroke:var(--grid)}}
.threshold{{stroke:var(--bad);stroke-dasharray:6 4;stroke-width:1.5}}
.stats{{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0}} .stat span{{color:var(--muted);font-size:11px;display:block}} .stat b{{font-size:16px}}
.legend{{display:flex;flex-wrap:wrap;gap:10px;font-size:11px;color:var(--muted)}} .legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}}
.legend i.dash{{height:0;border-top:2px dashed var(--bad);border-radius:0}}
.th{{margin:6px 0 0;font-size:12px}} .ok{{color:var(--ok)}} .bad{{color:var(--bad);font-weight:600}} svg{{width:100%;height:auto;display:block}}
</style></head><body>
<div class="top"><h1>{html.escape(config['title'])}</h1>
<div class="meta">Time range: last {minutes_window} min ({start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%H:%M')} UTC) · source: data/logs.jsonl · auto-refresh {config['refresh_seconds']}s · rendered {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</div></div>
<main class="grid6">{''.join(cards)}</main>
<script>setTimeout(()=>location.reload(),{config['refresh_seconds'] * 1000});</script>
</body></html>"""


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Serve the Day 13 six-panel dashboard")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--minutes", type=int, default=60, help="time range (contract default: 60)")
    parser.add_argument("--once", type=Path, help="write a static HTML snapshot to this path and exit")
    args = parser.parse_args()

    if args.once:
        args.once.write_text(render(args.minutes), encoding="utf-8")
        print(f"Wrote {args.once}")
        return 0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = render(args.minutes).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    print(f"Dashboard: http://localhost:{args.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
