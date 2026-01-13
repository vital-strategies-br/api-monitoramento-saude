import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[logging.StreamHandler(sys.stdout)],
    )
