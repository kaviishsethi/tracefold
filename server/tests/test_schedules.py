"""Optional scheduled checks: re-run a scan on a schedule, from a private copy of the uploaded files."""
import stat

from .conftest import fx

WS = "/v1/workspaces/ws_a"


def schedule(env, scan_id, who="app", **kw):
    return env.client.post(f"{WS}/schedules", headers=env.h(who), json={"scan_id": scan_id, "every": "day", "public": False, **kw})


def first_scan(env):
    inp = env.upload({"risky_app.py": fx("risky_app.py")})
    return env.scan(inp["input_id"], model_review=False)


def test_scheduled_scan_reruns_from_a_private_copy(env):
    s = first_scan(env)
    r = schedule(env, s["scan_id"])
    assert r.status_code == 201, r.text
    sch = r.json()
    assert sch["files"] == ["risky_app.py"] and sch["every"] == "day" and sch["runs"] == 0
    copy = env.engine.settings.data_dir / "schedule_files" / sch["schedule_id"] / "000"
    assert copy.read_bytes() == fx("risky_app.py") and stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert env.engine.schedules.run_due() == 0                         # not due yet

    env.engine.registry._caps.clear()                                   # what a restart does
    r = env.client.patch(f"{WS}/schedules/{sch['schedule_id']}", headers=env.h(), json={"run_now": True})
    assert r.status_code == 200 and r.json()["runs"] == 1 and r.json()["last_error"] is None
    new_scan = r.json()["last_scan_id"]
    assert new_scan != s["scan_id"]
    env.engine.runner.run_pending()
    first = {f["finding_id"] for f in env.findings(s["scan_id"])}
    again = {f["finding_id"] for f in env.findings(new_scan)}
    assert first and first == again                                     # same file, same findings
    assert env.engine.schedules.run_due() == 0                         # next run is a day away


def test_runs_do_not_stack_and_pausing_stops_them(env):
    s = first_scan(env)
    sid = schedule(env, s["scan_id"]).json()["schedule_id"]
    env.client.patch(f"{WS}/schedules/{sid}", headers=env.h(), json={"run_now": True})     # queued, not run yet
    env.engine.repo.update_monitor(sid, next_run_at="2000-01-01T00:00:00Z")
    assert env.engine.schedules.run_due() == 0                         # previous run still queued
    env.engine.runner.run_pending()
    env.client.patch(f"{WS}/schedules/{sid}", headers=env.h(), json={"enabled": False})
    env.engine.repo.update_monitor(sid, next_run_at="2000-01-01T00:00:00Z")
    assert env.engine.schedules.run_due() == 0                         # paused


def test_only_configure_clients_schedule_and_delete_removes_the_copy(env):
    s = first_scan(env)
    assert schedule(env, s["scan_id"], who="cloud").status_code == 403
    sid = schedule(env, s["scan_id"]).json()["schedule_id"]
    folder = env.engine.settings.data_dir / "schedule_files" / sid
    assert folder.is_dir()
    assert env.client.delete(f"{WS}/schedules/{sid}", headers=env.h()).status_code == 204
    assert not folder.exists() and env.client.get(f"{WS}/schedules", headers=env.h()).json()["items"] == []


def test_exact_interval_and_start_time(env):
    from datetime import datetime, timedelta, timezone
    s = first_scan(env)
    start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
    r = schedule(env, s["scan_id"], every=None, interval_seconds=90, start_at=start.isoformat())
    assert r.status_code == 201, r.text
    sch = r.json()
    assert sch["interval_seconds"] == 90 and sch["every"] == "custom"
    assert sch["next_run_at"].startswith(start.strftime("%Y-%m-%dT%H:%M"))       # first run at the chosen time
    # A start in the past rolls forward to the next slot on its cadence.
    past = (datetime.now(timezone.utc) - timedelta(seconds=200)).replace(microsecond=0)
    r = env.client.patch(f"{WS}/schedules/{sch['schedule_id']}", headers=env.h(), json={"start_at": past.isoformat()})
    nxt = datetime.fromisoformat(r.json()["next_run_at"].replace("Z", "+00:00"))
    assert timedelta(0) < nxt - datetime.now(timezone.utc) <= timedelta(seconds=90)
    assert ((nxt - past).total_seconds()) % 90 == 0
    assert schedule(env, s["scan_id"], every=None, interval_seconds=5).status_code == 422   # under 10 seconds
