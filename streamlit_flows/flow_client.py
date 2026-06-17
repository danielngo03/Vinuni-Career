from __future__ import annotations

import json
import mimetypes
import time
import uuid
from urllib import error, parse, request

from flow_log import add_log


def get_json(api_base: str, path: str, params: dict | None = None, token: str | None = None) -> dict:
    endpoint = build_endpoint(path, params)
    add_log("api_request", method="GET", endpoint=endpoint, input_user=params or {})
    req = request.Request(
        f"{api_base}{endpoint}",
        headers=auth_headers(token),
        method="GET",
    )
    return read_response(req, endpoint)


def post_json(api_base: str, path: str, payload: dict, token: str | None = None) -> dict:
    add_log("api_request", method="POST", endpoint=path, input_user=payload)
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{api_base}{path}",
        data=body,
        headers={"Content-Type": "application/json", **auth_headers(token)},
        method="POST",
    )
    return read_response(req, path)


def patch_json(api_base: str, path: str, payload: dict, token: str | None = None) -> dict:
    add_log("api_request", method="PATCH", endpoint=path, input_user=payload)
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{api_base}{path}",
        data=body,
        headers={"Content-Type": "application/json", **auth_headers(token)},
        method="PATCH",
    )
    return read_response(req, path)


def delete_json(api_base: str, path: str, token: str | None = None) -> dict:
    add_log("api_request", method="DELETE", endpoint=path, input_user={})
    req = request.Request(
        f"{api_base}{path}",
        headers=auth_headers(token),
        method="DELETE",
    )
    return read_response(req, path)


def post_upload(
    api_base: str,
    path: str,
    file_name: str,
    content: bytes,
    token: str | None = None,
) -> dict:
    add_log(
        "api_request",
        method="POST",
        endpoint=path,
        input_user={"file_name": file_name, "file_size": len(content)},
    )
    boundary = f"----c2flow{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{file_name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            content,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    req = request.Request(
        f"{api_base}{path}",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **auth_headers(token),
        },
        method="POST",
    )
    return read_response(req, path)


def read_response(req: request.Request, path: str) -> dict:
    started_at = time.perf_counter()
    try:
        with request.urlopen(req, timeout=20) as response:
            raw_body = response.read().decode("utf-8")
            data = json.loads(raw_body)
            add_log(
                "api_response",
                endpoint=path,
                status=response.status,
                duration_ms=_duration_ms(started_at),
                answer=data,
            )
            return data
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        message = f"{exc.code} {exc.reason}: {detail}"
        add_log(
            "api_error",
            endpoint=path,
            status=exc.code,
            duration_ms=_duration_ms(started_at),
            error=message,
        )
        raise RuntimeError(message) from exc
    except error.URLError as exc:
        message = f"Cannot reach backend: {exc.reason}"
        add_log(
            "api_error",
            endpoint=path,
            status=None,
            duration_ms=_duration_ms(started_at),
            error=message,
        )
        raise RuntimeError(message) from exc


def _duration_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


def auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token.strip()}"}


def build_endpoint(path: str, params: dict | None = None) -> str:
    clean_params = {
        key: value
        for key, value in (params or {}).items()
        if value not in (None, "", [])
    }
    if not clean_params:
        return path
    return f"{path}?{parse.urlencode(clean_params)}"
