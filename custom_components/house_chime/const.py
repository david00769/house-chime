"""Constants for House Chime."""

DOMAIN = "house_chime"

CONF_ACTIVE_CONFIG = "active_config"
CONF_EVENT_ID = "event_id"
CONF_MEDIA_EXISTS = "media_exists"

DEFAULT_NAME = "House Chime"
PLATFORMS = ["sensor", "binary_sensor"]
SIGNAL_STATUS_UPDATED = f"{DOMAIN}_status_updated"

DEFAULT_NORMAL_VOLUME = 0.8
DEFAULT_QUIET_MULTIPLIER = 0.5
DEFAULT_DUPLICATE_WINDOW_SECONDS = 45

EVENT_FRONT_DOOR_APPROACH = "front_door_approach"
EVENT_FRONT_DOOR_PACKAGE = "front_door_package"
EVENT_FRONT_DOOR_DOORBELL = "front_door_doorbell"

DEFAULT_EVENTS = (
    EVENT_FRONT_DOOR_APPROACH,
    EVENT_FRONT_DOOR_PACKAGE,
    EVENT_FRONT_DOOR_DOORBELL,
)

STATE_HOME = "home"
STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"

DEFAULT_VOICES = (
    "eve",
    "leo",
    "pierce",
    "samantha",
)
