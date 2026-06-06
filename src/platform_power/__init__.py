"""OS power-management helpers for keeping the machine awake during runs."""

from src.platform_power.sleep_inhibitor import (
    allow_sleep,
    prevent_sleep,
    sleep_prevented,
)

__all__ = ["allow_sleep", "prevent_sleep", "sleep_prevented"]
