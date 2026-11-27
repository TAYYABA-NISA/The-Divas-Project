"""Minimal standard-library HTTP client for the local proctoring agent."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class UplinkError(RuntimeError):
    pass


class UplinkClient:
    def __init__(self, server, token, timeout=10):
        self.server = server.rstrip("/")
        self._token = token
        self.timeout = timeout

    def _request(self, path, body, content_type="application/json"):
        request = Request(
            f"{self.server}{path}",
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": content_type},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, ValueError) as error:
            raise UplinkError("The server did not accept the advisory event.") from error

    def post_event(self, event_type, severity, details=None):
        payload = json.dumps(
            {"event_type": event_type, "severity": severity, "details": details or {}}
        ).encode("utf-8")
        return self._request("/api/proctoring/events/", payload)

    def post_baseline(self, devices):
        return self._request("/api/proctoring/baseline/", json.dumps({"devices": devices}).encode("utf-8"))
