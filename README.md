# Cisco Mobility Express tracker for Home Assistant

Presence detection for clients of a [Cisco Mobility Express](https://www.cisco.com/c/en/us/solutions/enterprise-networks/mobility-express/index.html) wireless controller **or a full Cisco Wireless LAN Controller (WLC)** running AireOS. Both use the same web API, so the integration works on either; on a WLC it also reads IP, SSID and band per client (see [Entities](#entities)).

> **Disclaimer:** this is an independent community project. It is not affiliated with, endorsed by, sponsored by or in any way linked to Cisco Systems, Inc. Cisco, Mobility Express and related names are trademarks of Cisco Systems, Inc.

This is a config-entry (UI) port of the core [`cisco_mobility_express`](https://www.home-assistant.io/integrations/cisco_mobility_express/) integration. That integration uses the legacy `device_tracker` platform API, which [is deprecated and will be removed in Home Assistant 2027.5](https://developers.home-assistant.io/blog/2026/04/20/legacy-device-tracker-deprecation/). This version uses the modern `ScannerEntity` API and keeps the same domain, so it replaces the core integration once installed.

## Installation

> **Upgrading from the core YAML tracker?** First remove the `cisco_mobility_express` platform from `configuration.yaml`, see [Migrating from the YAML platform](#migrating-from-the-yaml-platform). This integration has no YAML support, so a leftover entry only produces errors.

### HACS

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FrankFBi&repository=cisco_mobility_expres_tracker&category=integration)

1. Click the button above, or go to HACS → ⋮ → Custom repositories and add `https://github.com/FrankFBi/cisco_mobility_expres_tracker` (type *Integration*).
2. Install **Cisco Mobility Express** and restart Home Assistant.

HACS installs the release zip (`zip_release` in `hacs.json`), the same file as the manual install below.

### From a release zip

1. Download `cisco_mobility_express.zip` from the latest release on the [Releases page](https://github.com/FrankFBi/cisco_mobility_expres_tracker/releases).
2. Create the folder `<config>/custom_components/cisco_mobility_express/` and unzip the archive into it, so that `manifest.json` ends up directly in that folder. You can reach `<config>` with the Samba share, SSH or File editor apps.
3. Restart Home Assistant.

To update, delete the contents of that folder, unzip the new release into it and restart.

## Releasing

Set `version` in `manifest.json` on `main` to the new version, then push a matching tag like `v1.4.1`. The release workflow also sets `version` from the tag, builds `cisco_mobility_express.zip` and publishes a GitHub release with that zip attached.

```bash
git tag v1.4.1 && git push origin v1.4.1
```

## Configuration

Settings → Devices & services → Add integration → **Cisco Mobility Express**.

| Field | Description |
| --- | --- |
| Host | IP or hostname of the controller, e.g. `192.168.10.150` |
| Username / Password | An account with administrative privileges |
| Use HTTPS | Connect over HTTPS instead of HTTP (default off) |
| Verify SSL certificate | Turn off for self-signed certificates (default on) |
| Polling interval | Seconds between polls of the client list, 30–300 (default 30) |

### Options

Click **Configure** on the integration's page to change these settings. Changes apply without a restart.

| Option | Range (default) | Description |
| --- | --- | --- |
| Polling interval | 30–300 s (30) | How often the client list is read. A longer interval reduces the load on large controllers, but trackers and sensors react more slowly. |
| IPv6 › Fetch all IPv6 addresses | off | Also read each client's detail page for the full `ipv6` list. Costs one extra request per client, so leave it off on large setups unless you need it. **Only used on a full WLC.** |
| IPv6 › IPv6 polling interval | 1–15 min (5) | How often those detail pages are read. Only used when *Fetch all IPv6 addresses* is on. |
| Remove disabled trackers after | 1–60 days (30) | See [Cleanup of unused trackers](#cleanup-of-unused-trackers). |

### Changing the connection

To change the host, username, password, *Use HTTPS* or *Verify SSL certificate*, open the integration's ⋮ menu and choose **Reconfigure**. Leave the password empty to keep the current one. The connection is tested before saving. Trackers, devices and options are kept, also when the host changes, because they are tied to the clients' MAC addresses.

If the controller later rejects the credentials, Home Assistant prompts you to reauthenticate.

## Migrating from the YAML platform

Do these steps in this order:

1. Remove the `cisco_mobility_express` entry under `device_tracker:` in `configuration.yaml`, for example:
   ```yaml
   device_tracker:
     - platform: cisco_mobility_express  # remove this entry
       host: 192.168.10.150
       username: !secret me_username
       password: !secret me_password
   ```
   If it was the only entry, remove the `device_tracker:` line too.
2. Install this integration and restart Home Assistant.
3. Add it through the UI (Settings → Devices & services → Add integration) with the same host and credentials.
4. Tracked clients now show up as `device_tracker` entities on the integration. Like every modern router tracker, an entity is **disabled by default** unless its MAC address already belongs to a device from another integration (see [Which trackers start enabled](#which-trackers-start-enabled)). Enable the ones you want and assign them to a person. Old entries in `known_devices.yaml` are no longer used.

## Entities

There is one `device_tracker` entity per client MAC address the controller has reported. It is `home` while the client is associated and `not_home` after it leaves. Attributes include the hostname (`clId`) and whatever the controller's client table reports, such as `AP`, `PT` and `SS`. The controller is polled every 30 seconds by default (see *Polling interval* above).

On controllers with the classic AireOS web UI, such as a Cisco WLC, the client list is also read for:

| Attribute | Value |
|---|---|
| `ip` | IPv4 address, or the first global IPv6 address if the client has no IPv4 |
| `ipv4` | IPv4 address |
| `ipv6` | IPv6 address from the client list; with *Fetch all IPv6 addresses* on, all IPv6 addresses including link-local |
| `SSID` | WLAN SSID |
| `FB` | Band from the client list's protocol column (e.g. `802.11ac(5 GHz)` → `5GHz`), only when the controller's client table doesn't report `FB` itself |

Attributes the controller doesn't report are left out. The client list is read on every poll: one request per 75 clients, as the WLC splits it into pages of 75. Mobility Express doesn't serve it as far as we know; the integration then stops asking after the first try. A client without a usable address in the list gets its own detail page request instead, at the IPv6 polling interval. That covers clients missing from the list and IPv6-only clients for which the list only shows the link-local `fe80::` address. Controllers without these pages are tracked as before, without these attributes.

### Which trackers start enabled

New trackers start **disabled**, except when the client's MAC address already belongs to a device from another integration. Home Assistant then adds the tracker to that device and enables it. This is standard Home Assistant behaviour, the same as for other router integrations.

For example, an ESPHome device such as a Home Assistant Voice registers its Wi-Fi MAC address on its own device. Its tracker therefore shows up enabled on the Voice device's page instead of as a separate device. If you don't want it, disable the tracker entity there. It stays disabled, and the cleanup below removes it once the client is no longer seen.

### Cleanup of unused trackers

A **disabled** tracker is deleted once its client hasn't been seen on the controller for 30 days (see *Remove disabled trackers after* under [Options](#options)). If that client connects again, it gets a new tracker, which starts disabled like any new client. Enabled trackers are never deleted. Disabled trackers that existed before this feature start counting when you install it.

### Devices

Every **enabled** tracker gets a device, named after the tracker, with the client's MAC as its connection. The device has these diagnostic sensors: *IPv4 address*, *Access point* (`AP`), *SSID*, *Protocol* (`PT`), *Band* (`FB`) and *Signal strength* (`SS`, in dBm). With *Fetch all IPv6 addresses* on, there is also an *IPv6 addresses* sensor with the comma-separated list (cut off at 255 characters, the longest state Home Assistant allows; the `ipv6` attribute keeps the full list). Turning that option on or off reloads the integration to add or remove it. The sensors are `unknown` while the client is disconnected. Disabled trackers get no device. Home Assistant reloads the integration about 30 seconds after you enable or disable a tracker, and that reload adds or removes the device.

### Locating a person by access point

The tracker is mainly used to find out where a person is, using their phone's Wi-Fi connection. The `home`/`not_home` state shows whether the phone is on the network. The `AP` attribute shows **which access point** the phone is connected to, e.g. `AP3-Garage`. Give your APs room names on the controller, and `AP` then tells you which part of the house the person is in. It updates on every 30-second poll and is gone while the phone is disconnected.

Read it in a template:

```jinja
{{ state_attr('device_tracker.franks_phone', 'AP') }}
```

On an enabled tracker, the device's *Access point* sensor has the same value as a state, so it can be used directly in history graphs and triggers.

The controller is polled every 30 seconds, and a client that has left takes a little longer to be reported as gone. That's too slow for turning a light on as someone walks in. It suits actions that can wait a few minutes: heating, and turning things off once a person has left. For example, lights off once Frank's phone has been off the home network for 5 minutes:

```yaml
automation:
  - alias: Lights off when Frank has left home
    triggers:
      - trigger: state
        entity_id: device_tracker.franks_phone
        to: not_home
        for: "00:05:00"
    actions:
      - action: light.turn_off
        target:
          entity_id: light.office
```

The main use is heating: turning off the heater in a room nobody is in. Here the office heater turns off once Frank's phone has been off the office AP for 10 minutes. That covers both moving to another AP and leaving the house, since the sensor is `unknown` while the phone is disconnected:

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
