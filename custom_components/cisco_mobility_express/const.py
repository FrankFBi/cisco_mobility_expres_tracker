"""Constants for the Cisco Mobility Express integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "cisco_mobility_express"
PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]
SCAN_INTERVAL = timedelta(seconds=30)
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300
DETAILS_INTERVAL = timedelta(minutes=5)
MIN_DETAILS_INTERVAL = 1
MAX_DETAILS_INTERVAL = 15
CONF_DETAILS_INTERVAL = "details_interval"
PRUNE_INTERVAL = timedelta(hours=1)
STALE_TRACKER_AGE = timedelta(days=30)
MIN_STALE_TRACKER_AGE = 1
MAX_STALE_TRACKER_AGE = 60
CONF_STALE_TRACKER_AGE = "stale_tracker_age"

DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True

ATTR_HOSTNAME = "clId"
ATTR_MAC = "macaddr"
IP_ADDRESS_KEYS = ("ip", "ipaddr", "ipAddress")
