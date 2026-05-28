"""Logging configuration"""

import logging
import os
import sys
import json
from datetime import datetime
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Setup structured logging.

    When LOG_FILE is set, writes JSON logs to that path in addition to stdout.
    Defaults to logs/run.log when running locally (outside Lambda).
    Set LOG_FILE=none to disable file logging entirely.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = JSONFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    log_file = os.getenv("LOG_FILE")

    # Default to logs/run.log locally; Lambda sets AWS_LAMBDA_FUNCTION_NAME
    if log_file is None and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        log_file = "logs/run.log"

    if log_file and log_file.lower() != "none":
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger
