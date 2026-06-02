"""Tests for credential redaction in log helpers."""

from app.utils.logging import redact_url


def test_redacts_embedded_credentials():
    assert (
        redact_url("rtsp://user:pass@192.168.1.100:554/stream")
        == "rtsp://***@192.168.1.100:554/stream"
    )
    assert redact_url("http://admin:secret@host/api") == "http://***@host/api"


def test_leaves_credential_free_urls_untouched():
    url = "rtsp://192.168.53.254:8555/heisei"
    assert redact_url(url) == url


def test_non_string_passthrough():
    assert redact_url(None) is None
    assert redact_url(1234) == 1234
