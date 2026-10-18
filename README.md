# Cisco Mobility Express tracker for Home Assistant

Presence detection for clients of a [Cisco Mobility Express](https://www.cisco.com/c/en/us/solutions/enterprise-networks/mobility-express/index.html) wireless controller.

This is a config-entry (UI) port of the core `cisco_mobility_express` integration. That integration uses the legacy `device_tracker` platform API, which [is deprecated and will be removed in Home Assistant 2027.5](https://developers.home-assistant.io/blog/2026/04/20/legacy-device-tracker-deprecation/). This version uses the modern `ScannerEntity` API and keeps the same domain, so it replaces the core integration once installed.

## Installation

### HACS

1. HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/FrankFBi/cisco_mobility_expres_tracker` (category *Integration*).
2. Install **Cisco Mobility Express** and restart Home Assistant.

### Manual

Copy `custom_components/cisco_mobility_express` to `<config>/custom_components/` and restart Home Assistant.

## Configuration

Settings → Devices & services → Add integration → **Cisco Mobility Express**.

| Field | Description |
| --- | --- |
| Host | IP or hostname of the controller, e.g. `192.168.10.150` |
| Username / Password | An account with administrative privileges |
| Use HTTPS | Connect over HTTPS instead of HTTP (default off) |
| Verify SSL certificate | Turn off for self-signed certificates (default on) |

If the controller later rejects the credentials, Home Assistant prompts you to reauthenticate.

## Migrating from the YAML platform

1. Remove the `- platform: cisco_mobility_express` entry under `device_tracker:` in `configuration.yaml`.
2. Install this integration, restart, and add it through the UI with the same settings.
3. Tracked clients now show up as `device_tracker` entities on the integration. Like every modern router tracker, an entity is **disabled by default** unless its MAC address already belongs to a device from another integration. Enable the ones you want and assign them to a person. Old entries in `known_devices.yaml` are no longer used.

## Entities

There is one `device_tracker` entity per client MAC address the controller has reported. It is `home` while the client is associated and `not_home` after it leaves. Attributes include the IP address and hostname (`clId`), plus whatever the controller reports for the client, such as `SSID`, `PT` and `devtype`. The controller is polled every 30 seconds.

## Development

```bash
pip install -r requirements_test.txt   # Python 3.14
ruff check . && ruff format --check .
pytest
```
