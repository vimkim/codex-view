import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from conftest import append, record


def read_event(stream):
    event = {}
    while True:
        line = stream.readline().decode().strip()
        if not line and event:
            return event
        if line.startswith("event:"):
            event["event"] = line[6:].strip()
        elif line.startswith("data:"):
            event["data"] = json.loads(line[5:])


def test_direct_host_static_files_and_read_only_routes(running_viewer):
    url, _, server = running_viewer
    assert server.server_address[0] == "0.0.0.0"
    request = Request(url + "/api/session", headers={"Host": "vpn-server.example:8765"})
    with urlopen(request) as response:
        data = json.load(response)
    assert data["title"] == "Teach me probability"
    assert len(data["messages"]) == 2
    with urlopen(url + "/mathjax/tex-svg.js") as response:
        assert len(response.read()) > 100000
    for path in ("/server.py", "/api/sessions", "/mathjax/%2e%2e/%2e%2e/cli.py"):
        try:
            urlopen(url + path)
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError(path)
    try:
        urlopen(Request(url + "/api/session", data=b"write", method="POST"))
    except HTTPError as error:
        assert error.code == 501
    else:
        raise AssertionError("POST should not write")


def test_sse_snapshot_append_reconnect_and_reset(running_viewer):
    url, path, _ = running_viewer
    with urlopen(url + "/api/events", timeout=3) as stream:
        initial = read_event(stream)
        assert initial["event"] == "snapshot"
        append(path, record("New live answer"))
        update = read_event(stream)
        assert update["event"] == "append"
        assert len(update["data"]["messages"]) == 1
        assert "New live answer" in update["data"]["messages"][0]["html"]
        replacement = path.with_suffix(".new")
        append(replacement, record("Replacement log"))
        replacement.replace(path)
        reset = read_event(stream)
        assert reset["event"] == "snapshot"
        assert len(reset["data"]["messages"]) == 1
    with urlopen(
        Request(url + "/api/events", headers={"Last-Event-ID": "999999"}), timeout=3
    ) as stream:
        reconnect = read_event(stream)
        assert reconnect["event"] == "snapshot"
        assert "Replacement log" in reconnect["data"]["messages"][0]["html"]
