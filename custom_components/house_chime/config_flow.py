"""Config flow for House Chime."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import CONF_ACTIVE_CONFIG, DEFAULT_EVENTS, DEFAULT_NAME, DOMAIN
from .discovery import discover_device_trackers, discover_helpers, discover_media_players, discover_people
from .models import AnnouncementConfig, EventConfig, PersonConfig, QuietConfig, VoicePersonality, ZoneConfig
from .storage import migrate_config_dict

NONE_VALUE = "__none__"


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
    def async_get_options_flow(config_entry):
        """Return the options flow."""

        return HouseChimeOptionsFlow(config_entry)


class HouseChimeOptionsFlow(config_entries.OptionsFlow):
    """Options flow for the operator-managed runtime config."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the configuration menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options=["people", "zones", "quiet", "events", "voice_media"],
        )

    async def async_step_people(self, user_input: dict[str, Any] | None = None):
        """Configure selected people and priority."""

        config = self._config()
        discovered_people = discover_people(self.hass.states.async_all())
        discovered_trackers = discover_device_trackers(self.hass.states.async_all())
        people_options = _options(discovered_people)
        current_people_by_entity = {
            person.entity_id: person for person in config.people if person.entity_id
        }
        selected_people = [
            person.entity_id for person in config.people if person.in_scope and person.entity_id
        ]
        default_context_options = [
            selector.SelectOptionDict(value=person.id, label=person.name) for person in config.people
        ] or [selector.SelectOptionDict(value=NONE_VALUE, label="None")]

        if user_input is not None:
            selected = list(user_input.get("selected_people", []))
            tracker_by_person = _parse_mapping(user_input.get("fallback_trackers", ""))
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
                        fallback_tracker_entity_ids=tracker_by_person.get(person_id, []),
                        in_scope=True,
                        default_voice_id=existing.default_voice_id if existing else None,
                        custom_voice_profile=existing.custom_voice_profile if existing else None,
                    )
                )
            config.people = people
            config.person_priority = _ordered_ids(user_input.get("priority_order", ""), selected)
            default_context_id = user_input.get("default_context_id")
            config.default_context_id = None if default_context_id == NONE_VALUE else default_context_id
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
                    vol.Optional(
                        "priority_order",
                        default=", ".join(config.person_priority),
                    ): str,
                    vol.Optional(
                        "default_context_id",
                        default=config.default_context_id or NONE_VALUE,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=default_context_options)
                    ),
                    vol.Optional(
                        "fallback_trackers",
                        default=_format_tracker_mapping(config.people),
                    ): str,
                }
            ),
            description_placeholders={
                "fallback_help": "Fallback format: david=device_tracker.david_phone; scarlett=device_tracker.scarlett_phone",
                "tracker_count": str(len(discovered_trackers)),
            },
        )

    async def async_step_zones(self, user_input: dict[str, Any] | None = None):
        """Configure selected playback zones."""

        config = self._config()
        discovered_zones = discover_media_players(self.hass.states.async_all())
        zone_options = _options(discovered_zones)
        zones_by_entity = {zone.entity_id: zone for zone in config.zones}

        if user_input is not None:
            selected = set(user_input.get("selected_zones", []))
            quiet_excluded = set(user_input.get("quiet_excluded_zones", []))
            config.zones = [
                ZoneConfig(
                    entity_id=item.entity_id,
                    name=item.name,
                    selected=item.entity_id in selected,
                    quiet_excluded=item.entity_id in quiet_excluded,
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
                        default=[zone.entity_id for zone in config.zones if zone.selected],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=zone_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "quiet_excluded_zones",
                        default=[
                            entity_id
                            for entity_id, zone in zones_by_entity.items()
                            if zone.quiet_excluded
                        ],
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=zone_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
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
                zone_start=user_input.get("zone_start") or None,
                zone_end=user_input.get("zone_end") or None,
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
                    vol.Optional("zone_start", default=quiet.zone_start or ""): str,
                    vol.Optional("zone_end", default=quiet.zone_end or ""): str,
                }
            ),
        )

    async def async_step_events(self, user_input: dict[str, Any] | None = None):
        """Configure event behavior and per-context voices."""

        config = self._config()
        events_by_id = {event.id: event for event in config.events}
        voice_options = _voice_options(config)
        helper_options = [selector.SelectOptionDict(value=NONE_VALUE, label="None")]
        helper_options.extend(_options(discover_helpers(self.hass.states.async_all())))

        if user_input is not None:
            updated_events = []
            for event_id in DEFAULT_EVENTS:
                existing = events_by_id.get(
                    event_id,
                    EventConfig(id=event_id, name=event_id.replace("_", " ").title()),
                )
                voice_by_context = {}
                for person in config.people:
                    field = _voice_field(event_id, person.id)
                    selected_voice = user_input.get(field)
                    if selected_voice and selected_voice != NONE_VALUE:
                        voice_by_context[person.id] = selected_voice
                bridge_helper = user_input.get(f"{event_id}_bridge_helper_entity_id")
                updated_events.append(
                    EventConfig(
                        id=event_id,
                        name=existing.name,
                        enabled=bool(user_input[f"{event_id}_enabled"]),
                        voice_by_context=voice_by_context,
                        default_voice_id=user_input.get(f"{event_id}_default_voice_id"),
                        common_trigger_sound=user_input.get(f"{event_id}_common_trigger_sound") or None,
                        trigger_sound_by_context=dict(existing.trigger_sound_by_context),
                        bridge_helper_entity_id=None if bridge_helper == NONE_VALUE else bridge_helper,
                        duplicate_window_seconds=int(user_input[f"{event_id}_duplicate_window_seconds"]),
                    )
                )
            config.events = updated_events
            return self._save(config)

        fields = {}
        for event_id in DEFAULT_EVENTS:
            event = events_by_id[event_id]
            fields[vol.Optional(f"{event_id}_enabled", default=event.enabled)] = bool
            fields[
                vol.Optional(
                    f"{event_id}_default_voice_id",
                    default=event.default_voice_id or "samantha",
                )
            ] = selector.SelectSelector(selector.SelectSelectorConfig(options=voice_options))
            fields[
                vol.Optional(
                    f"{event_id}_common_trigger_sound",
                    default=event.common_trigger_sound or "",
                )
            ] = str
            fields[
                vol.Optional(
                    f"{event_id}_bridge_helper_entity_id",
                    default=event.bridge_helper_entity_id or NONE_VALUE,
                )
            ] = selector.SelectSelector(selector.SelectSelectorConfig(options=helper_options))
            fields[
                vol.Optional(
                    f"{event_id}_duplicate_window_seconds",
                    default=event.duplicate_window_seconds,
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=3600))
            for person in config.people:
                fields[
                    vol.Optional(
                        _voice_field(event_id, person.id),
                        default=event.voice_by_context.get(person.id, NONE_VALUE),
                    )
                ] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=NONE_VALUE, label="Default")]
                        + voice_options
                    )
                )

        return self.async_show_form(
            step_id="events",
            data_schema=vol.Schema(fields),
        )

    async def async_step_voice_media(self, user_input: dict[str, Any] | None = None):
        """Configure approved media paths for voices."""

        config = self._config()

        if user_input is not None:
            config.voices = [
                VoicePersonality(
                    id=voice.id,
                    name=voice.name,
                    source=voice.source,
                    media_by_event={
                        event_id: media_path
                        for event_id in DEFAULT_EVENTS
                        if (media_path := user_input.get(_media_field(voice.id, event_id)))
                    },
                )
                for voice in config.voices
            ]
            return self._save(config)

        fields = {}
        for voice in config.voices:
            for event_id in DEFAULT_EVENTS:
                fields[
                    vol.Optional(
                        _media_field(voice.id, event_id),
                        default=voice.media_by_event.get(event_id, ""),
                    )
                ] = str
        return self.async_show_form(
            step_id="voice_media",
            data_schema=vol.Schema(fields),
        )

    def _config(self) -> AnnouncementConfig:
        current_config = self._config_entry.options.get(CONF_ACTIVE_CONFIG) or self._config_entry.data.get(
            CONF_ACTIVE_CONFIG
        )
        migrated, _ = migrate_config_dict(current_config)
        return AnnouncementConfig.from_dict(migrated)

    def _save(self, config: AnnouncementConfig):
        migrated, _ = migrate_config_dict(config.to_dict())
        return self.async_create_entry(title="", data={CONF_ACTIVE_CONFIG: migrated})


def _options(records) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=record.entity_id, label=f"{record.name} ({record.entity_id})")
        for record in records
    ]


def _voice_options(config: AnnouncementConfig) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=voice.id, label=voice.name)
        for voice in config.voices
    ]


def _id_from_entity(entity_id: str) -> str:
    return entity_id.split(".", 1)[-1]


def _ordered_ids(priority_order: str, selected_entity_ids: list[str]) -> list[str]:
    selected_ids = [_id_from_entity(entity_id) for entity_id in selected_entity_ids]
    typed = [item.strip() for item in priority_order.split(",") if item.strip()]
    ordered = [item for item in typed if item in selected_ids]
    ordered.extend(item for item in selected_ids if item not in ordered)
    return ordered


def _parse_mapping(value: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for segment in value.split(";"):
        if "=" not in segment:
            continue
        person_id, tracker_values = segment.split("=", 1)
        mapping[person_id.strip()] = [
            tracker.strip() for tracker in tracker_values.split(",") if tracker.strip()
        ]
    return mapping


def _format_tracker_mapping(people: list[PersonConfig]) -> str:
    return "; ".join(
        f"{person.id}={','.join(person.fallback_tracker_entity_ids)}"
        for person in people
        if person.fallback_tracker_entity_ids
    )


def _voice_field(event_id: str, person_id: str) -> str:
    return f"{event_id}_{person_id}_voice_id"


def _media_field(voice_id: str, event_id: str) -> str:
    return f"{voice_id}_{event_id}_media_path"
