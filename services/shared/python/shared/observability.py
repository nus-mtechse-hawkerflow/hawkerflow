"""Structured logging and correlation helpers for asynchronous workflows."""
import json
import logging
import sys
import uuid


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in ("correlationId", "orderId", "event", "service"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(service: str) -> logging.Logger:
    logger = logging.getLogger(service)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def correlation_id(event: dict) -> str:
    context = event.get("requestContext", {})
    return (
        event.get("correlationId")
        or context.get("requestId")
        or context.get("http", {}).get("requestId")
        or str(uuid.uuid4())
    )


def log_extra(correlation: str, **values) -> dict:
    return {"extra": {"correlationId": correlation, **values}}
