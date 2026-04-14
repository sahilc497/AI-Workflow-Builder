"""
EmailNode – Sends an email via SMTP (Gmail App Password).
Handles both EMAIL and EMAIL_MESSAGE action types.
"""
import os
from .base import BaseNode


class EmailNode(BaseNode):
    node_type = "EMAIL"
    risk_level = "MEDIUM"

    def validate(self, params: dict) -> None:
        recipient = params.get("to") or params.get("recipient_ref", "")
        if not recipient:
            raise ValueError("EmailNode: 'to' recipient is required.")
        if "[" in recipient and "]" in recipient:
            raise ValueError(f"EmailNode: placeholder detected in recipient '{recipient}'.")

    def execute(self, params: dict, context: dict) -> str:
        from backend.email_service import send_email

        recipient = params.get("to") or params.get("recipient_ref", "")
        subject = params.get("subject", "AI Workflow Alert")
        body_text = params.get("body") or params.get("body_text_ref", "")

        # Context resolution
        rec_ref = params.get("recipient_ref")
        if rec_ref and rec_ref in context:
            val = str(context[rec_ref])
            if "@" in val:
                recipient = val

        body_ref = params.get("body_text_ref") or params.get("input_data_ref")
        if body_ref and body_ref in context:
            body_text = context[body_ref]

        # Placeholder guards
        if "[" in str(body_text) and "]" in str(body_text):
            raise ValueError(f"EmailNode: placeholder detected in body.")

        result = send_email(recipient, subject, str(body_text))
        return f"Email sent to {recipient}: {result}"
