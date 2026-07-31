"""Config flow for House Chime."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_ACTIVE_CONFIG, DEFAULT_EVENTS, DEFAULT_NAME, DOMAIN
from .discovery import (
    discover_device_trackers,
    discover_media_players,
    discover_people,
    is_selectable_announcement_player,
)
from .models import (
    AnnouncementConfig,
    ApproachDelayConfig,
    DoorGuardConfig,
    EventConfig,
    PersonConfig,
    QuietConfig,
    ResolverRuntime,
    ZoneConfig,
)
from .resolver import evaluate_door_guard, resolve_announcement
from .storage import migrate_config_dict

NONE_VALUE = "__none__"

EVENT_LABELS = {
    "front_door_approach": "Approach",
    "front_door_package": "Package",
    "front_door_doorbell": "Doorbell",
}

SETUP_MENU_OPTIONS = [
    "household",
    "announcements",
    "playback",
    "rules",
]


class HouseChimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for House Chime.

    V1 stores an empty operator config and relies on the options flow/service
    layer to populate discovered people, zones, events, voices, and quiet rules.
    """

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create the integration entry."""

        if user_input is not None:
            active_config, _ = migrate_config_dict(AnnouncementConfig().to_dict())
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_ACTIVE_CONFIG: active_config,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_NAME, default=DEFAULT_NAME): str}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""

        return HouseChimeOptionsFlow()


class HouseChimeOptionsFlow(config_entries.OptionsFlow):
    """Options flow for the operator-managed runtime config."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the configuration menu."""

        return self.async_show_menu(step_id="init", menu_options=SETUP_MENU_OPTIONS)

    async def async_step_playback(self, user_input: dict[str, Any] | None = None):
        """Group speaker selection and announcement-level configuration."""

        return self.async_show_menu(
            step_id="playback",
            menu_options=["zones", "volume", "zone_levels", "quiet"],
        )

    async def async_step_household(self, user_input: dict[str, Any] | None = None):
        """Group household presence and preference controls."""

        return self.async_show_menu(
            step_id="household",
            menu_options=["people", "priority", "preferences"],
        )

    async def async_step_announcements(self, user_input: dict[str, Any] | None = None):
        """Group event, audio, and personalisation controls."""

        return self.async_show_menu(
            step_id="announcements",
            menu_options=["events", "personalisation", "media"],
        )

    async def async_step_rules(self, user_input: dict[str, Any] | None = None):
        """Group suppression rules and non-audible diagnostics."""

        return self.async_show_menu(
            step_id="rules",
            menu_options=["door_guard", "review"],
        )

    async def async_step_people(self, user_input: dict[str, Any] | None = None):
        """Configure selected people."""

        config = self._config()
        discovered_people = discover_people(self.hass.states.async_all())
        people_options = _options(discovered_people)
        current_people_by_entity = {
            person.entity_id: person for person in config.people if person.entity_id
        }
        selected_people = [
            person.entity_id for person in config.people if person.in_scope and person.entity_id
        ]
        if user_input is not None:
            selected = list(user_input.get("selected_people", []))
            people = []
            for entity_id in selected:
                record = next((item for item in discovered_people if item.entity_id == entity_id), None)
                person_id = _id_from_entity(entity_id)
                existing = current_people_by_entity.get(entity_id)
                people.append(
                    PersonConfig(
                        id=person_id,
                        name=record.name if record else person_id,
                        entity_id=entity_id,
                        fallback_tracker_entity_ids=existing.fallback_tracker_entity_ids if existing else [],
                        in_scope=True,
                        default_voice_id=existing.default_voice_id if existing else None,
                        custom_voice_profile=existing.custom_voice_profile if existing else None,
                        playback_enabled_when_home=(
                            existing.playback_enabled_when_home if existing else True
                        ),
                    )
                )
            config.people = people
            selected_ids = [_id_from_entity(entity_id) for entity_id in selected]
            config.person_priority = [item for item in config.person_priority if item in selected_ids]
            config.person_priority.extend(item for item in selected_ids if item not in config.person_priority)
            if config.default_context_id not in selected_ids:
                config.default_context_id = None
            return self._save(config)

        return self.async_show_form(
            step_id="people",
            data_schema=vol.Schema(
                {
                    vol.Optional("selected_people", default=selected_people): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=people_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={
                "person_count": str(len(discovered_people)),
            },
        )

    async def async_step_preferences(self, user_input: dict[str, Any] | None = None):
        """Choose the person whose at-home preferences will be edited."""

        config = self._config()
        if user_input is not None:
            self._preference_person_id = user_input["person_id"]
            return await self.async_step_person_preference()
        return self.async_show_form(
            step_id="preferences",
            data_schema=vol.Schema(
                {
                    vol.Required("person_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=_person_options(config))
                    )
                }
            ),
        )

    async def async_step_person_preference(self, user_input: dict[str, Any] | None = None):
        """Edit one discovered person's playback preference and presence fallbacks."""

        config = self._config()
        person = _person_by_id(config, getattr(self, "_preference_person_id", None))
        if person is None:
            return await self.async_step_preferences()
        tracker_options = _options(
            discover_device_trackers(self.hass.states.async_all()), include_entity_id=True
        )
        if user_input is not None:
            person.playback_enabled_when_home = bool(user_input["playback_enabled_when_home"])
            person.fallback_tracker_entity_ids = _list_value(
                user_input.get("fallback_tracker_entity_ids")
            )
            return self._save(config)
        return self.async_show_form(
            step_id="person_preference",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "playback_enabled_when_home",
                        default=person.playback_enabled_when_home,
                    ): bool,
                    vol.Optional(
                        "fallback_tracker_entity_ids",
                        default=list(person.fallback_tracker_entity_ids),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=tracker_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={"person_name": person.name},
        )

    async def async_step_personalisation(self, user_input: dict[str, Any] | None = None):
        """Choose a person and event to personalise without numbered form fields."""

        config = self._config()
        if user_input is not None:
            self._personalisation_person_id = user_input["person_id"]
            self._personalisation_event_id = user_input["event_id"]
            return await self.async_step_personalisation_detail()
        event_options = [
            selector.SelectOptionDict(value=event_id, label=_event_label(event_id))
            for event_id in DEFAULT_EVENTS
        ]
        return self.async_show_form(
            step_id="personalisation",
            data_schema=vol.Schema(
                {
                    vol.Required("person_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=_person_options(config))
                    ),
                    vol.Required("event_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=event_options)
                    ),
                }
            ),
        )

    async def async_step_personalisation_detail(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit the selected person's voice and optional pre-sound for one event."""

        config = self._config()
        person = _person_by_id(config, getattr(self, "_personalisation_person_id", None))
        event_id = getattr(self, "_personalisation_event_id", None)
        event = next((item for item in config.events if item.id == event_id), None)
        if person is None or event is None:
            return await self.async_step_personalisation()
        if user_input is not None:
            voice_id = user_input.get("voice_id")
            if voice_id and voice_id != NONE_VALUE:
                event.voice_by_context[person.id] = voice_id
            else:
                event.voice_by_context.pop(person.id, None)
            trigger_sound = _media_value(user_input.get("trigger_sound"))
            if trigger_sound:
                event.trigger_sound_by_context[person.id] = trigger_sound
            else:
                event.trigger_sound_by_context.pop(person.id, None)
            return self._save(config)
        return self.async_show_form(
            step_id="personalisation_detail",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "voice_id",
                        default=event.voice_by_context.get(person.id, NONE_VALUE),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=NONE_VALUE, label="Use event default voice"
                                )
                            ]
                            + _voice_options(config)
                        )
                    ),
                    vol.Optional(
                        "trigger_sound",
                        default=_media_selector_default(
                            event.trigger_sound_by_context.get(person.id)
                        ),
                    ): _media_selector(),
                }
            ),
            description_placeholders={
                "person_name": person.name,
                "event_name": _event_label(event.id),
            },
        )

    async def async_step_priority(self, user_input: dict[str, Any] | None = None):
        """Configure active-context priority."""

        config = self._config()
        person_options = _person_options(config)
        fallback_options = [selector.SelectOptionDict(value=NONE_VALUE, label="None")]
        fallback_options.extend(person_options)

        if user_input is not None:
            ranked = [
                person_id
                for person_id in user_input.get("priority_people", [])
                if person_id in {person.id for person in config.people}
            ]
            ranked = list(dict.fromkeys(ranked))
            ranked.extend(person.id for person in config.people if person.id not in ranked)
            config.person_priority = ranked
            default_context_id = user_input.get("default_context_id")
            config.default_context_id = None if default_context_id == NONE_VALUE else default_context_id
            return self._save(config)

        fields = {
            vol.Optional(
                "priority_people",
                default=[
                    person_id
                    for person_id in config.person_priority
                    if person_id in {person.id for person in config.people}
                ],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=person_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "default_context_id",
                default=config.default_context_id or NONE_VALUE,
            ): selector.SelectSelector(selector.SelectSelectorConfig(options=fallback_options)),
        }

        return self.async_show_form(
            step_id="priority",
            data_schema=vol.Schema(fields),
        )

    async def async_step_zones(self, user_input: dict[str, Any] | None = None):
        """Configure selected playback zones (available Music Assistant targets)."""

        config = self._config()
        discovered_zones = discover_media_players(self.hass.states.async_all())
        selectable_zones = _selectable_announcement_zones(discovered_zones)
        selectable_zone_ids = {zone.entity_id for zone in selectable_zones}
        available_selected = [
            zone.entity_id
            for zone in config.zones
            if zone.selected and zone.entity_id in selectable_zone_ids
        ]
        zone_options = _options(selectable_zones, include_entity_id=True)
        zones_by_entity = {zone.entity_id: zone for zone in config.zones}

        if user_input is not None:
            selected = set(user_input.get("selected_zones", [])) & selectable_zone_ids
            config.zones = [
                ZoneConfig(
                    entity_id=item.entity_id,
                    name=item.name,
                    selected=item.entity_id in selected,
                    quiet_excluded=zones_by_entity.get(
                        item.entity_id,
                        ZoneConfig(item.entity_id),
                    ).quiet_excluded,
                    volume_multiplier=zones_by_entity.get(
                        item.entity_id,
                        ZoneConfig(item.entity_id),
                    ).volume_multiplier,
                )
                for item in selectable_zones
            ]
            return self._save(config)

        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "selected_zones",
                        default=available_selected,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=zone_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={
                "recommended_count": str(len(selectable_zones)),
                "total_count": str(len(discovered_zones)),
                **_speaker_drift_placeholders(config, selectable_zones),
            },
        )

    async def async_step_zones_all(self, user_input: dict[str, Any] | None = None):
        """Compatibility alias for older options links."""

        return await self.async_step_zones(user_input)

    async def async_step_volume(self, user_input: dict[str, Any] | None = None):
        """Configure the global announcement level used outside quiet hours."""

        config = self._config()
        if user_input is not None:
            config.normal_volume = float(user_input["normal_volume"])
            return self._save(config)

        return self.async_show_form(
            step_id="volume",
            data_schema=vol.Schema(
                {
                    vol.Required("normal_volume", default=config.normal_volume): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=1.0,
                            step=0.05,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    )
                }
            ),
            description_placeholders={
                "quiet_preview": _volume_preview(config.normal_volume, config.quiet.volume_multiplier),
            },
        )

    async def async_step_zone_levels(self, user_input: dict[str, Any] | None = None):
        """Choose a selected announcement target whose level should be adjusted."""

        config = self._config()
        selected_zones = [zone for zone in config.zones if zone.selected]
        if user_input is not None:
            self._zone_level_entity_id = user_input["entity_id"]
            return await self.async_step_zone_level_detail()
        return self.async_show_form(
            step_id="zone_levels",
            data_schema=vol.Schema(
                {
                    vol.Required("entity_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_options(selected_zones, include_entity_id=True),
                        )
                    )
                }
            ),
            description_placeholders={"selected_count": str(len(selected_zones))},
        )

    async def async_step_zone_level_detail(
        self, user_input: dict[str, Any] | None = None
    ):
        """Set one target's relative announcement level."""

        config = self._config()
        entity_id = getattr(self, "_zone_level_entity_id", None)
        zone = next(
            (item for item in config.zones if item.entity_id == entity_id and item.selected),
            None,
        )
        if zone is None:
            return await self.async_step_zone_levels()
        if user_input is not None:
            zone.volume_multiplier = float(user_input["volume_multiplier"])
            return self._save(config)
        return self.async_show_form(
            step_id="zone_level_detail",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "volume_multiplier",
                        default=zone.volume_multiplier,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=1.0,
                            step=0.05,
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    )
                }
            ),
            description_placeholders={
                "zone_name": zone.name or zone.entity_id,
                "day_preview": _percentage(config.normal_volume * zone.volume_multiplier),
                "quiet_preview": _percentage(
                    config.normal_volume
                    * config.quiet.volume_multiplier
                    * zone.volume_multiplier
                ),
            },
        )

    async def async_step_quiet(self, user_input: dict[str, Any] | None = None):
        """Configure quiet hours."""

        config = self._config()
        quiet = config.quiet
        discovered_zones = discover_media_players(self.hass.states.async_all())
        selectable_zones = _selectable_announcement_zones(discovered_zones)
        selectable_zone_ids = {zone.entity_id for zone in selectable_zones}
        zone_options = _options(selectable_zones, include_entity_id=True)

        if user_input is not None:
            config.quiet = QuietConfig(
                enabled=bool(user_input["enabled"]),
                start=user_input["start"],
                end=user_input["end"],
                volume_multiplier=float(user_input["volume_multiplier"]),
                excluded_zone_entity_ids=[
                    entity_id
                    for entity_id in user_input.get("quiet_excluded_zones", [])
                    if entity_id in selectable_zone_ids
                ],
                zone_start=user_input.get("zone_start") or None,
                zone_end=user_input.get("zone_end") or None,
            )
            for zone in config.zones:
                zone.quiet_excluded = zone.entity_id in config.quiet.excluded_zone_entity_ids
            return self._save(config)

        return self.async_show_form(
            step_id="quiet",
            data_schema=vol.Schema(
                {
                    vol.Optional("enabled", default=quiet.enabled): bool,
                    vol.Optional("start", default=quiet.start): str,
                    vol.Optional("end", default=quiet.end): str,
                    vol.Optional(
                        "volume_multiplier",
                        default=quiet.volume_multiplier,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
                    vol.Optional(
                        "quiet_excluded_zones",
                        default=[
                            entity_id
                            for entity_id in quiet.excluded_zone_entity_ids
                            if entity_id in selectable_zone_ids
                        ],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=zone_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional("zone_start", default=quiet.zone_start or ""): str,
                    vol.Optional("zone_end", default=quiet.zone_end or ""): str,
                }
            ),
            description_placeholders={
                "effective_preview": _volume_preview(
                    config.normal_volume,
                    quiet.volume_multiplier,
                ),
            },
        )

    async def async_step_events(self, user_input: dict[str, Any] | None = None):
        """Choose one event to configure."""

        return self.async_show_menu(
            step_id="events",
            menu_options=[f"event_{event_id}" for event_id in DEFAULT_EVENTS],
        )

    async def async_step_event_front_door_approach(self, user_input: dict[str, Any] | None = None):
        """Configure approach event."""

        return await self._async_step_event_config("front_door_approach", user_input)

    async def async_step_event_front_door_package(self, user_input: dict[str, Any] | None = None):
        """Configure package event."""

        return await self._async_step_event_config("front_door_package", user_input)

    async def async_step_event_front_door_doorbell(self, user_input: dict[str, Any] | None = None):
        """Configure doorbell event."""

        return await self._async_step_event_config("front_door_doorbell", user_input)

    async def _async_step_event_config(self, event_id: str, user_input: dict[str, Any] | None = None):
        """Configure one event's shared default settings."""

        config = self._config()
        events_by_id = {event.id: event for event in config.events}
        voice_options = _voice_options(config)
        event = events_by_id[event_id]
        step_id = f"event_{event_id}"

        if user_input is not None:
            config.events = [
                EventConfig(
                    id=existing.id,
                    name=existing.name,
                    enabled=bool(user_input["enabled"]),
                    voice_by_context=dict(existing.voice_by_context),
                    default_voice_id=user_input.get("default_voice_id"),
                    common_trigger_sound=_media_value(user_input.get("common_trigger_sound")),
                    trigger_sound_by_context=dict(existing.trigger_sound_by_context),
                    duplicate_window_seconds=int(
                        user_input.get(
                            "duplicate_window_seconds",
                            existing.duplicate_window_seconds,
                        )
                    ),
                )
                if existing.id == event_id
                else existing
                for existing in config.events
            ]
            return self._save(config)

        fields = {
            vol.Optional("enabled", default=event.enabled): bool,
            vol.Optional(
                "default_voice_id",
                default=event.default_voice_id or "samantha",
            ): selector.SelectSelector(selector.SelectSelectorConfig(options=voice_options)),
            vol.Optional(
                "common_trigger_sound",
                default=_media_selector_default(event.common_trigger_sound),
            ): _media_selector(),
            vol.Optional(
                "duplicate_window_seconds",
                default=event.duplicate_window_seconds,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=3600,
                    step=5,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(fields),
            description_placeholders={"event_name": _event_label(event_id)},
        )

    async def async_step_media(self, user_input: dict[str, Any] | None = None):
        """Choose one event whose voice media should be configured."""

        if user_input is not None:
            self._media_event_id = user_input["event_id"]
            return await self.async_step_event_media()
        return self.async_show_form(
            step_id="media",
            data_schema=vol.Schema(
                {
                    vol.Required("event_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=event_id,
                                    label=_event_label(event_id),
                                )
                                for event_id in DEFAULT_EVENTS
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_event_media(self, user_input: dict[str, Any] | None = None):
        """Configure every approved voice file for one event."""

        config = self._config()
        event_id = getattr(self, "_media_event_id", None)
        if event_id not in DEFAULT_EVENTS:
            return await self.async_step_media()
        if user_input is not None:
            for voice in config.voices:
                field = _media_field(voice.id, event_id)
                value = _media_value(user_input.get(field))
                if value:
                    voice.media_by_event[event_id] = value
                else:
                    voice.media_by_event.pop(event_id, None)
            return self._save(config)
        fields = {
            vol.Optional(
                _media_field(voice.id, event_id),
                default=_media_selector_default(voice.media_by_event.get(event_id)),
            ): _media_selector()
            for voice in config.voices
        }
        return self.async_show_form(
            step_id="event_media",
            data_schema=vol.Schema(fields),
            description_placeholders={"event_name": _event_label(event_id)},
        )

    async def async_step_voice_media(self, user_input: dict[str, Any] | None = None):
        """Compatibility alias for older options links/tests."""

        return await self.async_step_media(user_input)

    async def async_step_additional(self, user_input: dict[str, Any] | None = None):
        """Compatibility alias for removed advanced-settings links."""

        return await self.async_step_events()

    async def async_step_door_guard(self, user_input: dict[str, Any] | None = None):
        """Configure Approach timing and suppression."""

        config = self._config()
        if user_input is not None:
            config.approach_delay = ApproachDelayConfig(
                sensor_entity_id=user_input.get("approach_sensor_entity_id") or None,
                delay_seconds=int(user_input["approach_delay_seconds"]),
            )
            config.door_guard = DoorGuardConfig(
                sensor_entity_id=user_input.get("door_sensor_entity_id") or None,
                cooldown_seconds=int(user_input["after_door_quiet_seconds"]),
            )
            return self._save(config)

        approach_sensor_field = vol.Optional("approach_sensor_entity_id")
        if config.approach_delay.sensor_entity_id:
            approach_sensor_field = vol.Optional(
                "approach_sensor_entity_id",
                default=config.approach_delay.sensor_entity_id,
            )
        door_sensor_field = vol.Optional("door_sensor_entity_id")
        if config.door_guard.sensor_entity_id:
            door_sensor_field = vol.Optional(
                "door_sensor_entity_id",
                default=config.door_guard.sensor_entity_id,
            )
        fields = {
            approach_sensor_field: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(
                "approach_delay_seconds",
                default=config.approach_delay.delay_seconds,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=300,
                    step=5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="seconds",
                )
            ),
            door_sensor_field: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(
                "after_door_quiet_seconds",
                default=config.door_guard.cooldown_seconds,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=3600,
                    step=10,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="seconds",
                )
            ),
        }
        return self.async_show_form(
            step_id="door_guard",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "behavior_preview": (
                    f"Person detected → wait "
                    f"{_human_duration(config.approach_delay.delay_seconds)} → announce. "
                    "Cancel if the person leaves, the front door opens, or a Doorbell "
                    f"event arrives. After the door opens or a Doorbell arrives, ignore "
                    "new Approach detections "
                    f"for {_human_duration(config.door_guard.cooldown_seconds)}."
                ),
            },
        )

    async def async_step_review(self, user_input: dict[str, Any] | None = None):
        """Show a non-audible setup review."""

        config = self._config()
        if user_input is not None:
            return self._save(config)

        states = {state.entity_id: state.state for state in self.hass.states.async_all()}
        door_reason, door_until, door_warning = evaluate_door_guard(
            config,
            ResolverRuntime(
                states=states,
                door_suppression_until=self._door_suppression_until(),
            ),
        )
        summaries = []
        for event_id in DEFAULT_EVENTS:
            resolution = resolve_announcement(
                config,
                event_id,
                ResolverRuntime(
                    states=states,
                    available_media=None,
                    door_suppression_until=self._door_suppression_until(),
                ),
            )
            status = (
                "suppressed"
                if resolution.suppressed
                else "ready"
                if resolution.ok
                else "needs setup"
            )
            detail = ", ".join(
                resolution.errors
                or ([resolution.suppression_reason] if resolution.suppression_reason else [])
                or resolution.warnings
                or ["ok"]
            )
            summaries.append(f"{_event_label(event_id)}: {status} ({detail})")
        services = getattr(self.hass, "services", None)
        has_music_assistant = True
        if services is not None and hasattr(services, "has_service"):
            has_music_assistant = services.has_service("music_assistant", "play_announcement")
        service_summary = (
            "Music Assistant announcement service is available."
            if has_music_assistant
            else "Music Assistant announcement service was not found."
        )
        sensor_entity_id = config.door_guard.sensor_entity_id
        if not sensor_entity_id:
            door_summary = "Door-aware approach suppression is not configured."
        else:
            sensor_state = states.get(sensor_entity_id, "missing")
            door_summary = (
                f"{sensor_entity_id}: {sensor_state}; "
                + (
                    f"active ({door_reason})"
                    if door_reason
                    else "not currently suppressing"
                )
                + (f"; until {door_until}" if door_until else "")
                + (f"; warning {door_warning}" if door_warning else "")
            )
        approach_sensor_entity_id = config.approach_delay.sensor_entity_id
        if not approach_sensor_entity_id:
            approach_delay_summary = (
                "Delayed source Approach is disabled until a person-presence sensor "
                "is selected. Play now remains immediate for manual testing."
            )
        else:
            approach_sensor_state = states.get(approach_sensor_entity_id, "missing")
            approach_delay_summary = (
                f"{approach_sensor_entity_id}: {approach_sensor_state}; "
                f"continuous detection required for "
                f"{_human_duration(config.approach_delay.delay_seconds)}"
            )
            current_wait_until = self._approach_wait_until()
            if current_wait_until:
                approach_delay_summary += f"; waiting until {current_wait_until}"
        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema({}),
            description_placeholders={
                "summary": "\n".join(summaries),
                "music_assistant": service_summary,
                "approach_delay": approach_delay_summary,
                "door_guard": door_summary,
            },
        )

    def _config(self) -> AnnouncementConfig:
        current_config = self.config_entry.options.get(CONF_ACTIVE_CONFIG) or self.config_entry.data.get(
            CONF_ACTIVE_CONFIG
        )
        migrated, _ = migrate_config_dict(current_config)
        return AnnouncementConfig.from_dict(migrated)

    def _save(self, config: AnnouncementConfig):
        migrated, _ = migrate_config_dict(config.to_dict())
        return self.async_create_entry(title="", data={CONF_ACTIVE_CONFIG: migrated})

    def _door_suppression_until(self) -> str | None:
        """Return the current entry's in-memory deadline when options are live."""

        entry_id = getattr(self.config_entry, "entry_id", None)
        domain_data = getattr(self.hass, "data", {}).get(DOMAIN, {})
        return (domain_data.get(entry_id) or {}).get("door_suppression_until")

    def _approach_wait_until(self) -> str | None:
        """Return the current delayed-Approach deadline when options are live."""

        entry_id = getattr(self.config_entry, "entry_id", None)
        domain_data = getattr(self.hass, "data", {}).get(DOMAIN, {})
        return (domain_data.get(entry_id) or {}).get("approach_wait_until")


def _options(records, *, include_entity_id: bool = False) -> list[selector.SelectOptionDict]:
    name_counts: dict[str, int] = {}
    for record in records:
        name_counts[record.name] = name_counts.get(record.name, 0) + 1

    options: list[selector.SelectOptionDict] = []
    for record in records:
        label = record.name
        if include_entity_id or name_counts.get(record.name, 0) > 1:
            label = f"{record.name} ({record.entity_id})"
        options.append(selector.SelectOptionDict(value=record.entity_id, label=label))
    return options


def _human_duration(seconds: int) -> str:
    """Return concise operator copy for a duration stored in seconds."""

    if seconds == 0:
        return "no delay"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{seconds} seconds"


def _selectable_announcement_zones(records) -> list:
    return [record for record in records if is_selectable_announcement_player(record)]


def _speaker_drift_placeholders(config: AnnouncementConfig, discovered_zones) -> dict[str, str]:
    missing = _missing_selected_zones(config, discovered_zones)
    if not missing:
        return {
            "missing_selected_zones": "None.",
            "suggested_replacements": "None.",
        }

    return {
        "missing_selected_zones": "\n".join(
            _zone_label(zone.entity_id, zone.name) for zone in missing
        ),
        "suggested_replacements": "\n".join(
            _replacement_summary(zone, discovered_zones) for zone in missing
        ),
    }


def _missing_selected_zones(config: AnnouncementConfig, discovered_zones) -> list[ZoneConfig]:
    discovered_zone_ids = {zone.entity_id for zone in discovered_zones}
    return [
        zone
        for zone in config.zones
        if zone.selected and zone.entity_id not in discovered_zone_ids
    ]


def _replacement_summary(missing_zone: ZoneConfig, discovered_zones) -> str:
    candidates = _suggest_replacement_zones(missing_zone, discovered_zones)
    if not candidates:
        return f"{_zone_label(missing_zone.entity_id, missing_zone.name)} -> no close match found"
    return (
        f"{_zone_label(missing_zone.entity_id, missing_zone.name)} -> "
        + ", ".join(_zone_label(zone.entity_id, zone.name) for zone in candidates)
    )


def _suggest_replacement_zones(missing_zone: ZoneConfig, discovered_zones, limit: int = 3):
    missing_name = _normalise_zone_name(missing_zone.name or _id_from_entity(missing_zone.entity_id))
    missing_entity_name = _normalise_zone_name(_id_from_entity(missing_zone.entity_id))
    scored = []
    for zone in discovered_zones:
        zone_name = _normalise_zone_name(zone.name)
        zone_entity_name = _normalise_zone_name(_id_from_entity(zone.entity_id))
        score = 0
        if missing_name and zone_name == missing_name:
            score = 3
        elif missing_entity_name and zone_entity_name == missing_entity_name:
            score = 2
        elif missing_name and (
            missing_name in zone_name
            or zone_name in missing_name
            or missing_entity_name in zone_name
        ):
            score = 1
        if score:
            scored.append((score, zone.entity_id, zone))
    return [zone for _, _, zone in sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]]


def _normalise_zone_name(value: str | None) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").lower().split())


def _zone_label(entity_id: str, name: str | None) -> str:
    label = name or entity_id
    return f"{label} ({entity_id})"


def _voice_options(config: AnnouncementConfig) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=voice.id, label=voice.name)
        for voice in config.voices
    ]


def _person_options(config: AnnouncementConfig) -> list[selector.SelectOptionDict]:
    """Return current household people without encoding names in the form schema."""

    return [
        selector.SelectOptionDict(value=person.id, label=person.name)
        for person in config.people
        if person.in_scope
    ]


def _person_by_id(config: AnnouncementConfig, person_id: str | None) -> PersonConfig | None:
    return next((person for person in config.people if person.id == person_id), None)


def _id_from_entity(entity_id: str) -> str:
    return entity_id.split(".", 1)[-1]


def _media_field(voice_id: str, event_id: str) -> str:
    return f"{voice_id}_{event_id}_media_path"


def _event_label(event_id: str) -> str:
    return EVENT_LABELS.get(event_id, event_id.replace("_", " ").title())


def _percentage(value: float) -> str:
    """Format a clamped Home Assistant volume as an operator-readable percentage."""

    return f"{round(max(0.0, min(1.0, value)) * 100)}%"


def _volume_preview(normal_volume: float, quiet_multiplier: float) -> str:
    """Describe the saved daytime and quiet-time output levels."""

    return f"Daytime {_percentage(normal_volume)}; quiet {_percentage(normal_volume * quiet_multiplier)}."


def _media_selector():
    config_cls = getattr(selector, "MediaSelectorConfig", None)
    selector_cls = getattr(selector, "MediaSelector", None)
    if config_cls and selector_cls:
        return selector_cls(config_cls(accept=["audio/*"]))
    return str


def _media_selector_default(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    return {"media_content_id": value, "media_content_type": "audio/mpeg"}


def _media_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("media_content_id") or "")
    return str(value or "")


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [value] if value else []
    return list(value)
