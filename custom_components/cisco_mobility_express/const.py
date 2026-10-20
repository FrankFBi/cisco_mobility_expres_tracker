"""Constants for the Cisco Mobility Express integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "cisco_mobility_express"
PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]
SCAN_INTERVAL = timedelta(seconds=30)
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300
IPV6_POLLING_INTERVAL = timedelta(minutes=5)
MIN_IPV6_POLLING_INTERVAL = 1
MAX_IPV6_POLLING_INTERVAL = 15
CONF_IPV6_POLLING_INTERVAL = "ipv6_polling_interval"
CONF_ALL_IPV6 = "all_ipv6"
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
