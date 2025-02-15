from datetime import datetime

from flask_mail import Mail, Message
from flask import current_app
import os

mail = Mail()


def send_update_notification(status, details):
    try:
        msg = Message(
            f"Historical Data Update {status}",
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[os.getenv('ADMIN_EMAIL')]
        )

        msg.body = f"""
            Historical Data Update {status}
            
            Time: {datetime.now()}
            Details: {details}
            
            Tickers Updated: {details.get('tickers_updated', 0)}
            Records Added: {details.get('records_added', 0)}
            Status: {details.get('status', 'Unknown')}
            
            Error (if any): {details.get('error', 'None')}
            """

        mail.send(msg)
        print(f"Notification email sent: {status}")
    except Exception as e:
        print(f"Failed to send email notification: {e}")