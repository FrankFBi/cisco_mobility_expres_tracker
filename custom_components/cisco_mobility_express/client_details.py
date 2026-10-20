"""Client IP and SSID details from the controller's classic web UI.

The Mobility Express JSON pages do not include IP addresses or the SSID, but
the AireOS client list (Monitoring > Clients) has each client's IP and SSID,
and its detail page (Monitoring > Clients > Detail) also lists all IPv6 addresses.
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
# List rows are named "1.<row>.<total>.<field>".
_LIST_FIELD = re.compile(
    r'name="\d+\.(\d+)\.\d+\.(ms_addr|ms_ipaddr|ms_ssid)"[^>]*value="([^"]*)"', re.IGNORECASE
)


class ClientDetailsUnavailable(Exception):
    """The controller does not serve the classic client detail page."""


def _build_details(addresses: list[str], ssid: str) -> dict[str, Any]:
    """Return ip, ipv4, ipv6 and SSID attributes from raw controller values."""
    details: dict[str, Any] = {}
    ipv4: str | None = None
    ipv6: list[str] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value.strip())
        except ValueError:
            continue
        if address.version == 6:
            ipv6.append(str(address))
        elif not address.is_unspecified and ipv4 is None:
            ipv4 = str(address)

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

    if ssid := ssid.strip():
        details["SSID"] = ssid

    return details


def parse_client_details(html: str) -> dict[str, Any]:
    """Extract IPv4, IPv6 and SSID from a client detail page."""
    addresses = [m.group(1)] if (m := _IPV4.search(html)) else []
    if match := _IPV6.search(html):
        addresses += match.group(1).split(",")
    return _build_details(addresses, m.group(1) if (m := _SSID.search(html)) else "")


def parse_client_list(html: str) -> dict[str, dict[str, Any]]:
    """Extract each client's IP and SSID from the client list page, keyed by MAC."""
    rows: dict[str, dict[str, str]] = {}
    for row, name, value in _LIST_FIELD.findall(html):
        rows.setdefault(row, {})[name.lower()] = value
    return {
        row["ms_addr"].strip().lower(): _build_details(
            [row.get("ms_ipaddr", "")], row.get("ms_ssid", "")
        )
        for row in rows.values()
        if row.get("ms_addr")
    }


def fetch_client_details(
    session: Session, base_url: str, macs: list[str], all_ipv6: bool = False
) -> dict[str, dict[str, Any]]:
    """Fetch details for the given client MACs (blocking).

    One request for the client list covers every listed client. A client's
    detail page is only requested when it is missing from the list or when
    all_ipv6 is set, as only that page lists every IPv6 address.

    Raises ClientDetailsUnavailable if the controller has no detail page.
    """
    list_url = f"{base_url}{CLIENT_LIST_PATH}"
    response = session.get(list_url)
    if response.status_code != 200 or not (token := _CSRF_TOKEN.search(response.text)):
        raise ClientDetailsUnavailable(f"{list_url} returned HTTP {response.status_code}")

    listed = parse_client_list(response.text)
    results = {mac: listed[mac] for mac in macs if mac in listed}
    for mac in macs if all_ipv6 else [mac for mac in macs if mac not in listed]:
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
