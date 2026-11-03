"""日志。"""
from __future__ import annotations

import logging


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name)
