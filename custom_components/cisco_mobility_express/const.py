"""Constants for the Cisco Mobility Express integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "cisco_mobility_express"
PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]
SCAN_INTERVAL = timedelta(seconds=30)
DETAILS_INTERVAL = timedelta(minutes=5)

DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True

ATTR_HOSTNAME = "clId"
ATTR_MAC = "macaddr"
IP_ADDRESS_KEYS = ("ip", "ipaddr", "ipAddress")
