"""Real Home Assistant lifecycle coverage for delayed Approach listeners."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.house_chime.const import CONF_ACTIVE_CONFIG, DOMAIN
from custom_components.house_chime.models import (
    AnnouncementConfig,
    ApproachDelayConfig,
    DoorGuardConfig,
    EventConfig,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entry_tracks_sensor_timer_and_unloads(hass) -> None:
    """A real tracked-state event starts one cancellable Home Assistant timer."""

    config = AnnouncementConfig(
        approach_delay=ApproachDelayConfig("binary_sensor.front_door_person", 30),
        door_guard=DoorGuardConfig("binary_sensor.front_door", 180),
        events=[EventConfig(id="front_door_approach", name="Approach")],
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="House Chime",
        data={CONF_ACTIVE_CONFIG: config.to_dict()},
        entry_id="entry-1",
    )
    entry.add_to_hass(hass)
    hass.states.async_set("binary_sensor.front_door_person", "off")
    hass.states.async_set("binary_sensor.front_door", "off")

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data is hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set("binary_sensor.front_door_person", "on")
    await hass.async_block_till_done()
    deadline = entry.runtime_data["approach_wait_until"]
    assert deadline is not None

    with patch(
        "custom_components.house_chime._complete_approach_wait",
        new=AsyncMock(),
    ) as complete:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
        await hass.async_block_till_done()
        complete.assert_awaited_once_with(hass, entry.entry_id, deadline)

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(return_value=True),
    ):
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
