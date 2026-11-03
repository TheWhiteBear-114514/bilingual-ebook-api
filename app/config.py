"""兼容入口：等同于 config.config_unified。"""
from config.config_unified import ROOT, Settings, settings  # noqa: F401

__all__ = ["ROOT", "Settings", "settings"]
