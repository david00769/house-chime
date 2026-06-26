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
    discover_helpers,
    discover_media_players,
    discover_people,
    is_recommended_media_player,
)
from .models import (
    AnnouncementConfig,
    EventConfig,
    PersonConfig,
    QuietConfig,
    ResolverRuntime,
    VoicePersonality,
    ZoneConfig,
)
from .resolver import resolve_announcement
from .storage import migrate_config_dict

NONE_VALUE = "__none__"

EVENT_LABELS = {
    "front_door_approach": "Approach",
    "front_door_package": "Package",
    "front_door_doorbell": "Doorbell",
}

PRIORITY_FIELDS = ("priority_1", "priority_2", "priority_3", "priority_4", "priority_5")

SETUP_MENU_OPTIONS = [
    "people",
    "priority",
    "zones",
    "zones_all",
    "media",
    "events",
    "quiet",
    "advanced",
    "review",
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

    async def async_step_priority(self, user_input: dict[str, Any] | None = None):
        """Configure active-context priority."""

        config = self._config()
        person_options = [selector.SelectOptionDict(value=NONE_VALUE, label="None")]
        person_options.extend(
            selector.SelectOptionDict(value=person.id, label=person.name)
            for person in config.people
        )

        if user_input is not None:
            ranked = []
            for field in PRIORITY_FIELDS:
                person_id = user_input.get(field)
                if person_id and person_id != NONE_VALUE and person_id not in ranked:
                    ranked.append(person_id)
            ranked.extend(person.id for person in config.people if person.id not in ranked)
            config.person_priority = ranked
            default_context_id = user_input.get("default_context_id")
            config.default_context_id = None if default_context_id == NONE_VALUE else default_context_id
            return self._save(config)

        fields = {
            vol.Optional(
                field,
                default=(config.person_priority[index] if index < len(config.person_priority) else NONE_VALUE),
            ): selector.SelectSelector(selector.SelectSelectorConfig(options=person_options))
            for index, field in enumerate(PRIORITY_FIELDS[: max(1, min(len(config.people), len(PRIORITY_FIELDS)))])
        }
        fields[
            vol.Optional(
                "default_context_id",
                default=config.default_context_id or NONE_VALUE,
            )
        ] = selector.SelectSelector(selector.SelectSelectorConfig(options=person_options))

        return self.async_show_form(
            step_id="priority",
            data_schema=vol.Schema(fields),
        )

    async def async_step_zones(self, user_input: dict[str, Any] | None = None):
        """Configure selected playback zones (Juke/Music Assistant recommended list)."""

        config = self._config()
        discovered_zones = discover_media_players(self.hass.states.async_all())
        current_selected = {zone.entity_id for zone in config.zones if zone.selected}
        discovered_zone_ids = {zone.entity_id for zone in discovered_zones}
        available_selected = [
            zone.entity_id
            for zone in config.zones
            if zone.selected and zone.entity_id in discovered_zone_ids
        ]
        recommended_zones = [
            zone
            for zone in discovered_zones
            if is_recommended_media_player(zone) or zone.entity_id in current_selected
        ]
        # The default Speakers picker intentionally focuses on Music Assistant/Juke
        # targets to avoid confusing users with unrelated media_player entities
        # (TVs, receivers, stale AirPlay bridges, etc.).
        #
        # We still include any *currently selected* non-recommended entities so a
        # user's saved configuration does not silently disappear from the UI.
        zone_options = _options(recommended_zones, include_entity_id=True)
        zones_by_entity = {zone.entity_id: zone for zone in config.zones}

        if user_input is not None:
            selected = set(user_input.get("selected_zones", []))
            config.zones = [
                ZoneConfig(
                    entity_id=item.entity_id,
                    name=item.name,
                    selected=item.entity_id in selected,
                    quiet_excluded=zones_by_entity.get(item.entity_id, ZoneConfig(item.entity_id)).quiet_excluded,
                )
                for item in discovered_zones
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
                "recommended_count": str(len(recommended_zones)),
                "total_count": str(len(discovered_zones)),
                **_speaker_drift_placeholders(config, discovered_zones),
            },
        )

    async def async_step_zones_all(self, user_input: dict[str, Any] | None = None):
        """Configure selected playback zones (full media_player list)."""

        config = self._config()
        discovered_zones = discover_media_players(self.hass.states.async_all())
        zones_by_entity = {zone.entity_id: zone for zone in config.zones}
        discovered_zone_ids = {zone.entity_id for zone in discovered_zones}
        available_selected = [
            zone.entity_id
            for zone in config.zones
            if zone.selected and zone.entity_id in discovered_zone_ids
        ]
        zone_options = _options(discovered_zones, include_entity_id=True)

        if user_input is not None:
            selected = set(user_input.get("selected_zones", []))
            config.zones = [
                ZoneConfig(
                    entity_id=item.entity_id,
                    name=item.name,
                    selected=item.entity_id in selected,
                    quiet_excluded=zones_by_entity.get(item.entity_id, ZoneConfig(item.entity_id)).quiet_excluded,
                )
                for item in discovered_zones
            ]
            return self._save(config)

        recommended_count = sum(1 for zone in discovered_zones if is_recommended_media_player(zone))
        return self.async_show_form(
            step_id="zones_all",
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
                "recommended_count": str(recommended_count),
                "total_count": str(len(discovered_zones)),
                **_speaker_drift_placeholders(config, discovered_zones),
            },
        )

    async def async_step_quiet(self, user_input: dict[str, Any] | None = None):
        """Configure quiet hours."""

        config = self._config()
        quiet = config.quiet

        if user_input is not None:
            config.quiet = QuietConfig(
                enabled=bool(user_input["enabled"]),
                start=user_input["start"],
                end=user_input["end"],
                volume_multiplier=float(user_input["volume_multiplier"]),
                excluded_zone_entity_ids=list(quiet.excluded_zone_entity_ids),
                zone_start=quiet.zone_start,
                zone_end=quiet.zone_end,
            )
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
                }
            ),
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
        """Configure one event and its per-person voice selection."""

        config = self._config()
        events_by_id = {event.id: event for event in config.events}
        voice_options = _voice_options(config)
        event = events_by_id[event_id]
        step_id = f"event_{event_id}"

        if user_input is not None:
            voice_by_context = {}
            for index, person in enumerate(config.people):
                field = _voice_person_field(index)
                selected_voice = user_input.get(field)
                if selected_voice and selected_voice != NONE_VALUE:
                    voice_by_context[person.id] = selected_voice
            config.events = [
                EventConfig(
                    id=existing.id,
                    name=existing.name,
                    enabled=bool(user_input["enabled"]),
                    voice_by_context=voice_by_context,
                    default_voice_id=user_input.get("default_voice_id"),
                    common_trigger_sound=existing.common_trigger_sound,
                    trigger_sound_by_context=dict(existing.trigger_sound_by_context),
                    bridge_helper_entity_id=existing.bridge_helper_entity_id,
                    duplicate_window_seconds=existing.duplicate_window_seconds,
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
        }
        for index, person in enumerate(config.people):
            fields[
                vol.Optional(
                    _voice_person_field(index),
                    default=event.voice_by_context.get(person.id, NONE_VALUE),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=NONE_VALUE, label="Use default voice")]
                    + voice_options
                )
            )

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(fields),
            description_placeholders={"event_name": _event_label(event_id)},
        )

    async def async_step_media(self, user_input: dict[str, Any] | None = None):
        """Configure approved media paths for events and voices."""

        config = self._config()

        if user_input is not None:
            events_by_id = {event.id: event for event in config.events}
            for event_id in DEFAULT_EVENTS:
                event = events_by_id[event_id]
                event.common_trigger_sound = _media_value(
                    user_input.get(_trigger_sound_field(event_id))
                )
            config.voices = [
                VoicePersonality(
                    id=voice.id,
                    name=voice.name,
                    source=voice.source,
                    media_by_event={
                        event_id: media_path
                        for event_id in DEFAULT_EVENTS
                        if (media_path := _media_value(user_input.get(_media_field(voice.id, event_id))))
                    },
                )
                for voice in config.voices
            ]
            return self._save(config)

        fields = {}
        for event_id in DEFAULT_EVENTS:
            event = next(event for event in config.events if event.id == event_id)
            fields[
                vol.Optional(
                    _trigger_sound_field(event_id),
                    default=_media_selector_default(event.common_trigger_sound),
                )
            ] = _media_selector()
        for event_id in DEFAULT_EVENTS:
            for voice in config.voices:
                fields[
                    vol.Optional(
                        _media_field(voice.id, event_id),
                        default=_media_selector_default(voice.media_by_event.get(event_id)),
                    )
                ] = _media_selector()
        return self.async_show_form(
            step_id="media",
            data_schema=vol.Schema(fields),
        )

    async def async_step_voice_media(self, user_input: dict[str, Any] | None = None):
        """Compatibility alias for older options links/tests."""

        return await self.async_step_media(user_input)

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None):
        """Configure advanced helpers, fallbacks, and raw overrides."""

        config = self._config()
        helper_options = [selector.SelectOptionDict(value=NONE_VALUE, label="None")]
        helper_options.extend(_options(discover_helpers(self.hass.states.async_all()), include_entity_id=True))
        tracker_options = _options(discover_device_trackers(self.hass.states.async_all()), include_entity_id=True)
        zone_options = _options(discover_media_players(self.hass.states.async_all()), include_entity_id=True)
        events_by_id = {event.id: event for event in config.events}

        if user_input is not None:
            for person in config.people:
                person.fallback_tracker_entity_ids = _list_value(
                    user_input.get(_fallback_trackers_field(person.id))
                )
            if "selected_zones_all" in user_input:
                selected = set(user_input.get("selected_zones_all", []))
                current_zones_by_entity = {zone.entity_id: zone for zone in config.zones}
                config.zones = [
                    ZoneConfig(
                        entity_id=item.entity_id,
                        name=item.name,
                        selected=item.entity_id in selected,
                        quiet_excluded=current_zones_by_entity.get(
                            item.entity_id,
                            ZoneConfig(item.entity_id),
                        ).quiet_excluded,
                    )
                    for item in discover_media_players(self.hass.states.async_all())
                ]
            quiet = config.quiet
            config.quiet = QuietConfig(
                enabled=quiet.enabled,
                start=quiet.start,
                end=quiet.end,
                volume_multiplier=quiet.volume_multiplier,
                excluded_zone_entity_ids=list(user_input.get("quiet_excluded_zones", [])),
                zone_start=user_input.get("zone_start") or None,
                zone_end=user_input.get("zone_end") or None,
            )
            for zone in config.zones:
                zone.quiet_excluded = zone.entity_id in config.quiet.excluded_zone_entity_ids
            for event_id in DEFAULT_EVENTS:
                event = events_by_id[event_id]
                if _trigger_sound_field(event_id) in user_input:
                    event.common_trigger_sound = _media_value(user_input.get(_trigger_sound_field(event_id)))
                bridge_helper = user_input.get(_bridge_helper_field(event_id))
                event.bridge_helper_entity_id = None if bridge_helper == NONE_VALUE else bridge_helper
                event.duplicate_window_seconds = int(user_input[_duplicate_window_field(event_id)])
                for person in config.people:
                    value = _media_value(user_input.get(_trigger_sound_context_field(event_id, person.id)))
                    if value:
                        event.trigger_sound_by_context[person.id] = value
                    else:
                        event.trigger_sound_by_context.pop(person.id, None)
            for voice in config.voices:
                for event_id in DEFAULT_EVENTS:
                    field = _media_field(voice.id, event_id)
                    if field in user_input:
                        value = _media_value(user_input.get(field))
                        if value:
                            voice.media_by_event[event_id] = value
                        else:
                            voice.media_by_event.pop(event_id, None)
            return self._save(config)

        fields = {}
        for person in config.people:
            fields[
                vol.Optional(
                    _fallback_trackers_field(person.id),
                    default=list(person.fallback_tracker_entity_ids),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=tracker_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        fields[
            vol.Optional(
                "selected_zones_all",
                default=[zone.entity_id for zone in config.zones if zone.selected],
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=zone_options,
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        fields[
            vol.Optional(
                "quiet_excluded_zones",
                default=list(config.quiet.excluded_zone_entity_ids),
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=zone_options,
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        fields[vol.Optional("zone_start", default=config.quiet.zone_start or "")] = str
        fields[vol.Optional("zone_end", default=config.quiet.zone_end or "")] = str
        for event_id in DEFAULT_EVENTS:
            event = events_by_id[event_id]
            fields[vol.Optional(_trigger_sound_field(event_id), default=event.common_trigger_sound or "")] = str
            fields[
                vol.Optional(
                    _bridge_helper_field(event_id),
                    default=event.bridge_helper_entity_id or NONE_VALUE,
                )
            ] = selector.SelectSelector(selector.SelectSelectorConfig(options=helper_options))
            fields[
                vol.Optional(
                    _duplicate_window_field(event_id),
                    default=event.duplicate_window_seconds,
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=3600))
            for person in config.people:
                fields[
                    vol.Optional(
                        _trigger_sound_context_field(event_id, person.id),
                        default=_media_selector_default(
                            event.trigger_sound_by_context.get(person.id)
                        ),
                    )
                ] = _media_selector()
            for voice in config.voices:
                fields[
                    vol.Optional(
                        _media_field(voice.id, event_id),
                        default=voice.media_by_event.get(event_id, ""),
                    )
                ] = str

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(fields),
        )

    async def async_step_review(self, user_input: dict[str, Any] | None = None):
        """Show a non-audible setup review."""

        config = self._config()
        if user_input is not None:
            return self._save(config)

        states = {state.entity_id: state.state for state in self.hass.states.async_all()}
        summaries = []
        for event_id in DEFAULT_EVENTS:
            resolution = resolve_announcement(
                config,
                event_id,
                ResolverRuntime(states=states, available_media=None),
            )
            status = "ready" if resolution.ok else "needs setup"
            detail = ", ".join(resolution.errors or resolution.warnings or ["ok"])
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
        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema({}),
            description_placeholders={
                "summary": "\n".join(summaries),
                "music_assistant": service_summary,
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


def _id_from_entity(entity_id: str) -> str:
    return entity_id.split(".", 1)[-1]


def _voice_field(event_id: str, person_id: str) -> str:
    return f"{event_id}_{person_id}_voice_id"


def _voice_person_field(index: int) -> str:
    return f"person_voice_{index + 1}"


def _media_field(voice_id: str, event_id: str) -> str:
    return f"{voice_id}_{event_id}_media_path"


def _trigger_sound_field(event_id: str) -> str:
    return f"{event_id}_common_trigger_sound"


def _trigger_sound_context_field(event_id: str, person_id: str) -> str:
    return f"{event_id}_{person_id}_trigger_sound"


def _fallback_trackers_field(person_id: str) -> str:
    return f"{person_id}_fallback_trackers"


def _bridge_helper_field(event_id: str) -> str:
    return f"{event_id}_bridge_helper_entity_id"


def _duplicate_window_field(event_id: str) -> str:
    return f"{event_id}_duplicate_window_seconds"


def _event_label(event_id: str) -> str:
    return EVENT_LABELS.get(event_id, event_id.replace("_", " ").title())


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
