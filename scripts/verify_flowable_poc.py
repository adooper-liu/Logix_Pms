"""Run the isolated synthetic Flowable POC only; never connects to PMS."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import tempfile
import time
import uuid
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


def utc_now():
    return dt.datetime.now(dt.UTC).isoformat()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("UTC timestamp required for restart evidence")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required for restart evidence")
    return parsed.timestamp()


def validate_restart(state, info, timer=None):
    if not info.get("boot_id") or info["boot_id"] == state.get("boot_id"):
        raise ValueError("A different process boot is required; no restart verified")
    stop = state.get("stop_evidence", {})
    if (
        stop.get("project") != "logix-flowable-poc"
        or stop.get("service") != "runner"
        or stop.get("running") is not False
        or not stop.get("container_id")
    ):
        raise ValueError("Observed stopped POC container evidence required")
    try:
        prepared = timestamp(state["prepared_at"])
        finished = timestamp(stop["finished_at"])
        observed = timestamp(stop["observed_at"])
        due = timestamp(state["timer_due_at"])
        boot = timestamp(info["boot_started_at"])
        if not prepared <= finished <= observed < due < boot:
            raise ValueError("Timer must expire between observed stop and new boot")
        if timer is not None and timestamp(timer["completed_at"]) < boot:
            raise ValueError("Timer completed before the new boot")
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete restart evidence") from exc


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def wait_for(read, predicate, timeout=40):
    deadline = time.monotonic() + timeout
    last = None
    while True:
        last = read()
        if predicate(last):
            return last
        if time.monotonic() >= deadline:
            raise TimeoutError(f"POC deadline expired; last state: {last}")
        time.sleep(min(0.15, max(0, deadline - time.monotonic())))


def save_state(path, state, *, exclusive=False):
    encoded = json.dumps(state, indent=2)
    if any(key in encoded.lower() for key in ('"token"', '"password"', '"authorization"')):
        raise ValueError("Credentials must not enter probe state")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".poc-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # mkstemp is owner-only on POSIX; Windows access inherits the local directory ACL.
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


AMBIGUOUS = (
    URLError,
    TimeoutError,
    ConnectionError,
    HTTPException,
    json.JSONDecodeError,
    UnicodeDecodeError,
)


class Client:
    def __init__(self, url, token, revision, journal_dir=None):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port in {None, 8123}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Explicit loopback POC URL required; PMS port is forbidden")
        if len(token) < 32 or not revision or revision == "unknown":
            raise ValueError("Dedicated token and expected build revision required")
        self.url = url.rstrip("/") + "/poc/v1"
        self.token = token
        self.revision = revision
        self.journal_dir = (
            Path(journal_dir) if journal_dir is not None else Path("var/flowable-poc/commands")
        )
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(
            self.url + path,
            data=data,
            method=method,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        with self.opener.open(req, timeout=15) as response:
            return json.load(response)

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload):
        return self.request("POST", path, payload)

    def check_identity(self):
        info = self.get("/info")
        if info.get("poc") is not True or info.get("build_revision") != self.revision:
            raise ValueError("Refusing unknown POC service or stale build")
        return info

    def command_path(self, command_id):
        return self.journal_dir / (str(uuid.UUID(command_id)) + ".json")

    def persist_command(self, command):
        record = {"url": self.url, "revision": self.revision, "request": command}
        path = self.command_path(command["command_id"])
        try:
            save_state(path, record, exclusive=True)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != record:
                raise ValueError(
                    "Refusing different request or service for existing command_id"
                ) from None

    def checked_receipt(self, receipt, command):
        if (
            not isinstance(receipt, dict)
            or receipt.get("command_id") != command["command_id"]
            or not isinstance(receipt.get("result"), dict)
        ):
            raise ValueError("Invalid POC command receipt")
        return receipt

    def lookup_or_retry(self, command):
        try:
            return self.checked_receipt(self.get("/commands/" + command["command_id"]), command)
        except HTTPError as query:
            if query.code != 404:
                raise
        return self.checked_receipt(self.post("/commands", command), command)

    def submit(self, command):
        self.persist_command(command)
        try:
            return self.checked_receipt(self.post("/commands", command), command)
        except AMBIGUOUS as exc:
            if isinstance(exc, HTTPError) and exc.code < 500:
                raise
        try:
            return self.lookup_or_retry(command)
        except AMBIGUOUS + (ValueError,):
            raise RuntimeError(
                f"POC outcome unknown; command_id={command['command_id']}; "
                "request retained in command journal; recover the original ID, never create a replacement"
            ) from None

    def recover(self, command_id):
        record = json.loads(self.command_path(command_id).read_text(encoding="utf-8"))
        if record["url"] != self.url or record["revision"] != self.revision:
            raise ValueError("Command journal belongs to a different POC service/build")
        command = record["request"]
        if command["command_id"] != command_id:
            raise ValueError("Command journal identity mismatch")
        try:
            return self.lookup_or_retry(command)
        except AMBIGUOUS + (ValueError,):
            raise RuntimeError(
                f"POC recovery unresolved; command_id={command_id}; journal retained"
            ) from None

    def command(self, action, target, payload):
        return self.submit(
            {
                "command_id": str(uuid.uuid4()),
                "action": action,
                "target": target,
                "payload": payload,
            }
        )["result"]

    def events(self, cursor, seen):
        fresh = []
        known = set(seen)
        while True:
            page = self.get(f"/events?after_id={cursor}&limit=100")
            next_cursor = page["next_after_id"]
            for event in page["events"]:
                if event["event_id"] not in known:
                    fresh.append(event)
                    known.add(event["event_id"])
            if not page["has_more"]:
                return fresh, next_cursor
            if next_cursor <= cursor:
                raise ValueError("Event cursor did not progress")
            cursor = next_cursor

    def instance(self, instance_id):
        return self.get("/instances/" + instance_id)

    def complete(self, task):
        actor = task["assignee"] or task["candidates"][0]
        return self.command("COMPLETE", task["task_id"], {"actor": actor})


def before(client, path):
    if Path(path).exists():
        raise ValueError("State file exists; use a new file for a new run")
    info = client.check_identity()
    if not info.get("boot_id") or not info.get("boot_started_at"):
        raise ValueError("Current runner boot identity required")
    run_id = str(uuid.uuid4())
    definitions = {}
    for fixture in client.get("/fixtures"):
        result = client.command("DEPLOY", fixture["name"], {"bpmn_sha256": fixture["bpmn_sha256"]})
        definitions[fixture["name"]] = result["definition_id"]

    def start(fixture, case, variables=None):
        return {
            "command_id": str(uuid.uuid4()),
            "action": "START",
            "target": definitions[fixture],
            "payload": {
                "business_key": f"poc:{run_id}:{case}",
                "context": {
                    "source": "POC_FIXTURE",
                    "process_id": 910001,
                    "model_version_id": 910001,
                    "project_id": None,
                    "round_id": None,
                },
                "variables": variables or {},
            },
        }

    serial = client.submit(start("serial", "serial"))["result"]["instance_id"]
    task = client.instance(serial)["tasks"][0]
    client.command("CLAIM", task["task_id"], {"actor": "poc-applicant"})
    client.complete(client.instance(serial)["tasks"][0])
    assert client.instance(serial)["status"] == "COMPLETED"
    print("OK serial claim/complete")

    parallel = client.submit(start("parallel-signoff", "parallel"))["result"]["instance_id"]
    tasks = client.instance(parallel)["tasks"]
    assert len(tasks) == 2
    client.complete(tasks[0])
    assert len(client.instance(parallel)["tasks"]) == 1
    client.complete(client.instance(parallel)["tasks"][0])
    reviews = client.instance(parallel)["tasks"]
    assert len(reviews) == 2 and all(t["activity_id"] == "review" for t in reviews)
    client.complete(reviews[0])
    assert client.instance(parallel)["status"] == "RUNNING"
    client.complete(client.instance(parallel)["tasks"][0])
    assert client.instance(parallel)["status"] == "COMPLETED"
    print("OK parallel join/all-reviewers")

    message = client.submit(start("message-timer", "message", {"waitDuration": "PT60S"}))["result"][
        "instance_id"
    ]
    client.command("MESSAGE", message, {"message_name": "PocResponse"})
    assert client.instance(message)["outcome"] == "MESSAGE"
    print("OK message branch")

    pending_command = start("serial", "restart-task")
    pending = client.submit(pending_command)["result"]["instance_id"]
    timer_command = start("message-timer", "restart-timer", {"waitDuration": "PT60S"})
    timer = client.submit(timer_command)["result"]["instance_id"]
    timer_view = client.instance(timer)
    if (
        timer_view["status"] != "RUNNING"
        or timer_view.get("timer_jobs") != 1
        or not timer_view.get("timer_due_at")
        or timer_view.get("completed_at") is not None
    ):
        raise ValueError("Before phase requires one pending actual timer")
    events, cursor = client.events(0, set())
    state = {
        "boot_id": info["boot_id"],
        "boot_started_at": info["boot_started_at"],
        "timer_due_at": timer_view["timer_due_at"],
        "prepared_at": utc_now(),
        "run_id": run_id,
        "revision": client.revision,
        "pending_id": pending,
        "timer_id": timer,
        "pending_command": pending_command,
        "timer_command": timer_command,
        "cursor": cursor,
        "seen": [e["event_id"] for e in events],
    }
    if timestamp(state["prepared_at"]) >= timestamp(state["timer_due_at"]):
        raise ValueError("Timer already due before state preparation; use a new experiment")
    save_state(path, state, exclusive=True)
    print("OK prepared persistent task/timer; stop runner before timer deadline")


def after(client, path):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    if state["revision"] != client.revision:
        raise ValueError("State belongs to a different build")
    info = client.check_identity()
    validate_restart(state, info)
    timer = wait_for(
        lambda: client.instance(state["timer_id"]),
        lambda x: x["status"] == "COMPLETED",
        timeout=100,
    )
    validate_restart(state, info, timer)
    assert timer["outcome"] == "TIMEOUT" and timer["deadletter_jobs"] == 0
    original = client.submit(state["pending_command"])["result"]["instance_id"]
    assert original == state["pending_id"]
    instance = client.instance(original)
    assert instance["status"] == "RUNNING", "Use a fresh before phase for each restart experiment"
    client.complete(instance["tasks"][0])
    assert client.instance(original)["status"] == "COMPLETED"
    assert client.submit(state["timer_command"])["result"]["instance_id"] == state["timer_id"]
    fresh, cursor = client.events(state["cursor"], set(state["seen"]))
    assert any(
        e.get("engine_instance_id") == original and e["type"] == "TASK_COMPLETED" for e in fresh
    )
    replay, _ = client.events(0, set())
    timer_ends = [
        e
        for e in replay
        if e.get("engine_instance_id") == state["timer_id"] and e["type"] == "PROCESS_COMPLETED"
    ]
    assert len(timer_ends) == 1
    duplicates, _ = client.events(0, {e["event_id"] for e in replay})
    assert not duplicates
    state["after_cursor"] = cursor
    state["after_boot_id"] = info["boot_id"]
    state["after_boot_started_at"] = info["boot_started_at"]
    state["timer_completed_at"] = timer["completed_at"]
    state["verified"] = True
    save_state(path, state)
    print("OK persisted task/timer, original-command replay, event continuation/full replay dedup")


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / "var/flowable-poc/empty.env"),
    "-f",
    str(ROOT / "engine/flowable-runner/compose.poc.yml"),
    "-p",
    "logix-flowable-poc",
]


def docker_call(arguments):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(
            "Isolated POC Docker operation failed; inspect local Docker status (secrets suppressed)"
        )
    return result.stdout.strip()


def runner_state(container_id=None):
    if container_id is None:
        container_id = docker_call(COMPOSE + ["ps", "-a", "-q", "runner"])
    if not container_id or "\n" in container_id:
        raise ValueError("Exactly one isolated POC runner required")
    template = (
        '{"container_id":{{json .Id}},"image":{{json .Image}},'
        '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
        '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
        '"running":{{json .State.Running}},"finished_at":{{json .State.FinishedAt}},'
        '"started_at":{{json .State.StartedAt}}}'
    )
    observed = json.loads(docker_call(["docker", "inspect", "--format", template, container_id]))
    if observed["project"] != "logix-flowable-poc" or observed["service"] != "runner":
        raise ValueError("Refusing non-POC runner container")
    observed["observed_at"] = docker_call(["docker", "info", "--format", "{{.SystemTime}}"])
    return observed


def controlled_restart(client, path, mode):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    info = client.check_identity()
    if state["revision"] != client.revision or state["boot_id"] != info["boot_id"]:
        raise ValueError("Before state must belong to the current runner boot")
    timer = client.instance(state["timer_id"])
    if (
        timer["status"] != "RUNNING"
        or timer.get("timer_jobs") != 1
        or timer.get("completed_at") is not None
        or timer.get("timer_due_at") != state["timer_due_at"]
        or timestamp(state["timer_due_at"]) <= time.time()
    ):
        raise ValueError("A pending, not-yet-due timer is required; use a new before state")
    current = runner_state()
    if not current["running"]:
        raise ValueError("POC runner is not running")
    if timestamp(info["boot_started_at"]) < timestamp(current["started_at"]):
        raise ValueError("API boot does not belong to the current POC container")
    stopped = False
    try:
        docker_call(COMPOSE + ["stop", "runner"])
        stopped = True
        stop = runner_state(current["container_id"])
        state["stop_evidence"] = stop
        save_state(path, state)
        if stop["running"] or not (
            timestamp(state["prepared_at"])
            <= timestamp(stop["finished_at"])
            <= timestamp(stop["observed_at"])
            < timestamp(state["timer_due_at"])
        ):
            raise ValueError(
                "Runner did not stop before actual timer deadline; restart not verified"
            )
        if mode == "stack":
            docker_call(COMPOSE + ["down"])  # Never -v: retain the original database volume.
        time.sleep(max(0, timestamp(state["timer_due_at"]) - timestamp(stop["observed_at"]) + 2))
    finally:
        if stopped:
            docker_call(
                COMPOSE
                + (
                    ["up", "-d", "--wait", "--wait-timeout", "180"]
                    if mode == "stack"
                    else ["start", "--wait", "runner"]
                )
            )
    started = runner_state()
    if not started["running"] or started["image"] != current["image"]:
        raise ValueError("Current runner image/state changed during restart")
    state["restart_container"] = started
    save_state(path, state)
    after(client, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--journal-dir", type=Path)
    parser.add_argument(
        "--recover-command", help="Query the original durable command, retry same ID only on404"
    )
    parser.add_argument(
        "--phase", choices=["before-restart", "after-restart", "restart-runner", "restart-stack"]
    )
    args = parser.parse_args()
    if not args.recover_command and (args.state_file is None or args.phase is None):
        parser.error("--state-file and --phase required unless recovering a command")
    client = Client(
        args.url, os.environ.get("FLOWABLE_POC_TOKEN", ""), args.expected_revision, args.journal_dir
    )
    print(json.dumps(client.check_identity(), ensure_ascii=False))
    if args.recover_command:
        print(json.dumps(client.recover(args.recover_command)))
    elif args.phase == "before-restart":
        before(client, args.state_file)
    elif args.phase == "after-restart":
        after(client, args.state_file)
    else:
        controlled_restart(
            client, args.state_file, "stack" if args.phase == "restart-stack" else "runner"
        )


if __name__ == "__main__":
    main()
