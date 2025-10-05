"""
Helios Trading System V3.0 - Logging System
Component-based structured logging with JSON support
"""

import logging
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add component if available
        if hasattr(record, "component"):
            log_data["component"] = record.component

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ComponentLogger(logging.LoggerAdapter):
    """Logger adapter that adds component information to logs"""

    def __init__(self, logger: logging.Logger, component: str):
        super().__init__(logger, {"component": component})
        self.component = component

    def process(self, msg, kwargs):
        # Add component to extra
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"]["component"] = self.component
        return msg, kwargs

    def with_fields(self, **fields):
        """Add extra fields to a single log message"""

        class FieldLogger:
            def __init__(self, logger, fields):
                self.logger = logger
                self.fields = fields

            def debug(self, msg):
                self.logger.debug(msg, extra={"extra_fields": self.fields})

            def info(self, msg):
                self.logger.info(msg, extra={"extra_fields": self.fields})

            def warning(self, msg):
                self.logger.warning(msg, extra={"extra_fields": self.fields})

            def error(self, msg, exc_info=False):
                self.logger.error(msg, extra={"extra_fields": self.fields}, exc_info=exc_info)

            def critical(self, msg, exc_info=False):
                self.logger.critical(msg, extra={"extra_fields": self.fields}, exc_info=exc_info)

        return FieldLogger(self, fields)


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_dir: str = "logs",
    rotation_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 30,
) -> None:
    """
    Setup application-wide logging configuration

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format ('json' or 'text')
        log_dir: Directory for log files
        rotation_size: Max size of each log file in bytes
        backup_count: Number of backup log files to keep
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    if log_format == "json":
        console_formatter = StructuredFormatter()
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path / "helios.log",
        maxBytes=rotation_size,
        backupCount=backup_count,
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))

    if log_format == "json":
        file_formatter = StructuredFormatter()
    else:
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(component)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Component-specific log files
    components = [
        "tier1_data",
        "tier2_ml",
        "tier3_risk",
        "tier4_llm",
        "tier5_portfolio",
        "trading_orchestrator",
        "websocket",
        "api",
    ]

    for component in components:
        component_handler = RotatingFileHandler(
            log_path / f"{component}.log",
            maxBytes=rotation_size,
            backupCount=backup_count,
        )
        component_handler.setLevel(getattr(logging, log_level.upper()))
        component_handler.setFormatter(
            StructuredFormatter() if log_format == "json" else file_formatter
        )

        # Add filter to only log messages from this component
        component_handler.addFilter(lambda record, c=component: getattr(record, "component", "") == c)
        root_logger.addHandler(component_handler)


def get_logger(name: str, component: Optional[str] = None) -> ComponentLogger:
    """
    Get a logger instance with component information

    Args:
        name: Logger name (typically __name__)
        component: Component name (e.g., 'tier1_data', 'tier2_ml')

    Returns:
        ComponentLogger instance
    """
    logger = logging.getLogger(name)

    if component:
        return ComponentLogger(logger, component)

    # Infer component from module name
    if "tier1" in name or "data" in name:
        inferred_component = "tier1_data"
    elif "tier2" in name or "ml" in name:
        inferred_component = "tier2_ml"
    elif "tier3" in name or "risk" in name:
        inferred_component = "tier3_risk"
    elif "tier4" in name or "llm" in name:
        inferred_component = "tier4_llm"
    elif "tier5" in name or "portfolio" in name:
        inferred_component = "tier5_portfolio"
    elif "orchestrator" in name:
        inferred_component = "trading_orchestrator"
    elif "websocket" in name:
        inferred_component = "websocket"
    elif "api" in name or "router" in name:
        inferred_component = "api"
    else:
        inferred_component = "general"

    return ComponentLogger(logger, inferred_component)


# Convenience function for performance logging
def log_performance(logger: ComponentLogger, operation: str, duration_ms: float, **kwargs):
    """Log performance metrics"""
    logger.with_fields(
        operation=operation,
        duration_ms=duration_ms,
        **kwargs,
    ).info(f"Performance: {operation} took {duration_ms:.2f}ms")


# Convenience function for error logging with context
def log_error_with_context(
    logger: ComponentLogger,
    error: Exception,
    context: Dict[str, Any],
    message: str = "Error occurred",
):
    """Log error with full context"""
    logger.with_fields(
        error_type=type(error).__name__,
        error_message=str(error),
        **context,
    ).error(message, exc_info=True)
