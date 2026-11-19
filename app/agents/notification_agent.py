import logging
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Notification, User

logger = logging.getLogger("NotificationAgent")

class NotificationAgent(BaseAgent):
    """
    NotificationAgent
    Goal: Tell the right person what affects them.
    Decisions:
    - Transform domain events and agent performatives into actionable user alerts.
    - Advanced: Simulate and log outbound HTML/text email notifications.
    - Reactive broadcast listener for system-wide INFORM events.
    """
    def __init__(self):
        super().__init__(
            name="NotificationAgent",
            goal="Turn events from other agents into prompt, well-formatted user notifications and emails."
        )
        self.decision_rules = [
            "Rule NA-1: User-targeted messages must be converted to persistent in-app notifications.",
            "Rule NA-2: Critical booking confirmations and seat hold offers trigger simulated email delivery.",
            "Rule NA-3: Broadcast INFORM events are audited and aggregated into system intelligence beliefs."
        ]

    def send_simulated_email(self, recipient_email: str, subject: str, message_body: str) -> bool:
        """Simulates asynchronous outbound SMTP email delivery."""
        logger.info(
            f"[OUTBOUND EMAIL DISPATCH]\n"
            f"To: {recipient_email}\n"
            f"Subject: {subject}\n"
            f"Body: {message_body}\n"
            f"Timestamp: {datetime.utcnow().isoformat()}\n"
            f"Status: DELIVERED (Simulated SMTP)"
        )
        return True

    def handle_message(self, db: Session, message: Dict[str, Any], bus) -> Dict[str, Any]:
        conv_id = message.get("conversation_id")
        sender = message.get("sender")
        performative = message.get("performative")
        content = message.get("content", {})

        # Handle user-specific notification request
        user_id = content.get("user_id")
        title = content.get("title", "EventSphere Notification")
        body = content.get("message", "")
        notif_type = content.get("type", "system")

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            email_sent = False
            if user:
                email_sent = self.send_simulated_email(user.email, title, body)

            notif = Notification(
                user_id=user_id,
                title=title,
                message=body,
                notification_type=notif_type,
                is_read=False,
                simulated_email_sent=email_sent
            )
            db.add(notif)

            # Update persistent belief counter
            total_sent = self.get_belief(db, "total_notifications_dispatched", default=0) + 1
            self.set_belief(db, "total_notifications_dispatched", total_sent)

            db.commit()

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "INFORM",
                "content": {
                    "notification_id": notif.id,
                    "delivered": True,
                    "email_sent": email_sent
                }
            }

        # Handle system-wide broadcast INFORM
        if performative == "INFORM":
            broadcast_count = self.get_belief(db, "broadcast_events_received", default=0) + 1
            self.set_belief(db, "broadcast_events_received", broadcast_count)
            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "INFORM",
                "content": {"status": "broadcast_logged", "total_broadcasts": broadcast_count}
            }

        return {
            "conversation_id": conv_id,
            "sender": self.name,
            "receiver": sender,
            "performative": "FAILURE",
            "content": {"error": "Missing user_id for notification delivery."}
        }
