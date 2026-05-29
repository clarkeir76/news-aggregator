"""Tests for the CloudWatch alarm alerting Lambda handler."""

import json
import os
from unittest.mock import MagicMock, patch


def load_handler():
    """Import handler from the Terraform module directory."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "handler",
        os.path.join(
            os.path.dirname(__file__),
            "../infra/terraform/modules/alerting/handler.py",
        ),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_sns_event(alarm_name, state, reason, region="eu-west-1"):
    message = {
        "AlarmName": alarm_name,
        "NewStateValue": state,
        "NewStateReason": reason,
        "Region": region,
    }
    return {"Records": [{"Sns": {"Message": json.dumps(message)}}]}


def test_alarm_state_sends_payload(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/triggers/test")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    handler = load_handler()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        event = make_sns_event(
            "news-aggregator-prod-errors", "ALARM", "Threshold breached"
        )
        handler.lambda_handler(event, None)

    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data.decode())

    assert "payload" in body
    assert "news-aggregator-prod-errors" in body["payload"]
    assert "ALARM" in body["payload"]
    assert "[prod]" in body["payload"]


def test_ok_state_sends_payload(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/triggers/test")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    handler = load_handler()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        event = make_sns_event(
            "news-aggregator-prod-errors", "OK", "Threshold no longer breached"
        )
        handler.lambda_handler(event, None)

    body = json.loads(mock_urlopen.call_args[0][0].data.decode())
    assert "OK" in body["payload"]
    assert "✅" in body["payload"]


def test_alarm_emoji_is_red_circle(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/triggers/test")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    handler = load_handler()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        handler.lambda_handler(make_sns_event("test-alarm", "ALARM", "reason"), None)

    body = json.loads(mock_urlopen.call_args[0][0].data.decode())
    assert "\U0001f534" in body["payload"]  # 🔴


def test_payload_sent_to_correct_webhook(monkeypatch):
    webhook = "https://hooks.slack.com/triggers/specific-url"
    monkeypatch.setenv("SLACK_WEBHOOK_URL", webhook)
    monkeypatch.setenv("ENVIRONMENT", "test")

    handler = load_handler()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        handler.lambda_handler(make_sns_event("test-alarm", "ALARM", "reason"), None)

    request = mock_urlopen.call_args[0][0]
    assert request.full_url == webhook
