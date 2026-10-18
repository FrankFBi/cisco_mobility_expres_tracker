# Cisco Mobility Express tracker for Home Assistant

Presence detection for clients of a [Cisco Mobility Express](https://www.cisco.com/c/en/us/solutions/enterprise-networks/mobility-express/index.html) wireless controller.

This is a config-entry (UI) port of the core [`cisco_mobility_express`](https://www.home-assistant.io/integrations/cisco_mobility_express/) integration. That integration uses the legacy `device_tracker` platform API, which [is deprecated and will be removed in Home Assistant 2027.5](https://developers.home-assistant.io/blog/2026/04/20/legacy-device-tracker-deprecation/). This version uses the modern `ScannerEntity` API and keeps the same domain, so it replaces the core integration once installed.

## Installation

### From a release zip

1. Download `cisco_mobility_express.zip` from the latest release on the [Releases page](https://github.com/FrankFBi/cisco_mobility_expres_tracker/releases). The repository is private, so you need to be signed in to GitHub with access to it.
2. Create the folder `<config>/custom_components/cisco_mobility_express/` and unzip the archive into it, so that `manifest.json` ends up directly in that folder. You can reach `<config>` with the Samba share, SSH or File editor apps.
3. Restart Home Assistant.

To update, delete the contents of that folder, unzip the new release into it and restart.

### HACS (once the repository is public)

HACS only works with public repositories. `hacs.json` is already set up to install the same release zip (`zip_release`), so once the repository is public:

1. HACS → ⋮ → Custom repositories → add `https://github.com/FrankFBi/cisco_mobility_expres_tracker` (type *Integration*).
2. Install **Cisco Mobility Express** and restart Home Assistant.

## Releasing

Push a tag like `v1.0.1`. The release workflow sets `version` in `manifest.json` from the tag, builds `cisco_mobility_express.zip` and publishes a GitHub release with that zip attached.

```bash
git tag v1.0.1 && git push origin v1.0.1
```

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

There is one `device_tracker` entity per client MAC address the controller has reported. It is `home` while the client is associated and `not_home` after it leaves. Attributes include the hostname (`clId`) and whatever the controller's client table reports, such as `AP`, `PT` and `SS`. The controller is polled every 30 seconds.

On controllers with the classic AireOS client detail page, such as a Cisco WLC, each client's detail page is also read for:

| Attribute | Value |
|---|---|
| `ip` | IPv4 address, or the first global IPv6 address if the client has no IPv4 |
| `ipv4` | IPv4 address |
| `ipv6` | All IPv6 addresses, including link-local |
| `SSID` | WLAN SSID |

Attributes the controller doesn't report are left out. Details are fetched when a client connects and then every 5 minutes. Controllers without that page are tracked as before, without these attributes.

### Cleanup of unused trackers

A **disabled** tracker is deleted once its client hasn't been seen on the controller for 30 days. If that client connects again, it gets a new tracker, which starts disabled like any new client. Enabled trackers are never deleted. Disabled trackers that existed before this feature start their 30 days when you install it.

### Devices

Every **enabled** tracker gets a device, named after the tracker, with the client's MAC as its connection. The device has these diagnostic sensors: *IPv4 address*, *Access point* (`AP`), *SSID*, *Protocol* (`PT`) and *Band* (`FB`). They are `unknown` while the client is disconnected. Disabled trackers get no device. Home Assistant reloads the integration about 30 seconds after you enable or disable a tracker, and that reload adds or removes the device.

### Locating a person by access point

The tracker is mainly used to find out where a person is, using their phone's Wi-Fi connection. The `home`/`not_home` state shows whether the phone is on the network. The `AP` attribute shows **which access point** the phone is connected to, e.g. `AP3-Garage`. Give your APs room names on the controller, and `AP` then tells you which part of the house the person is in. It updates on every 30-second poll and is gone while the phone is disconnected.

Read it in a template:

```jinja
{{ state_attr('device_tracker.franks_phone', 'AP') }}
```

On an enabled tracker, the device's *Access point* sensor has the same value as a state, so it can be used directly in history graphs and triggers:

```yaml
automation:
  - alias: Garage light on when Frank's phone joins the garage AP
    triggers:
      - trigger: state
        entity_id: sensor.franks_phone_access_point
        to: AP3-Garage
    actions:
      - action: light.turn_on
        target:
          entity_id: light.garage
```

A common use is turning off heating in a room nobody is in. Here the office heater turns off once Frank's phone has been off the office AP for 10 minutes. That covers both moving to another AP and leaving the house, since the sensor is `unknown` while the phone is disconnected:

```yaml
automation:
  - alias: Office heater off when Frank has left the office
    triggers:
      - trigger: state
        entity_id: sensor.franks_phone_access_point
        from: AP2-Office
        for: "00:10:00"
    actions:
      - action: climate.turn_off
        target:
          entity_id: climate.office_heater
```

The `for` delay is a buffer for walking through another room, so the heater stays on when you're only passing through.

This works well because the data comes from a controller (WLC or Mobility Express). The controller decides which AP each client is associated with, and with controller-based roaming (e.g. *Optimized Roaming*) it moves a phone to the nearest AP as it moves. Standalone APs often lack this, and their phones can stay on a distant AP. To get a reliable room location, enable roaming on the controller and place the APs so each room or zone has its own.

## Development

```bash
pip install -r requirements_test.txt   # Python 3.14
ruff check . && ruff format --check .
pytest
```
