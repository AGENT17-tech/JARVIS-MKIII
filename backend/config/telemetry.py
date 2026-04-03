"""
JARVIS-MKIII — config/telemetry.py
OpenTelemetry distributed tracing setup.

- Instruments FastAPI endpoints automatically
- Instruments httpx client calls
- Provides a module-level tracer for manual spans in the voice pipeline
- Exports spans to console (stdout) and an in-memory ring buffer
  readable via GET /telemetry/summary

Usage:
    from config.telemetry import setup_telemetry, get_tracer
    setup_telemetry(app)          # call once after app creation
    tracer = get_tracer("jarvis.voice")
    with tracer.start_as_current_span("stt_to_chat") as span:
        span.set_attribute("transcript.length", len(text))
        ...
"""
from __future__ import annotations
import collections
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# ── In-memory span ring buffer ─────────────────────────────────────────────────
_SPAN_BUFFER: collections.deque[dict] = collections.deque(maxlen=100)


class _BufferSpanExporter:
    """Captures finished spans into the in-memory ring buffer."""

    def export(self, spans) -> int:  # type: ignore[override]
        try:
            from opentelemetry.sdk.trace.export import SpanExportResult
        except ImportError:
            return 0
        for span in spans:
            try:
                dur_ns = span.end_time - span.start_time if span.end_time and span.start_time else 0
                _SPAN_BUFFER.append({
                    "name":        span.name,
                    "duration_ms": round(dur_ns / 1_000_000, 2),
                    "attributes":  dict(span.attributes or {}),
                    "status":      str(span.status.status_code.name) if span.status else "UNSET",
                    "timestamp":   time.time(),
                })
            except Exception:
                pass
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def setup_telemetry(app: "FastAPI") -> None:
    """Instrument FastAPI + httpx and register span exporters."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        logger.warning(
            "[TELEMETRY] opentelemetry packages not installed — tracing disabled. "
            "Run: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-httpx"
        )
        return

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    provider.add_span_processor(BatchSpanProcessor(_BufferSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    logger.info("[TELEMETRY] OpenTelemetry tracing active — FastAPI + httpx instrumented.")


def get_tracer(name: str = "jarvis"):
    """Return a tracer. Falls back to a no-op tracer if OTel not installed."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


def get_recent_spans(limit: int = 100) -> list[dict]:
    """Return the last `limit` recorded spans from the ring buffer."""
    spans = list(_SPAN_BUFFER)
    return spans[-limit:]


# ── No-op fallback tracer ─────────────────────────────────────────────────────

class _NoOpSpan:
    def set_attribute(self, key: str, value) -> None: pass
    def __enter__(self): return self
    def __exit__(self, *_): pass


class _NoOpTracer:
    def start_as_current_span(self, name: str, **_):
        return _NoOpSpan()
