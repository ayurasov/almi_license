"""End-to-end scenarios of stage 1 with the real DL module (E16-04, prompt I5-01).

Each scenario prepares its data through the Admin API of the stand; the steps are in the
docstrings (they go to the HTML report). Criteria of section 15.6 of document 1 are mapped in
docs/traceability.md.
"""

from pathlib import Path

from conftest import new_device
from stand import Device, Stand

OK = "result: 0"


def test_online_activation_check_release_and_another_device(
    stand: Stand, device: Device, tmp_path: Path
) -> None:
    """1. Online.
    - activate the key on computer 1: FULL, one seat taken;
    - check: a new lease;
    - deactivate: the seat is free;
    - activate the same key on computer 2: FULL; computer 1 stays in the trial.
    """
    lic = stand.license(limit=1, enforcement="enforce")
    assert OK in device.run("activate", lic["key"])
    assert device.status()["mode"] == "FULL"
    assert OK in device.run("check")
    assert [a["status"] for a in stand.activations(lic["license_id"])] == ["active"]

    assert OK in device.run("deactivate")
    assert device.status()["mode"] == "TRIAL"
    other = new_device(stand, tmp_path / "pc-2")
    assert OK in other.run("activate", lic["key"])
    assert other.status()["mode"] == "FULL"
    statuses = sorted(a["status"] for a in stand.activations(lic["license_id"]))
    assert statuses == ["active", "released"]

    # Criterion 11: the statistics of the licence.
    [row] = stand.api("GET", f"stats?customer_id={lic['customer_id']}")["rows"]
    assert (row["limit"], row["active"], row["free"]) == (1, 1, 0)
    assert row["by_version"] == {"lm-demo": 1} and row["last_seen_at"]

    # Criterion 5: no server — the product keeps working by its lease.
    unreachable = Device(other.binary, other.data, "https://localhost:9", other.home)
    assert "result: -3" in unreachable.run("check")
    assert unreachable.status()["mode"] == "FULL"


def test_offline_activation_through_the_portal(
    stand: Stand, device: Device, tmp_path: Path
) -> None:
    """2. Offline.
    - the computer without network writes .alk-req;
    - the portal /api/v1/offline/requests answers with .alk-lic;
    - the module applies it: FULL, the activation is marked offline;
    - release by file: the receipt is applied, the seat is free.
    """
    lic = stand.license(enforcement="enforce")
    request = tmp_path / "ws.alk-req"
    assert OK in device.run("offline-request", lic["key"], str(request))
    answer = stand.upload("/api/v1/offline/requests", "ws.alk-req", request.read_bytes())
    assert answer.status == 200, answer.body
    (tmp_path / "ws.alk-lic").write_bytes(answer.body)
    assert OK in device.run("apply", str(tmp_path / "ws.alk-lic"))
    assert device.status()["mode"] == "FULL"
    [activation] = stand.activations(lic["license_id"])
    assert activation["offline"] is True

    release = tmp_path / "release.alk-req"
    assert OK in device.run("release-request", str(release))
    receipt = stand.upload("/api/v1/offline/requests", "release.alk-req", release.read_bytes())
    assert receipt.status == 200, receipt.body
    (tmp_path / "release.alk-lic").write_bytes(receipt.body)
    assert OK in device.run("apply", str(tmp_path / "release.alk-lic"))
    assert device.status()["mode"] == "TRIAL"
    assert [a["status"] for a in stand.activations(lic["license_id"])] == ["released"]


def test_auto_release_and_activation_again(stand: Stand, device: Device) -> None:
    """5. Automatic release.
    - activate; the stand moves release_after_days + 1 (31 days) ahead;
    - the worker releases the activation: released_auto;
    - the product checks: 410, activates again by itself, FULL with a new activation.
    """
    lic = stand.license(enforcement="enforce")
    assert OK in device.run("activate", lic["key"])
    first = device.status()["activation_id"]
    stand.hourly_tasks(31)
    assert [a["status"] for a in stand.activations(lic["license_id"])] == ["released_auto"]
    assert OK in device.run("check", days=31)
    status = device.status(days=31)
    assert status["mode"] == "FULL"
    assert status["activation_id"] != first
    assert sorted(a["status"] for a in stand.activations(lic["license_id"])) == [
        "active",
        "released_auto",
    ]


def test_policy_states_and_renewal(stand: Stand, device: Device) -> None:
    """6. Policy (enforce): NOTICE → GRACE → RESTRICTED → renewal → ACTIVE.
    - a licence until today + 40 days; activate: FULL;
    - +15 days: NOTICE (30 days of notice); +45 days: GRACE (14 days); +60 days: RESTRICTED;
    - the operator renews the licence for a year; the next check gives FULL again.
    """
    lic = stand.license(valid_days=40, enforcement="enforce")
    assert OK in device.run("activate", lic["key"])
    assert device.status()["mode"] == "FULL"
    for days, mode in ((15, "NOTICE"), (45, "GRACE"), (60, "LIMITED (RESTRICTED)")):
        stand.shift(days)
        assert OK in device.run("check", days=days)
        assert device.status(days=days)["mode"] == mode, days
    renewed = stand.now().replace(microsecond=0) + __import__("datetime").timedelta(days=365)
    stand.api("POST", f"licenses/{lic['license_id']}/renew", {"valid_until": renewed.isoformat()})
    assert OK in device.run("check", days=60)
    assert device.status(days=60)["mode"] == "FULL"


def test_monitor_mode_does_not_restrict(stand: Stand, device: Device) -> None:
    """7. monitor: the licence is past its term, functions are not restricted, messages are shown.
    - a licence in monitor mode until today + 10 days; activate;
    - +60 days (past the grace): the state is RESTRICTED, but the module works as FULL;
    - the messages of the state are shown.
    """
    lic = stand.license(valid_days=10, enforcement="monitor")
    assert OK in device.run("activate", lic["key"])
    stand.shift(60)
    assert OK in device.run("check", days=60)
    status = device.status(days=60)
    assert status["monitor"].startswith("1"), status
    assert "edit" in device.run("features", days=60)
    assert device.run("messages", days=60).strip()


def test_trial_reinstall_and_clock(stand: Stand, device: Device, tmp_path: Path) -> None:
    """8. Trial: 30 days, a reinstall does not start it again, a clock moved back does not help.
    - a new installation: TRIAL, 30 days;
    - +31 days: the trial is over (UNLICENSED);
    - the data of the product is deleted (reinstall): still no new trial;
    - the clock is moved back to day 5: still no trial.
    """
    status = device.status()
    assert (status["mode"], status["trial_days_left"]) == ("TRIAL", "30")
    assert device.status(days=31)["mode"].startswith("SOFT_BLOCK")
    reinstalled = Device(device.binary, tmp_path / "reinstalled", device.server, device.home)
    assert reinstalled.status(days=31)["mode"].startswith("SOFT_BLOCK")
    assert reinstalled.status(days=5)["mode"].startswith("SOFT_BLOCK")


COMPAT = Path(__file__).resolve().parents[2] / "server" / "tests" / "compat"


def shape(value: object) -> object:
    """Field names and types of a JSON answer: the values depend on the data of the stand."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    return type(value).__name__


def test_compatibility_fixtures_against_the_stand(stand: Stand) -> None:
    """9. AlterOffice Web and AlterOS by the compatibility fixtures, over HTTPS of the stand.
    - the subscription of a Web instance: the answer has the fields and types of the fixture;
    - an unknown key: 404 as the fixture;
    - registration.sh: a node activated (JSON), the same node again, a second node.
    """
    import json
    from urllib.parse import urlencode

    web = stand.license(product="alteroffice-web", enforcement="enforce")
    active = json.loads((COMPAT / "nextcloud" / "subscription-active.json").read_text())
    path = active["request"]["path"].replace("{key}", web["key"])
    reply = stand.request("POST", path, active["request"]["body"])
    assert reply.status == active["response"]["status"], reply.body
    assert shape(reply.json()) == shape(active["response"]["body"])
    missing = json.loads((COMPAT / "nextcloud" / "subscription-not-found.json").read_text())
    unknown = missing["request"]["path"].replace("{key}", "2611-AAAA-BBBB-CCCC")
    assert (
        stand.request("POST", unknown, missing["request"]["body"]).status
        == (missing["response"]["status"])
    )

    node = stand.license(product="alteros", limit=2, enforcement="enforce")
    for name in ("activated-json", "already-json", "second-json"):
        fixture = json.loads((COMPAT / "registration" / f"{name}.json").read_text())
        sent = fixture["request"]
        fields = {
            k: v.replace("{key}", node["key"])
            for k, v in sent.get("query", sent.get("form", {})).items()
        }
        if sent["method"] == "GET":
            reply = stand.request("GET", "/api/activate/?" + urlencode(fields))
        else:
            reply = stand.request(
                "POST",
                "/api/activate/",
                raw=urlencode(fields).encode(),
                content_type="application/x-www-form-urlencoded",
                headers={"Accept": sent.get("accept", "text/html")},
            )
        assert reply.status == fixture["response"]["status"], (name, reply.body)
        assert shape(reply.json()) == shape(fixture["response"]["json"]), name


def _local_server_for(stand: Stand, seats: int = 2) -> tuple[dict[str, str], str]:
    """A licence on the central server and a local server of its customer with seats of it."""
    lic = stand.license(limit=5, enforcement="enforce")
    issued = stand.api(
        "POST",
        "local-servers",
        {
            "customer_id": lic["customer_id"],
            "name": "ЦОД заказчика",
            "allocations": {lic["license_id"]: seats},
        },
    )
    return lic, issued["code"]


def test_local_server_with_outgoing_access(
    stand: Stand, local_server: Stand, tmp_path: Path
) -> None:
    """3. Local server with outgoing access.
    - the operator creates a local server with 2 seats; its administrator runs the wizard online;
    - the package arrives at once; a sync asks for a newer one;
    - a computer activates against the local server: FULL (the lease of the local server key);
    - the third computer gets no seat (2 seats of the package, reserve ceil(2 * 3 %) = 1);
    - the usage report goes to the central server and comes back with a receipt.
    """
    lic, code = _local_server_for(stand)
    setup = local_server.api("POST", "setup", {"registration_code": code, "central_url": stand.url})
    assert (setup["status"]["registered"], setup["status"]["package_seq"]) == (True, 1)
    assert local_server.api("POST", "package/sync")["package_seq"] == 1

    devices = [new_device(local_server, tmp_path / f"pc-{n}") for n in range(4)]
    results = [d.run("activate", lic["key"]).splitlines()[0] for d in devices]
    assert results == [OK, OK, OK, "result: -2"], results  # 2 seats + 1 reserve, then no seat
    assert devices[0].status()["mode"] == "FULL"

    from stand import manage

    sent = manage(
        local_server.env,
        "shell",
        "-c",
        "from apps.packages.domain import send_report; from infra.clock import current_clock;"
        " print(send_report(now=current_clock().now()))",
    )
    assert sent.strip().splitlines()[-1] == "1"
    status = local_server.api("GET", "setup")
    assert (status["report_seq"], status["receipt_seq"]) == (1, 1)
    rows = stand.api("GET", f"stats?customer_id={lic['customer_id']}")["rows"]
    assert rows[0]["local_active"] == 3


def test_closed_network_local_server(stand: Stand, local_server: Stand, tmp_path: Path) -> None:
    """4. Closed network: everything by files.
    - the wizard without a central URL gives the registration request .alk-req;
    - the operator loads it on the central server and gets the package .alk;
    - the package is loaded on the local server; a computer activates: FULL;
    - the usage report .alk-usage is saved and loaded on the central server: a receipt.
    """
    import json

    lic, code = _local_server_for(stand)
    setup = local_server.api("POST", "setup", {"registration_code": code})
    request = json.dumps(setup["request_file"]).encode()
    package = stand.upload("/api/admin/local-servers/register-file", "server.alk-req", request)
    assert package.status == 200, package.body
    loaded = local_server.upload("/api/admin/package", "server.alk", package.body)
    assert loaded.status == 200, loaded.body
    assert loaded.json()["package_seq"] == 1

    device = new_device(local_server, tmp_path / "pc")
    assert OK in device.run("activate", lic["key"])
    assert device.status()["mode"] == "FULL"

    report = local_server.request("POST", "/api/admin/usage-report")
    assert report.status == 200, report.body
    receipt = stand.upload("/api/admin/local-servers/usage-file", "report.alk-usage", report.body)
    assert receipt.status == 200, receipt.body
    assert receipt.json()["report_seq"] == 1


def test_logs_hold_no_keys_or_leases(stand: Stand, device: Device) -> None:
    """14. The log of the stand after the scenarios: no licence key, lease or signature.
    - one more activation and check; the log of the server is read in full;
    - neither the key, nor the lease, nor the request signature of the device is there.
    """
    lic = stand.license(enforcement="enforce")
    assert OK in device.run("activate", lic["key"])
    assert OK in device.run("check")
    log = stand.log.read_text(encoding="utf-8", errors="replace")
    assert lic["key"] not in log
    assert lic["key"].replace("-", "") not in log
    assert "eyJhbGciOiJFZERTQSI" not in log  # the header of every lease and certificate
    assert "sig=" not in log
