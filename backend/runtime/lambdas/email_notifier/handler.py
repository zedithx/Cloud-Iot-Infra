import html
import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ses_client = boto3.client("ses")

FROM_EMAIL = os.environ["FROM_EMAIL"]
_to_emails = os.environ.get("TO_EMAILS", "")
TO_EMAILS = [addr.strip() for addr in _to_emails.split(",") if addr.strip()] or [FROM_EMAIL]

CHARSET = "UTF-8"


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    records = event.get("Records", [])
    sent = 0
    failures: List[str] = []

    for record in records:
        sns_payload = record.get("Sns", {})
        message_id = sns_payload.get("MessageId")
        try:
            subject, body_text, body_html = _parse_message(sns_payload)
            _send_email(subject, body_text, body_html)
            sent += 1
        except ClientError as error:
            failures.append(f"{message_id or 'unknown'}: {error}")
            logger.exception("Failed to send SES email for message %s", message_id)
        except Exception as error:  # pylint: disable=broad-exception-caught
            failures.append(f"{message_id or 'unknown'}: {error}")
            logger.exception("Unexpected error while processing SNS message %s", message_id)

    return {
        "statusCode": 200,
        "sent": sent,
        "failed": len(failures),
        "failures": failures,
    }


def _parse_message(sns_payload: Dict[str, Any]) -> tuple[str, str, Optional[str]]:
    subject = sns_payload.get("Subject") or "Leaf Disease Alert"
    message = sns_payload.get("Message", "")
    body_text = message or ""
    body_html: Optional[str] = None

    try:
        parsed = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        parsed = None

    if isinstance(parsed, dict):
        subject = parsed.get("subject") or subject
        body_text = parsed.get("bodyText") or parsed.get("body") or body_text
        body_html = parsed.get("bodyHtml")
        
        # Do not append payload JSON to client-facing emails
        # payload = parsed.get("payload")
        # if payload is not None:
        #     pretty_payload = json.dumps(payload, indent=2, default=str)
        #     body_text = _append_payload(body_text, pretty_payload)
        #     body_html = _append_payload_html(body_html, pretty_payload)

    if not body_text:
        body_text = "(No message content provided.)"

    return subject, body_text, body_html


def _append_payload(body_text: str, payload: str) -> str:
    lines = ["", "Details:", payload]
    return "\n".join([body_text] + lines if body_text else lines[1:])


def _append_payload_html(body_html: Optional[str], payload: str) -> str:
    payload_html = f"<pre style='font-family:monospace'>{html.escape(payload)}</pre>"
    if body_html:
        return f"{body_html}<hr/>{payload_html}"
    return payload_html


def _send_email(subject: str, body_text: str, body_html: Optional[str]) -> None:
    body: Dict[str, Any] = {}
    if body_text:
        body["Text"] = {"Charset": CHARSET, "Data": body_text}
    if body_html:
        body["Html"] = {"Charset": CHARSET, "Data": body_html}
    if not body:
        body["Text"] = {"Charset": CHARSET, "Data": "(No body provided.)"}

    ses_client.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": TO_EMAILS},
        Message={
            "Subject": {"Charset": CHARSET, "Data": subject},
            "Body": body,
        },
    )

