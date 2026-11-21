"""Multipart support in the interactive endpoint tester."""

import httpx

from scripts.test_api_endpoints import EndpointTester, collect_uploads


def test_collect_uploads_uses_openapi_binary_field(tmp_path, monkeypatch):
    path = tmp_path / "voice.wav"
    path.write_bytes(b"audio recording")
    answers = iter([str(path), "audio/wav"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    operation = {
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "properties": {"file": {"type": "string", "format": "binary"}}
                    }
                }
            }
        }
    }
    assert collect_uploads(operation, {}) == {
        "file": ("voice.wav", b"audio recording", "audio/wav")
    }
    assert collect_uploads({}, {}) is None


def test_endpoint_tester_sends_multipart_upload(monkeypatch):
    monkeypatch.delenv("FIKRAH_API_ACCESS_TOKEN", raising=False)
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"text": "transcribed words"})

    tester = EndpointTester("http://test", 5)
    tester.close()
    tester.client = httpx.Client(transport=httpx.MockTransport(handle))
    try:
        assert tester.test(
            "POST",
            "/v1/transcriptions",
            200,
            files={"file": ("voice.wav", b"audio recording", "audio/wav")},
        )
    finally:
        tester.close()
    assert requests[0].headers["Content-Type"].startswith("multipart/form-data;")
    assert b"audio recording" in requests[0].content
