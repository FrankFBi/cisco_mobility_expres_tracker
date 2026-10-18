"""Client IP and SSID details from the controller's classic web UI.

The Mobility Express JSON pages do not include IP addresses or the SSID, but
the AireOS client detail page (Monitoring > Clients > Detail) does.
"""

import ipaddress
import logging
import re
from typing import Any

from requests import Session

_LOGGER = logging.getLogger(__name__)

CLIENT_LIST_PATH = "/screens/apf/mobile_station_list.html"

_CSRF_TOKEN = re.compile(r'name="csrf_token"[^>]*value="([^"]*)"', re.IGNORECASE)
_IPV4 = re.compile(r'name="ms_ipaddr"[^>]*value="([^"]*)"', re.IGNORECASE)
_IPV6 = re.compile(r'name="ms_ipaddr6"[^>]*>([^<]*)</textarea>', re.IGNORECASE)
_SSID = re.compile(r'name="ms_ssid"[^>]*value="([^"]*)"', re.IGNORECASE)


class ClientDetailsUnavailable(Exception):
    """The controller does not serve the classic client detail page."""


def parse_client_details(html: str) -> dict[str, Any]:
    """Extract IPv4, IPv6 and SSID from a client detail page."""
    details: dict[str, Any] = {}
    ipv4: str | None = None
    ipv6: list[str] = []

    if match := _IPV4.search(html):
        try:
            address = ipaddress.IPv4Address(match.group(1).strip())
        except ValueError:
            pass
        else:
            if not address.is_unspecified:
                ipv4 = str(address)

    if match := _IPV6.search(html):
        for value in match.group(1).split(","):
            try:
                ipv6.append(str(ipaddress.IPv6Address(value.strip())))
            except ValueError:
                continue

    if ipv4:
        details["ipv4"] = ipv4
    if ipv6:
        details["ipv6"] = ipv6
    if (
        ip := ipv4
        or next((a for a in ipv6 if not ipaddress.IPv6Address(a).is_link_local), None)
        or next(iter(ipv6), None)
    ):
        details["ip"] = ip

    if (match := _SSID.search(html)) and match.group(1).strip():
        details["SSID"] = match.group(1).strip()

    return details


def fetch_client_details(
    session: Session, base_url: str, macs: list[str]
) -> dict[str, dict[str, Any]]:
    """Fetch details for the given client MACs (blocking).

    Raises ClientDetailsUnavailable if the controller has no detail page.
    """
    list_url = f"{base_url}{CLIENT_LIST_PATH}"
    response = session.get(list_url)
    if response.status_code != 200 or not (token := _CSRF_TOKEN.search(response.text)):
        raise ClientDetailsUnavailable(f"{list_url} returned HTTP {response.status_code}")

    results: dict[str, dict[str, Any]] = {}
    for mac in macs:
        response = session.post(
            list_url,
            data={
                "csrf_token": token.group(1),
                "buttonClicked": "2",
                "query_str": "",
                "indexClicked": "0",
                "selected_ms_addr": mac,
            },
            headers={"Referer": list_url},
        )
        if response.status_code != 200:
            _LOGGER.debug("Client detail for %s returned HTTP %s", mac, response.status_code)
        results[mac] = parse_client_details(response.text) if response.status_code == 200 else {}
    return results
