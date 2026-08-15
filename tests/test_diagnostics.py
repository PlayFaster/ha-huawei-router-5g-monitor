"""Tests for the Huawei Router 5G diagnostics platform.

**These assert the output, not the mechanism.** The previous suite mocked
`async_redact_data` and asserted it had been *called* with the right arguments,
which is true of an implementation that redacts nothing useful — and that is
precisely the shape that let `unifi_network_monitor` hold `diagnostics: done`
across two clean IQS scans while leaking real identifiers.

The single most important property here is the **negative** one: no real
identifier from the input may appear anywhere in the serialized output. That is
asserted structurally, over the whole document, rather than key by key — a
key-by-key assertion can only find the leaks somebody already thought of.
"""

import json
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.huawei_router_5g.diagnostics import (
    REDACTED,
    async_get_config_entry_diagnostics,
)

# Every value below is something a real router returns and a maintainer must
# never receive. They are deliberately distinctive strings so a substring search
# over the whole output is conclusive.
SECRETS = [
    "secret_password",
    "admin",
    "860123456789012",  # IMEI
    "DC:71:96:11:22:33",  # router WAN MAC
    "AA:BB:CC:DD:EE:01",  # a client's MAC
    "Sams-iPhone",  # a client hostname — often a person's name
    "TheSmiths-5G",  # the household SSID
    "Neighbour-Guest",  # a third party's SSID
    "10.1.2.3",  # WAN IP
    "192.168.8.100",  # a client's LAN IP
    "8.8.8.8",
    "2001:db8::1",
    "+441234567890",  # an SMS sender — a third party
    "Your verification code is 998877",  # an SMS body
    "Three",  # carrier
    # --- added after the 2026-08-14 live-capture audit (§P-2) ----------------
    # Every one of these was published in full, or was covered only under a key
    # name the router never sends. None was caught by reading the module.
    "27203",  # Mccmnc — the operator, reached by a second key name
    "3 Ireland",  # Spn — the list said lowercase `spn`; the router sends `Spn`
    "40122",  # tac — serving tracking area, a metro-sized region
    "36199",  # scc_pci — secondary-carrier cell identifier
    "31337",  # sc — UMTS scrambling code, null on an LTE attach
    "hunter2WifiKey",  # WifiWpapsk — the household's WiFi password
    "wep0011223344",  # WifiWepKey1
]


def _payload() -> dict:
    """Return a realistic Huawei payload, including the blocks no sibling has."""
    return {
        "device_information": {
            "DeviceName": "B535s-232",
            "SoftwareVersion": "11.0.1.1(H192SP1C983)",
            "HardwareVersion": "Ver.A",
            "Imei": "860123456789012",
            "MacAddress1": "DC:71:96:11:22:33",
            "WanIPAddress": "10.1.2.3",
            "WanIPv6Address": "2001:db8::1",
            "uptime": "123456",
            "Mccmnc": "27203",
        },
        "monitoring_status": {
            "ConnectionStatus": "901",
            "SignalIcon": "4",
            "PrimaryDns": "8.8.8.8",
            "SecondaryDns": "8.8.4.4",
        },
        "device_signal": {
            "rsrp": "-95dBm",
            "sinr": "6dB",
            "cell_id": "5A6B3",
            # Populated on the live B535 and published in full.
            "tac": "40122",
            "scc_pci": "36199",
            # Null on an LTE/NR attach, populated on a 3G or GSM fallback.
            "sc": "31337",
        },
        "current_plmn": {
            "FullName": "Three",
            "ShortName": "3",
            "Numeric": "27205",
            "Spn": "3 Ireland",
        },
        # The device_tracker surface — no sibling project has this.
        "lan_host_info": {
            "Hosts": {
                "Host": [
                    {
                        "HostName": "Sams-iPhone",
                        "MacAddress": "AA:BB:CC:DD:EE:01",
                        "IpAddress": "192.168.8.100",
                        "Active": "1",
                        "AssociatedSsid": "TheSmiths-5G",
                    }
                ]
            }
        },
        "wlan_multi_basic_settings": {
            "Ssids": {
                "Ssid": [
                    {
                        "WifiSsid": "TheSmiths-5G",
                        "WifiEnable": "1",
                        # Null on the live capture, so a code reading passed
                        # over them. Null is a property of that firmware and
                        # auth level, not of the schema.
                        "WifiWpapsk": "hunter2WifiKey",
                        "WifiWepKey1": "wep0011223344",
                    },
                    {"WifiSsid": "Neighbour-Guest", "WifiEnable": "0"},
                ]
            }
        },
        "sms_list": {
            "Messages": {
                "Message": [
                    {
                        "Index": "1",
                        "Phone": "+441234567890",
                        "Content": "Your verification code is 998877",
                        "Date": "2026-08-09 10:00:00",
                    }
                ]
            }
        },
        # A key this module has never heard of, carrying an address — the case
        # the shape-based sweep exists for.
        "some_future_firmware_block": {
            "unknown_key": "gateway 192.168.8.100 via AA:BB:CC:DD:EE:01",
        },
    }


@pytest.fixture
def entry() -> ConfigEntry:
    """Build a config entry whose data and options both carry secrets."""
    e = MagicMock(spec=ConfigEntry)
    e.entry_id = "test_entry_id"
    e.title = "My Huawei Router"
    e.data = {
        "model": "B535s-232",
        "mac": "DC:71:96:11:22:33",
        "sw_version": "11.0.1.1",
    }
    e.options = {
        "host": "http://192.168.8.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret_password",
    }
    coordinator = MagicMock()
    coordinator.data = _payload()
    coordinator.consecutive_failures = 2
    coordinator.last_update_success = True
    coordinator.last_update_success_time = None
    coordinator.update_interval = None
    e.runtime_data = coordinator
    return e


async def _dump(entry: ConfigEntry) -> tuple[dict, str]:
    """Return the diagnostics document and its serialized form."""
    result = await async_get_config_entry_diagnostics(
        MagicMock(spec=HomeAssistant), entry
    )
    return result, json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# The property that matters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("secret", SECRETS)
async def test_no_real_identifier_survives_anywhere_in_the_document(entry, secret):
    """No input identifier may appear anywhere in the output.

    Parametrized so a failure names the exact value that leaked rather than
    reporting "something leaked". The search is over the **serialized** output,
    so it reaches nested lists and dicts a key-based check would miss — which
    is exactly how the previous implementation published every connected
    client's MAC, hostname and IP.
    """
    _, text = await _dump(entry)
    assert secret not in text


@pytest.mark.asyncio
async def test_an_address_under_an_unknown_key_is_still_scrubbed(entry):
    """The shape-based sweep is the part that survives a firmware update.

    A key list is never complete: new firmware adds keys, and anything under a
    key this module has not enumerated was previously published verbatim. This
    asserts the backstop catches an address embedded in free text under a key
    that does not exist anywhere in the module.
    """
    result, _ = await _dump(entry)
    swept = result["data"]["some_future_firmware_block"]["unknown_key"]

    assert "192.168.8.100" not in swept
    assert "AA:BB:CC:DD:EE:01" not in swept
    # The surrounding prose is preserved — the point is a readable file.
    assert swept.startswith("gateway ")


# ---------------------------------------------------------------------------
# The file has to stay useful
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_everything_diagnostically_useful_is_preserved(entry):
    """Redaction that removes the diagnosis is not a win.

    Model, firmware, signal metrics, connection status and coordinator health
    are the reason the file exists.
    """
    result, _ = await _dump(entry)
    dev = result["data"]["device_information"]

    assert dev["DeviceName"] == "B535s-232"
    assert dev["SoftwareVersion"] == "11.0.1.1(H192SP1C983)"
    assert dev["HardwareVersion"] == "Ver.A"
    assert dev["uptime"] == "123456"
    assert result["data"]["device_signal"]["rsrp"] == "-95dBm"
    assert result["data"]["monitoring_status"]["ConnectionStatus"] == "901"
    assert result["coordinator"]["consecutive_failures"] == 2
    assert result["coordinator"]["last_update_success"] is True
    assert result["entry"]["title"] == "My Huawei Router"


@pytest.mark.asyncio
async def test_the_same_identifier_gets_the_same_token_across_the_document(entry):
    """Stable pseudonyms, not twenty identical `**REDACTED**` strings.

    The household SSID appears in three places — the client's
    `AssociatedSsid` and both WiFi entries. A maintainer must be able to see
    that they are the same network; that is the whole reason tokens beat
    blanking here.
    """
    result, _ = await _dump(entry)

    associated = result["data"]["lan_host_info"]["Hosts"]["Host"][0]["AssociatedSsid"]
    ssids = result["data"]["wlan_multi_basic_settings"]["Ssids"]["Ssid"]

    assert associated == ssids[0]["WifiSsid"]
    assert associated != ssids[1]["WifiSsid"], (
        "two different SSIDs collapsed to one token"
    )
    assert associated.startswith("ssid-")


@pytest.mark.asyncio
async def test_sms_keeps_its_shape_and_loses_its_content(entry):
    """An SMS-handling bug turns on length and structure, not on the words.

    The body is the highest-sensitivity content in the payload — data about a
    third party who never consented to appear in a bug report.
    """
    result, _ = await _dump(entry)
    msg = result["data"]["sms_list"]["Messages"]["Message"][0]

    assert msg["Index"] == "1"
    assert msg["Date"] == "2026-08-09 10:00:00"
    assert msg["Content"] == "<Content: 32 chars>"
    assert msg["Phone"].startswith("phone-")


@pytest.mark.asyncio
async def test_credentials_and_subscriber_identifiers_are_blanked_not_tokenized(entry):
    """A password has no cross-reference value, so it is blanked outright."""
    result, _ = await _dump(entry)

    assert result["entry"]["options"][CONF_PASSWORD] == REDACTED
    assert result["entry"]["options"][CONF_USERNAME] == REDACTED
    assert result["data"]["device_information"]["Imei"] == REDACTED
    assert result["data"]["current_plmn"]["FullName"] == REDACTED


# ---------------------------------------------------------------------------
# Read-path safety and edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnostics_never_mutates_the_live_payload(entry):
    """Diagnostics is a read path (Section 20).

    Sanitizing in place would replace the values the entities are currently
    serving from — a download would blank the user's actual sensor states.
    """
    before = json.dumps(entry.runtime_data.data, default=str)
    await _dump(entry)
    assert json.dumps(entry.runtime_data.data, default=str) == before


@pytest.mark.asyncio
async def test_diagnostics_with_no_data_yet(entry):
    """A download before the first successful poll must not raise."""
    entry.runtime_data.data = None
    result, _ = await _dump(entry)

    assert result["data"] == {}
    assert result["coordinator"]["data_available"] is False


@pytest.mark.asyncio
async def test_empty_and_non_string_values_pass_through_untouched(entry):
    """Sanitizing must not coerce types or invent values.

    Guard bands, counters and booleans are numbers, and an absent field is
    often `None` or `""`. Turning any of those into a token would make the file
    unreadable and could hide a real "this field came back empty" symptom.
    """
    entry.runtime_data.data = {
        "block": {
            "WanIPAddress": "",
            "HostName": None,
            "count": 42,
            "enabled": True,
            "ratio": 1.5,
        }
    }
    result, _ = await _dump(entry)
    block = result["data"]["block"]

    assert block["WanIPAddress"] == ""
    assert block["HostName"] is None
    assert block["count"] == 42
    assert block["enabled"] is True
    assert block["ratio"] == 1.5


@pytest.mark.asyncio
async def test_a_semicolon_separated_address_list_is_tokenized_per_address(entry):
    """Huawei returns several addresses in one field, semicolon-separated.

    Tokenizing the whole string as one value would produce a single opaque
    token and lose the fact that there were two addresses — and a naive
    implementation that only handled the single-address case would leak the
    second one.
    """
    entry.runtime_data.data = {
        "lan_host_info": {
            "Hosts": {"Host": [{"IpAddress": "192.168.8.100;192.168.8.101"}]}
        }
    }
    result, text = await _dump(entry)
    value = result["data"]["lan_host_info"]["Hosts"]["Host"][0]["IpAddress"]

    assert "192.168.8.100" not in text
    assert "192.168.8.101" not in text
    first, second = value.split(";")
    assert first.startswith("ip-")
    assert second.startswith("ip-")
    assert first != second


# ---------------------------------------------------------------------------
# The sweep must not corrupt what it does not understand
# ---------------------------------------------------------------------------
#
# Both cases below were found by this suite failing against a first-draft
# sweep, not by review. They are kept because the shapes genuinely collide:
# a four-part firmware version parses as an IPv4 address, and a `HH:MM:SS`
# timestamp parses as a short IPv6.


# ---------------------------------------------------------------------------
# Findings from the live-capture audit, 2026-08-14 (§P-2)
# ---------------------------------------------------------------------------
#
# The global SECRETS sweep above already fails if any of these regress. These
# four exist as well because a named test says *what* was wrong and why the
# code reading did not find it, which a substring sweep cannot.
#
# The shared lesson: every one of these sat next to a correctly-handled field.
# That is the same shape as the unifi_network_monitor precedent.


@pytest.mark.asyncio
async def test_the_operator_is_redacted_under_both_key_names(entry):
    """`Mccmnc` is `current_plmn.Numeric` reached by a second key name.

    The module redacted `Numeric` and published `Mccmnc` in full. Combined with
    a tracking area it resolves to a mast in open databases, and it is the
    single field that names the subscriber's carrier and country.
    """
    result, _ = await _dump(entry)
    assert result["data"]["device_information"]["Mccmnc"] == REDACTED
    assert result["data"]["current_plmn"]["Numeric"] == REDACTED


@pytest.mark.asyncio
async def test_a_key_listed_under_the_wrong_case_is_still_redacted(entry):
    """`Spn` was listed as lowercase `spn`, which no router sends.

    It was null in the capture, so the output looked clean. A miss of this
    shape is invisible until the one router that populates the field files a
    bug report — the failure mode the module docstring warns about.
    """
    result, _ = await _dump(entry)
    assert result["data"]["current_plmn"]["Spn"] == REDACTED


@pytest.mark.asyncio
async def test_area_and_neighbour_cell_identifiers_are_tokenized(entry):
    """`tac` and `scc_pci` were published while `cell_id` beside them was not.

    Tokenized rather than blanked: whether two readings share a serving cell is
    genuinely diagnostic for a signal fault, and the token preserves that.
    """
    signal = (await _dump(entry))[0]["data"]["device_signal"]

    for key in ("tac", "scc_pci", "sc", "cell_id"):
        assert signal[key].startswith("cell-"), key
    # ...and the untouched half of the block is still readable.
    assert signal["rsrp"] == "-95dBm"


@pytest.mark.asyncio
async def test_wifi_key_material_is_blanked(entry):
    """`WifiWpapsk` is the household's WiFi password.

    Null on the live B535 and therefore invisible in the capture, but null
    there is a property of that firmware and auth level, not of the schema.
    Blanked, not tokenized — a key has no cross-reference worth keeping.
    """
    ssid = (await _dump(entry))[0]["data"]["wlan_multi_basic_settings"]["Ssids"][
        "Ssid"
    ][0]

    assert ssid["WifiWpapsk"] == REDACTED
    assert ssid["WifiWepKey1"] == REDACTED
    assert ssid["WifiEnable"] == "1"


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_firmware_version_is_not_mistaken_for_an_ip_address(entry):
    """`11.0.1.1(H192SP1C983)` is a firmware version, not an address.

    A first-draft sweep rewrote it as `ip-1(H192SP1C983)`, which destroys the
    single most useful field in the file — the version is usually the first
    thing anyone asks for.
    """
    result, _ = await _dump(entry)
    assert (
        result["data"]["device_information"]["SoftwareVersion"]
        == "11.0.1.1(H192SP1C983)"
    )


@pytest.mark.asyncio
async def test_a_timestamp_is_not_mistaken_for_an_ipv6_address(entry):
    """`2026-08-09 10:00:00` is a date, not an address.

    A first-draft IPv6 pattern matched the `10:00:00` as three hex groups and
    rewrote it as `ip6-1`, which would make every SMS and every log timestamp
    in the file unreadable.
    """
    result, _ = await _dump(entry)
    msg = result["data"]["sms_list"]["Messages"]["Message"][0]
    assert msg["Date"] == "2026-08-09 10:00:00"


@pytest.mark.asyncio
async def test_an_out_of_range_dotted_number_is_not_an_ip_address(entry):
    """`999.1.2.3` cannot be an address, so it must survive intact.

    Octet bounds are what separates a real address from an arbitrary dotted
    number, and an unbounded pattern would tokenize firmware build numbers and
    signal readings alike.
    """
    entry.runtime_data.data = {"block": {"some_value": "build 999.1.2.3 ok"}}
    result, _ = await _dump(entry)
    assert result["data"]["block"]["some_value"] == "build 999.1.2.3 ok"


@pytest.mark.asyncio
async def test_a_real_ipv6_address_in_free_text_is_still_caught(entry):
    """Narrowing the IPv6 rule must not have disarmed it.

    The two forms that matter are the `::` elision and the full eight-group
    address; both must still be swept out of a string under an unknown key.
    """
    entry.runtime_data.data = {
        "block": {
            "elided": "route via 2001:db8::1 ok",
            "full": "route via 2001:0db8:0000:0000:0000:0000:0000:0001 ok",
        }
    }
    result, text = await _dump(entry)

    assert "2001:db8::1" not in text
    assert "2001:0db8:0000:0000:0000:0000:0000:0001" not in text
    assert result["data"]["block"]["elided"].startswith("route via ip6-")


# ---------------------------------------------------------------------------
# Mutation findings, recommendations_20260815.md
#
# Everything above asserts a **negative** — that no input identifier survives
# into the output. That is the property that matters most, and it is not
# sufficient on its own: deleting every address satisfies it, and so does
# collapsing every MAC in the document to a single token. Section 20 requires
# pseudonymization rather than blanking, and says in terms that a sanitizer
# which guts the file has failed as surely as one that leaks. These assert
# what the sanitizer *produces*.
# ---------------------------------------------------------------------------


def _two_client_payload() -> dict:
    """Return a payload with two clients and an unenumerated free-text key."""
    payload = _payload()
    payload["lan_host_info"]["Hosts"]["Host"].append(
        {
            "HostName": "Erins-Laptop",
            "MacAddress": "AA:BB:CC:DD:EE:02",
            "IpAddress": "192.168.8.101",
            "Active": "1",
        }
    )
    # A routable address, deliberately — every existing fixture uses an RFC1918
    # one, and the private-range half of the rule would otherwise cover for the
    # branch under test. The MAC is hyphen-separated for the same reason: the
    # regex accepts both and only the colon form appears above.
    payload["another_future_block"] = {
        "some_key": "peer AA-BB-CC-DD-EE-03 reached 8.8.4.4 ok",
    }
    return payload


@pytest.mark.asyncio
async def test_identifiers_are_replaced_by_tokens_not_merely_removed(entry):
    """Section 20: pseudonymize, do not blank.

    Covers finding DIAG.1 from recommendations_20260815.md.

    Sixteen mutants survived on this one gap, including replacing the sweep's
    substitution with a function returning `None` — which does **not** raise,
    it deletes the match. The output would read "peer  reached  ok" and every
    existing assertion would still pass, because every existing assertion is
    about what is absent.
    """
    entry.runtime_data.data = _two_client_payload()
    result, dumped = await _dump(entry)

    block = result["data"]["another_future_block"]["some_key"]

    # The identifiers are gone — and something stands in their place.
    assert "AA-BB-CC-DD-EE-03" not in dumped
    assert "8.8.4.4" not in dumped
    assert "mac-" in block, f"the MAC was removed rather than tokenized: {block!r}"
    assert "ip-" in block, f"the address was removed rather than tokenized: {block!r}"
    # The surrounding prose must survive, or the file is useless to a reader.
    assert block.startswith("peer ")
    assert block.endswith(" ok")


@pytest.mark.asyncio
async def test_two_different_identifiers_get_two_different_tokens(entry):
    """The converse of the stability test, and the one that was missing.

    Covers finding DIAG.1 from recommendations_20260815.md.
    `test_the_same_identifier_gets_the_same_token_across_the_document` is
    satisfied trivially when *everything* yields the same token — which is
    exactly what `tokenizer.token("mac", None)` produces, and it survived.
    """
    entry.runtime_data.data = _two_client_payload()
    result, _ = await _dump(entry)

    hosts = result["data"]["lan_host_info"]["Hosts"]["Host"]
    macs = [h["MacAddress"] for h in hosts]
    names = [h["HostName"] for h in hosts]

    assert len(set(macs)) == 2, f"both clients share one MAC token: {macs}"
    assert len(set(names)) == 2, f"both clients share one name token: {names}"
    # The prefix is what makes the document readable; nothing checked it.
    assert all(m.startswith("mac-") for m in macs), macs
    assert all(n.startswith("name-") for n in names), names


@pytest.mark.asyncio
async def test_a_list_of_bare_strings_keeps_its_key(entry):
    """The key is what routes a value; the list branch can drop it.

    Covers finding DIAG.3 from recommendations_20260815.md. Every list in the
    fixtures held dicts, whose own keys are then used, so dropping the key
    when recursing into a list was invisible.

    A name is the right probe: it has no shape, so the structural sweep cannot
    rescue it and the test isolates key propagation.
    """
    payload = _payload()
    payload["some_block_with_a_name_list"] = {"HostName": ["Sams-iPhone", "Erins-Pad"]}
    entry.runtime_data.data = payload

    result, dumped = await _dump(entry)

    names = result["data"]["some_block_with_a_name_list"]["HostName"]
    assert "Erins-Pad" not in dumped
    assert all(n.startswith("name-") for n in names), names


@pytest.mark.asyncio
async def test_the_entry_data_section_is_present_and_sanitized(entry):
    """The whole `data` section could become None with the suite green.

    Covers finding RETVAL.1 from recommendations_20260815.md. `entry.data` is
    where the Flat Identity pattern keeps the model and firmware version — the
    fields a maintainer reads first — and nothing asserted the section existed.
    """
    result, dumped = await _dump(entry)

    data = result["entry"]["data"]
    assert data is not None
    assert data["model"] == "B535s-232"
    assert data["sw_version"] == "11.0.1.1"
    assert "DC:71:96:11:22:33" not in dumped
    assert data["mac"].startswith("mac-")

    coordinator = result["coordinator"]
    assert coordinator["consecutive_failures"] == 2
    assert "last_update_success_time" in coordinator
    assert "update_interval_seconds" in coordinator


@pytest.mark.asyncio
async def test_an_empty_value_under_a_redacted_key_stays_empty(entry):
    """`**REDACTED**` in place of nothing tells the reader a value was there.

    Covers finding ERR.1 from recommendations_20260815.md. The guard runs only
    under a `TO_REDACT` or carrier key, and the existing empty-value test does
    not use one.
    """
    payload = _payload()
    payload["device_information"]["Imei"] = ""
    payload["current_plmn"]["Spn"] = None
    entry.runtime_data.data = payload

    result, _ = await _dump(entry)

    assert result["data"]["device_information"]["Imei"] == ""
    assert result["data"]["current_plmn"]["Spn"] is None
