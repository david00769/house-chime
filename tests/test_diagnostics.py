from __future__ import annotations

from types import SimpleNamespace
import unittest

from custom_components.house_chime.const import DOMAIN
from custom_components.house_chime.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.house_chime.models import (
    AnnouncementConfig,
    DoorGuardConfig,
)


class DiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostics_expose_door_guard_state_reason_and_expiry(
        self,
    ) -> None:
        config = AnnouncementConfig(
            door_guard=DoorGuardConfig("binary_sensor.front_door", 180),
        )
        hass = SimpleNamespace(
            data={
                DOMAIN: {
                    "entry-1": {
                        "config": config,
                        "last_resolution": None,
                        "status": {
                            "door_guard_sensor_state": "off",
                            "approach_suppression_active": True,
                            "approach_suppression_reason": (
                                "recent_front_door_activity"
                            ),
                            "approach_suppression_until": (
                                "2026-08-01T00:03:00+00:00"
                            ),
                            "door_guard_warning": None,
                        },
                    }
                }
            }
        )

        result = await async_get_config_entry_diagnostics(
            hass,
            SimpleNamespace(entry_id="entry-1"),
        )

        self.assertEqual(result["config_version"], 4)
        self.assertEqual(
            result["door_guard"],
            {
                "configured": True,
                "sensor_entity_id": "binary_sensor.front_door",
                "cooldown_seconds": 180,
                "sensor_state": "off",
                "suppression_active": True,
                "suppression_reason": "recent_front_door_activity",
                "suppression_until": "2026-08-01T00:03:00+00:00",
                "warning": None,
            },
        )
