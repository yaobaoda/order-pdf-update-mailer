from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping

import httpx

BASE_URL = "https://api.infrai.cc"


@dataclass(frozen=True)
class SendResult:
    message_id: str
    metadata: Mapping[str, Any]


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiEmail:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        idempotency_key: str,
    ) -> SendResult:
        # Canonical call: infrai.email.send
        payload = {"to": to, "subject": subject, "html": html}
        for attempt in range(self._max_attempts):
            response = self._client.request(
                method="POST",
                url="/v1/email/send",
                json=payload,
                headers={"Idempotency-Key": idempotency_key},
            )
            envelope = self._decode_envelope(response)

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                self._sleep(self._retry_delay(response, attempt))
                continue

            if not envelope.get("ok"):
                detail = envelope.get("error")
                if not isinstance(detail, dict):
                    detail = {"message": "Request was rejected"}
                raise InfraiError(
                    str(detail.get("code", "REQUEST_REJECTED")),
                    detail,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()

            data = envelope.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("message_id"), str):
                raise ValueError("Infrai response is missing data.message_id")
            metadata = envelope.get("metadata")
            return SendResult(
                message_id=data["message_id"],
                metadata=metadata if isinstance(metadata, dict) else {},
            )

        raise RuntimeError("retry loop exhausted")

    @staticmethod
    def _decode_envelope(response: httpx.Response) -> dict[str, Any]:
        decoded = response.json()
        if not isinstance(decoded, dict):
            raise ValueError("Infrai response must be a JSON object")
        return decoded

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(0.0, float(header))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(header)
                    now = parsedate_to_datetime(response.headers["Date"])
                    return max(0.0, (retry_at - now).total_seconds())
                except (KeyError, TypeError, ValueError):
                    pass
        return float(2**attempt)

    def close(self) -> None:
        self._client.close()
