#!/usr/bin/env python3
"""Run a safe API smoke check against a running FIKRAH backend."""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from typing import Any

import httpx
from dotenv import load_dotenv


class SmokeCheckError(RuntimeError):
    pass


class ApiSmokeCheck:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self.passed = 0
        self.project_id: str | None = None
        self.note_id: str | None = None
        self.conversation_id: str | None = None
        self.refresh_token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: int,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        label: str | None = None,
    ) -> httpx.Response:
        response = self.client.request(method, path, json=json, headers=headers)
        name = label or f"{method.upper()} {path}"
        if response.status_code != expected:
            detail = response.text[:500].replace("\n", " ")
            raise SmokeCheckError(
                f"{name}: expected HTTP {expected}, got {response.status_code}: {detail}"
            )
        self.passed += 1
        print(f"PASS {name} ({response.status_code})")
        return response

    def cleanup(self) -> None:
        for path in (
            f"/v1/conversations/{self.conversation_id}" if self.conversation_id else None,
            f"/v1/notes/{self.note_id}" if self.note_id else None,
            f"/v1/projects/{self.project_id}" if self.project_id else None,
        ):
            if path is None:
                continue
            try:
                response = self.client.delete(path)
                if response.status_code not in (204, 404):
                    print(
                        f"WARN cleanup {path}: HTTP {response.status_code}",
                        file=sys.stderr,
                    )
            except httpx.HTTPError as error:
                print(f"WARN cleanup failed: {error}", file=sys.stderr)

        if self.refresh_token:
            try:
                response = self.client.post(
                    "/v1/auth/logout", json={"refresh_token": self.refresh_token}
                )
                if response.status_code not in (200, 401):
                    print(
                        f"WARN logout: HTTP {response.status_code}", file=sys.stderr
                    )
            except httpx.HTTPError as error:
                print(f"WARN logout failed: {error}", file=sys.stderr)
        self.client.close()


def run_smoke_check(
    *, base_url: str, email: str, password: str, timeout: float, with_llm: bool
) -> int:
    check = ApiSmokeCheck(base_url, timeout)
    try:
        check.request("GET", "/health", expected=200)
        check.request("GET", "/v1/projects", expected=401)

        login = check.request(
            "POST",
            "/v1/auth/login",
            expected=200,
            json={"email": email, "password": password},
        ).json()
        access_token = login["access_token"]
        check.refresh_token = login["refresh_token"]
        check.client.headers["Authorization"] = f"Bearer {access_token}"
        check.request("GET", "/v1/auth/me", expected=200)

        projects = check.request("GET", "/v1/projects", expected=200).json()
        general_project = next(
            (project for project in projects if project.get("is_general")), None
        )
        if general_project is None:
            raise SmokeCheckError("GET /v1/projects: protected General project missing")
        check.passed += 1
        print("PASS General project is present and protected")

        project = check.request(
            "POST",
            "/v1/projects",
            expected=201,
            json={"name": f"API smoke {uuid.uuid4().hex[:8]}"},
        ).json()
        check.project_id = project["id"]
        project_path = f"/v1/projects/{check.project_id}"
        check.request("GET", project_path, expected=200)
        check.request(
            "PATCH",
            project_path,
            expected=200,
            json={"name": f"API smoke renamed {uuid.uuid4().hex[:8]}"},
        )
        check.request("GET", f"{project_path}/notes", expected=200)

        note = check.request(
            "POST",
            f"{project_path}/notes",
            expected=201,
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={"content": "Temporary API smoke note for endpoint verification."},
        ).json()
        check.note_id = note["id"]
        note_path = f"/v1/notes/{check.note_id}"
        check.request("GET", note_path, expected=200)
        check.request(
            "PATCH",
            note_path,
            expected=200,
            json={"content": "Updated temporary API smoke note."},
        )

        if with_llm:
            note = wait_for_note_processing(check, note_path, timeout=timeout)
            if note.get("processing_status") != "completed":
                raise SmokeCheckError(
                    "Note processing did not complete; inspect worker logs and LLM settings"
                )
            check.request("GET", f"{note_path}/connections", expected=200)
            check.request("GET", f"{project_path}/knowledge-graph", expected=200)
            check.request(
                "POST",
                f"{project_path}/search",
                expected=200,
                json={"query": "temporary API smoke note", "limit": 5},
            )

        check.request("GET", f"{project_path}/conversations", expected=200)
        conversation = check.request(
            "POST",
            f"{project_path}/conversations",
            expected=201,
            json={"title": "API smoke conversation"},
        ).json()
        check.conversation_id = conversation["id"]
        conversation_path = f"/v1/conversations/{check.conversation_id}"
        check.request("GET", conversation_path, expected=200)

        if with_llm:
            check.request(
                "POST",
                f"{conversation_path}/messages",
                expected=200,
                json={"content": "What does my temporary smoke note say?"},
            )
            check.request("GET", conversation_path, expected=200)

        refreshed = check.request(
            "POST",
            "/v1/auth/refresh",
            expected=200,
            json={"refresh_token": check.refresh_token},
        ).json()
        check.refresh_token = refreshed["refresh_token"]
        check.client.headers["Authorization"] = f"Bearer {refreshed['access_token']}"
        check.request(
            "GET",
            "/v1/auth/me",
            expected=200,
            label="GET /v1/auth/me after refresh",
        )

        check.request("DELETE", conversation_path, expected=204)
        check.conversation_id = None
        check.request("DELETE", note_path, expected=204)
        check.note_id = None
        check.request("DELETE", project_path, expected=204)
        check.project_id = None

        check.request(
            "POST",
            "/v1/auth/logout",
            expected=200,
            json={"refresh_token": check.refresh_token},
        )
        check.refresh_token = None

        print(f"\nAPI smoke check passed: {check.passed} checks")
        if not with_llm:
            print(
                "LLM-dependent note processing, connections, graph, semantic search, "
                "and chat-message checks were skipped. Re-run with --with-llm to include them."
            )
        return 0
    except (httpx.HTTPError, KeyError, SmokeCheckError) as error:
        print(f"\nAPI smoke check failed: {error}", file=sys.stderr)
        return 1
    finally:
        check.cleanup()


def wait_for_note_processing(
    check: ApiSmokeCheck, note_path: str, *, timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = check.client.get(note_path)
        if response.status_code != 200:
            raise SmokeCheckError(
                f"GET {note_path}: expected HTTP 200, got {response.status_code}"
            )
        note = response.json()
        state = note.get("processing_status")
        if state in {"completed", "failed"}:
            check.passed += 1
            print(f"PASS note processing reached terminal state: {state}")
            return note
        time.sleep(2)
    raise SmokeCheckError(
        f"Note processing did not finish within {timeout:g} seconds"
    )


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Exercise FIKRAH API endpoints using a disposable project and note."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("FIKRAH_API_BASE_URL", "http://localhost:8000"),
        help="API root URL (default: FIKRAH_API_BASE_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("FIKRAH_SMOKE_EMAIL"),
        help="Verified test account email",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("FIKRAH_SMOKE_PASSWORD"),
        help="Verified test account password",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90,
        help="Request and processing timeout in seconds (default: 90)",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help=(
            "Also test processing, connections, knowledge graph, semantic search, "
            "and chat messages"
        ),
    )
    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error(
            "Set FIKRAH_SMOKE_EMAIL and FIKRAH_SMOKE_PASSWORD, or pass --email and --password."
        )
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    return run_smoke_check(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        timeout=args.timeout,
        with_llm=args.with_llm,
    )


if __name__ == "__main__":
    raise SystemExit(main())
