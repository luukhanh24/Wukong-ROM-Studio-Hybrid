from __future__ import annotations

import unittest

from tools.dccloud_bootstrap import exchange_password_for_refresh_token


class _Response:
    status_code = 200

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class DCloudBootstrapTests(unittest.TestCase):
    def test_password_exchange_returns_only_refresh_token(self) -> None:
        calls: list[dict[str, object]] = []

        def request(method: str, url: str, **kwargs: object) -> _Response:
            calls.append({"method": method, "url": url, **kwargs})
            return _Response(
                {
                    "code": 0,
                    "data": {
                        "user": {"id": "user"},
                        "token": {
                            "access_token": "short-lived",
                            "refresh_token": "long-lived",
                        },
                    },
                }
            )

        token = exchange_password_for_refresh_token(
            "https://cloud.example",
            "user@example.com",
            "password",
            request=request,
        )
        self.assertEqual("long-lived", token)
        self.assertEqual(
            {"email": "user@example.com", "password": "password"},
            calls[0]["json"],
        )

    def test_password_exchange_reports_only_sanitized_login_error(self) -> None:
        def request(*_: object, **__: object) -> _Response:
            return _Response({"code": 401, "msg": "Incorrect password or email address"})

        with self.assertRaisesRegex(SystemExit, r"code 401.*Incorrect password"):
            exchange_password_for_refresh_token(
                "https://cloud.example",
                "user@example.com",
                "secret-not-in-error",
                request=request,
            )


if __name__ == "__main__":
    unittest.main()
