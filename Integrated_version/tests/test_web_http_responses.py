from http import HTTPStatus
from io import BytesIO
import json
import unittest

from Integrated_version.web.http_responses import send_bytes, send_json


class ResponseRecorder:
    def __init__(self) -> None:
        self.status = None
        self.headers: dict[str, str] = {}
        self.wfile = BytesIO()

    def send_response(self, status: HTTPStatus) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers[key] = value

    def end_headers(self) -> None:
        pass


class HttpResponseTests(unittest.TestCase):
    def test_json_response_is_utf8_and_not_cached(self) -> None:
        handler = ResponseRecorder()
        send_json(handler, {"message": "繁體中文"}, HTTPStatus.CREATED)

        body = handler.wfile.getvalue()
        self.assertEqual(handler.status, HTTPStatus.CREATED)
        self.assertEqual(handler.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(handler.headers["Content-Length"], str(len(body)))
        self.assertEqual(handler.headers["Cache-Control"], "no-store")
        self.assertIn("繁體中文", body.decode("utf-8"))
        self.assertEqual(json.loads(body), {"message": "繁體中文"})

    def test_byte_response_preserves_content_type_and_body(self) -> None:
        handler = ResponseRecorder()
        payload = b"\x00\xff"
        send_bytes(handler, payload, "application/octet-stream")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(handler.headers["Content-Length"], str(len(payload)))
        self.assertEqual(handler.wfile.getvalue(), payload)


if __name__ == "__main__":
    unittest.main()
