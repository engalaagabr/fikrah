#!/usr/bin/env python3
"""Interactively call FIKRAH API endpoints one at a time."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

import httpx
from dotenv import load_dotenv

SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "id_token",
    "password",
    "refresh_token",
    "token",
}


class EndpointTester:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)
        self.access_token = os.getenv("FIKRAH_API_ACCESS_TOKEN")
        self.refresh_token: str | None = None

    def close(self) -> None:
        self.client.close()

    def test(
        self,
        method: str,
        path: str,
        expected_status: int,
        body: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bool:
        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        headers.update(extra_headers or {})

        url = f"{self.base_url}{path}"
        print(f"\n→ {method} {url}")
        try:
            body = replace_token_placeholders(
                body,
                access_token=self.access_token,
                refresh_token=self.refresh_token,
            )
        except ValueError as error:
            print(f"FAIL {error}")
            return False
        try:
            response = self.client.request(method, url, headers=headers, json=body)
        except httpx.HTTPError as error:
            print(f"FAIL request error: {error}")
            return False

        status_result = "PASS" if response.status_code == expected_status else "FAIL"
        print(
            f"{status_result} expected HTTP {expected_status}; "
            f"received HTTP {response.status_code}"
        )

        payload = parse_response(response)
        if isinstance(payload, dict):
            access_token = payload.get("access_token")
            refresh_token = payload.get("refresh_token")
            if isinstance(access_token, str):
                self.access_token = access_token
                print("Saved access token in memory for the next request.")
            if isinstance(refresh_token, str):
                self.refresh_token = refresh_token
                print("Saved refresh token in memory for the next request.")

        if response.content:
            print("Response:")
            print(json.dumps(redact(payload), indent=2, ensure_ascii=False))
        else:
            print("Response: <empty>")
        return response.status_code == expected_status


def parse_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "<redacted>" if key.lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def replace_token_placeholders(
    value: Any, *, access_token: str | None, refresh_token: str | None
) -> Any:
    tokens = {
        "@access_token": access_token,
        "@refresh_token": refresh_token,
    }
    if isinstance(value, str) and value in tokens:
        token = tokens[value]
        if token is None:
            raise ValueError(f"{value} is not available in this session")
        return token
    if isinstance(value, list):
        return [
            replace_token_placeholders(
                item, access_token=access_token, refresh_token=refresh_token
            )
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: replace_token_placeholders(
                item, access_token=access_token, refresh_token=refresh_token
            )
            for key, item in value.items()
        }
    return value


def resolve_schema(schema: dict[str, Any], openapi: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/components/"):
        return schema
    value: Any = openapi
    for segment in reference.removeprefix("#/").split("/"):
        value = value[segment]
    return value if isinstance(value, dict) else schema


def describe_schema(
    schema: dict[str, Any], openapi: dict[str, Any], *, depth: int = 0
) -> list[str]:
    schema = resolve_schema(schema, openapi)
    if depth > 5:
        return ["  " * depth + "…"]
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return [f"  " * depth + schema.get("type", "object")]

    required = set(schema.get("required", []))
    lines: list[str] = []
    for name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            continue
        property_schema = resolve_schema(property_schema, openapi)
        marker = "required" if name in required else "optional"
        property_type = property_schema.get("type", "object")
        description = property_schema.get("description")
        suffix = f" — {description}" if description else ""
        lines.append(
            f"  " * depth + f"{name}: {property_type} ({marker}){suffix}"
        )
        if property_schema.get("properties"):
            lines.extend(
                describe_schema(property_schema, openapi, depth=depth + 1)
            )
    return lines or ["  " * depth + schema.get("type", "object")]


def request_body_schema(
    operation: dict[str, Any], openapi: dict[str, Any]
) -> dict[str, Any] | None:
    request_body = operation.get("requestBody", {})
    if "$ref" in request_body:
        request_body = resolve_schema(request_body, openapi)
    content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
    json_content = content.get("application/json", {})
    schema = json_content.get("schema") if isinstance(json_content, dict) else None
    return schema if isinstance(schema, dict) else None


def body_is_required(operation: dict[str, Any], openapi: dict[str, Any]) -> bool:
    request_body = operation.get("requestBody", {})
    if isinstance(request_body, dict) and "$ref" in request_body:
        request_body = resolve_schema(request_body, openapi)
    return bool(request_body.get("required")) if isinstance(request_body, dict) else False


def expected_status_default(operation: dict[str, Any]) -> int:
    for code in operation.get("responses", {}):
        if code.isdigit() and 200 <= int(code) < 300:
            return int(code)
    return 200


def endpoint_catalog(openapi: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    endpoints: list[tuple[str, str, dict[str, Any]]] = []
    for path, operations in openapi.get("paths", {}).items():
        for method, operation in operations.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                endpoints.append((method.upper(), path, operation))
    return sorted(endpoints, key=lambda item: (item[1], item[0]))


def fill_path(path: str) -> str:
    for parameter in re.findall(r"{([^}]+)}", path):
        value = input(f"Enter {parameter}: ").strip()
        if not value:
            raise ValueError(f"A value is required for {parameter}")
        path = path.replace("{" + parameter + "}", quote(value, safe=""))
    query = input("Query string (without '?', blank for none): ").strip()
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        path = f"{path}?{urlencode(pairs)}"
    return path


def collect_body(
    operation: dict[str, Any], openapi: dict[str, Any]
) -> Any:
    required = body_is_required(operation, openapi)
    schema = request_body_schema(operation, openapi)
    if schema is None:
        return None

    print("Request JSON fields:")
    for line in describe_schema(schema, openapi):
        print(line)
    while True:
        raw_body = input("JSON body (blank for no body): ").strip()
        if not raw_body:
            if required:
                print("This endpoint requires a JSON body.")
                continue
            return None
        try:
            value = json.loads(raw_body)
        except json.JSONDecodeError as error:
            print(f"Invalid JSON: {error}")
            continue
        if not isinstance(value, (dict, list, str, int, float, bool)) and value is not None:
            print("Enter a valid JSON value.")
            continue
        return value


def collect_headers(operation: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "header":
            continue
        name = parameter.get("name")
        if not name:
            continue
        required = parameter.get("required", False)
        while True:
            answer = input(
                f"Header {name}{' (required)' if required else ''}: "
            ).strip()
            if not required or answer:
                break
            print(f"Header {name} is required.")
        if answer:
            headers[name] = answer

    while True:
        extra = input("Additional headers as JSON object (blank for none): ").strip()
        if not extra:
            break
        try:
            values = json.loads(extra)
        except json.JSONDecodeError as error:
            print(f"Invalid header JSON: {error}")
            continue
        if not isinstance(values, dict) or not all(
            isinstance(name, str) and isinstance(value, str)
            for name, value in values.items()
        ):
            print("Headers must be a JSON object with string names and values.")
            continue
        headers.update(values)
        break
    return headers


def choose_endpoint(
    endpoints: list[tuple[str, str, dict[str, Any]]]
) -> int | None:
    print("\nFIKRAH API endpoints")
    for index, (method, path, operation) in enumerate(endpoints, start=1):
        summary = operation.get("summary", "")
        print(f"{index:2}. {method:6} {path}  {summary}")
    selection = input("\nChoose endpoint number (q to quit): ").strip().lower()
    if selection in {"q", "quit", "exit"}:
        return None
    try:
        index = int(selection)
    except ValueError:
        print("Enter a number from the list, or q to quit.")
        return -1
    if not 1 <= index <= len(endpoints):
        print("That endpoint number is not in the list.")
        return -1
    return index - 1


def run_interactive(tester: EndpointTester, openapi: dict[str, Any]) -> int:
    endpoints = endpoint_catalog(openapi)
    successes = 0
    failures = 0
    while True:
        selected = choose_endpoint(endpoints)
        if selected is None:
            break
        if selected < 0:
            continue

        method, template, operation = endpoints[selected]
        description = operation.get("description")
        if description:
            print(f"\n{description}")
        if operation.get("security", openapi.get("security", [])):
            if not tester.access_token:
                tester.access_token = getpass.getpass(
                    "Bearer access token (input hidden): "
                ).strip()
                if not tester.access_token:
                    print("This endpoint requires an access token.")
                    failures += 1
                    continue

        try:
            path = fill_path(template)
            body = collect_body(operation, openapi)
            extra_headers = collect_headers(operation)
            default_status = expected_status_default(operation)
            expected_text = input(
                f"Expected HTTP status [{default_status}]: "
            ).strip()
            expected_status = int(expected_text) if expected_text else default_status
        except (ValueError, KeyboardInterrupt):
            print("Endpoint call cancelled.")
            continue

        if tester.test(method, path, expected_status, body, extra_headers):
            successes += 1
        else:
            failures += 1
        again = input("\nTest another endpoint? [Y/n]: ").strip().lower()
        if again in {"n", "no"}:
            break

    print(f"\nEndpoint checks: {successes} passed, {failures} failed.")
    return 1 if failures else 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Choose and call FIKRAH API endpoints individually."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("FIKRAH_API_BASE_URL", "http://localhost:8000"),
        help="API root URL (default: FIKRAH_API_BASE_URL or http://localhost:8000)",
    )
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        with httpx.Client(timeout=args.timeout) as client:
            response = client.get(f"{args.base_url.rstrip('/')}/openapi.json")
            response.raise_for_status()
            openapi = response.json()
    except (httpx.HTTPError, ValueError) as error:
        print(f"Could not load the API schema: {error}", file=sys.stderr)
        return 2

    tester = EndpointTester(args.base_url, args.timeout)
    try:
        return run_interactive(tester, openapi)
    finally:
        tester.close()


if __name__ == "__main__":
    raise SystemExit(main())
