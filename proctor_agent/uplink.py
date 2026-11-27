"""Minimal HTTP client for the local advisory proctoring agent.

The token lives only in this process and is never written to output or logs.
"""

import json
import mimetypes
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class UplinkError(RuntimeError):
    pass


class UplinkClient:
    def __init__(self, server, token, timeout=10):
        self.server = server.rstrip("/")
        self._token = token
        self.timeout = timeout

    def _headers(self, content_type=None):
        headers = {"Authorization": f"Bearer {self._token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request(self, path, body=None, content_type="application/json", method="POST", raw=False):
        request = Request(
            f"{self.server}{path}", data=body, method=method, headers=self._headers(content_type)
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                return payload if raw else json.loads(payload.decode("utf-8"))
        except (HTTPError, URLError, ValueError) as error:
            raise UplinkError("The server did not accept the advisory data.") from error

    def post_event(self, event_type, severity, details=None):
        payload = json.dumps(
            {"event_type": event_type, "severity": severity, "details": details or {}}
        ).encode("utf-8")
        return self._request("/api/proctoring/events/", payload)

    def post_baseline(self, devices):
        return self._request("/api/proctoring/baseline/", json.dumps({"devices": devices}).encode("utf-8"))

    def fetch_profile_photo(self):
        return self._request("/api/proctoring/profile-photo/", content_type=None, method="GET", raw=True)

    def post_clip(self, event_id, clip_path):
        clip_path = str(clip_path)
        with open(clip_path, "rb") as evidence:
            data = evidence.read()
        boundary = f"----proctor-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(clip_path)[0] or "application/octet-stream"
        body = b"".join((
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="event_id"\r\n\r\n', str(event_id).encode(), b"\r\n",
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="clip"; filename="evidence.mp4"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(), data, b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ))
        return self._request("/api/proctoring/clips/", body, f"multipart/form-data; boundary={boundary}")
