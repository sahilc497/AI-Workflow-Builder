import os
import smtplib
from email.message import EmailMessage

class EmailService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmailService, cls).__new__(cls)
        return cls._instance

    def send_email(self, to: str, subject: str, body: str) -> str:
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_email = os.getenv("SMTP_EMAIL")
        smtp_password = os.getenv("SMTP_PASSWORD")

        if not smtp_email or not smtp_password:
            raise Exception("SMTP_EMAIL or SMTP_PASSWORD environment variables are not set. Please properly configure your .env file with a Gmail App Password.")

        message = EmailMessage()
        message.set_content(body)
        
        # Ensure 'to' is a clean string or comma-separated list
        if isinstance(to, list):
            clean_to = ", ".join([str(t).strip() for t in to if t])
        else:
            clean_to = str(to).strip()
            
        # Clean any unwanted artifacts
        clean_to = clean_to.replace("'", "").replace('"', "").replace("[", "").replace("]", "")
        
        message['To'] = clean_to
        message['From'] = smtp_email
        message['Subject'] = subject

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_email, smtp_password)
                server.send_message(message)
                return f"Message successfully sent via SMTP to {clean_to}"
        except smtplib.SMTPAuthenticationError:
            raise Exception("SMTP Authentication Error: Failed to login. Please ensure you are using an App Password and not your normal account password.")
        except Exception as e:
            raise Exception(f"SMTP Error sending email: {e}")

def send_email(to: str, subject: str, body: str) -> str:
    """Helper wrapper for the singleton instance."""
    service = EmailService()
    return service.send_email(to, subject, body)
