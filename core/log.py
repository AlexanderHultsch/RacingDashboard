import logging
import logging.handlers
import sys
from pathlib import Path

logger = logging.getLogger("racing-dashboard")
file_handler = None


def setup(log_cfg: dict) -> None:
    """Console and (if enabled) a rolling file. Safe to call once per process; a second call is ignored."""
    global file_handler
    if logger.handlers:
        return
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S"))
    logger.addHandler(console)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if log_cfg.get("enabled", True):
        Path(log_cfg["file"]).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_cfg["file"], maxBytes=int(log_cfg["max_mb"] * 1024 * 1024), backupCount=log_cfg["backups"], encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d | %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(file_handler)


def line(source: str, name: str, value="") -> None:
    logger.info(f"{source:<8} | {name:<18} | {value}")
