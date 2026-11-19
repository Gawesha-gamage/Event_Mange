from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.config import settings
from app.models import WaitlistEntry, TicketCategory, Event, User

class WaitlistAgent(BaseAgent):
    """
    WaitlistAgent
    Goal: Pass freed seats to waiting customers fairly.
    Decisions:
    - Prioritize waiting attendees by FIFO order (timestamp & priority score).
    - Place timed seat holds (default 300s) for offered customers.
    - Proactive Timer: Periodically sweeps and expires unclaimed holds,
      automatically cascading the seat to the next waiting customer.
    """
    def __init__(self):
        super().__init__(
            name="WaitlistAgent",
            goal="Pass freed seats to waiting customers, hold them for a time limit, and re-offer on expiry."
        )
        self.decision_rules = [
            "Rule WA-1: Seats are re-allocated strictly in FIFO order by waitlist registration timestamp.",
            "Rule WA-2: A waiting attendee is granted a timed hold (5 mins) to claim their seat.",
            "Rule WA-3: Unclaimed holds that exceed expiry time are automatically revoked by the proactive sweep.",
            "Rule WA-4: Revoked seats are immediately re-offered to the next waiting attendee in line.",
            "Rule WA-5: If the waitlist queue is exhausted, released seats are returned to general inventory."
        ]

    def offer_seat_to_next(self, db: Session, cat_id: int, bus, conversation_id: str) -> Optional[WaitlistEntry]:
        """Finds next eligible waitlisted attendee and assigns a timed hold."""
        next_entry = db.query(WaitlistEntry).filter(
            WaitlistEntry.ticket_category_id == cat_id,
            WaitlistEntry.status == "waiting"
        ).order_by(WaitlistEntry.priority.desc(), WaitlistEntry.created_at.asc()).first()

        if not next_entry:
            return None

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=settings.WAITLIST_HOLD_DURATION_SECONDS)
        
        next_entry.status = "offered"
        next_entry.offered_at = now
        next_entry.hold_expires_at = expires_at
        db.commit()
        db.refresh(next_entry)

        event = db.query(Event).filter(Event.id == next_entry.event_id).first()
        category = db.query(TicketCategory).filter(TicketCategory.id == cat_id).first()

        # Proactive Notification via NotificationAgent
        bus.send(
            db=db,
            sender=self.name,
            receiver="NotificationAgent",
            performative="REQUEST",
            content={
                "user_id": next_entry.user_id,
                "title": f"Seat Available: {event.title if event else 'Event'}",
                "message": (
                    f"A released seat for {category.name if category else 'your event'} is now reserved for you! "
                    f"You have 5 minutes to claim it before it is offered to the next attendee."
                ),
                "type": "waitlist"
            },
            conversation_id=conversation_id
        )

        return next_entry

    def proactive_expiry_sweep(self, db: Session, bus) -> int:
        """
        Proactive autonomous behavior running on a schedule with no user action.
        Finds expired seat holds, revokes them, and re-offers them to the next attendee.
        """
        now = datetime.utcnow()
        expired_entries = db.query(WaitlistEntry).filter(
            WaitlistEntry.status == "offered",
            WaitlistEntry.hold_expires_at <= now
        ).all()

        reallocated_count = 0
        conv_id = f"conv-sweep-{now.strftime('%H%M%S')}"

        for entry in expired_entries:
            entry.status = "expired"
            db.commit()

            category = db.query(TicketCategory).filter(TicketCategory.id == entry.ticket_category_id).first()
            if not category:
                continue

            # Try to re-offer to next attendee in line
            next_offer = self.offer_seat_to_next(db, entry.ticket_category_id, bus, conv_id)
            if next_offer:
                reallocated_count += 1
            else:
                # No one left in waitlist; restore back to general inventory
                category.remaining_quantity += entry.requested_quantity
                db.commit()

        # Update persistent belief
        total_sweeps = self.get_belief(db, "total_expiry_sweeps", default=0) + 1
        self.set_belief(db, "total_expiry_sweeps", total_sweeps)

        return reallocated_count

    def handle_message(self, db: Session, message: Dict[str, Any], bus) -> Dict[str, Any]:
        conv_id = message.get("conversation_id")
        sender = message.get("sender")
        performative = message.get("performative")
        content = message.get("content", {})
        action = content.get("action")

        # ----------------------------------------------------
        # Action 1: Join Waitlist
        # ----------------------------------------------------
        if action == "join_waitlist":
            user_id = content.get("user_id")
            cat_id = content.get("ticket_category_id")
            quantity = content.get("requested_quantity", 1)

            category = db.query(TicketCategory).filter(TicketCategory.id == cat_id).first()
            if not category:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Ticket category not found."}
                }

            # Check if user already waiting
            existing = db.query(WaitlistEntry).filter(
                WaitlistEntry.user_id == user_id,
                WaitlistEntry.ticket_category_id == cat_id,
                WaitlistEntry.status.in_(["waiting", "offered"])
            ).first()

            if existing:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "You already hold an active waitlist entry for this ticket category."}
                }

            entry = WaitlistEntry(
                user_id=user_id,
                event_id=category.event_id,
                ticket_category_id=cat_id,
                requested_quantity=quantity,
                status="waiting"
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)

            # Count queue position
            position = db.query(WaitlistEntry).filter(
                WaitlistEntry.ticket_category_id == cat_id,
                WaitlistEntry.status == "waiting",
                WaitlistEntry.created_at <= entry.created_at
            ).count()

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "entry_id": entry.id,
                    "queue_position": position,
                    "message": f"Successfully joined waitlist. Your position is #{position}."
                }
            }

        # ----------------------------------------------------
        # Action 2: React to Released Seats (INFORM from BookingAgent)
        # ----------------------------------------------------
        elif action == "seats_released":
            cat_id = content.get("ticket_category_id")
            quantity = content.get("quantity", 1)

            assigned = 0
            for _ in range(quantity):
                offered = self.offer_seat_to_next(db, cat_id, bus, conv_id)
                if offered:
                    assigned += 1
                else:
                    break

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "INFORM",
                "content": {
                    "seats_offered": assigned,
                    "category_id": cat_id
                }
            }

        # ----------------------------------------------------
        # Action 3: Claim Offered Seat
        # ----------------------------------------------------
        elif action == "claim_seat":
            user_id = content.get("user_id")
            entry_id = content.get("waitlist_entry_id")

            entry = db.query(WaitlistEntry).filter(
                WaitlistEntry.id == entry_id,
                WaitlistEntry.user_id == user_id
            ).first()

            if not entry:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Waitlist entry not found."}
                }

            if entry.status != "offered":
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": f"Cannot claim entry in status '{entry.status}'."}
                }

            if entry.hold_expires_at and entry.hold_expires_at < datetime.utcnow():
                entry.status = "expired"
                db.commit()
                # Re-offer seat
                self.offer_seat_to_next(db, entry.ticket_category_id, bus, conv_id)
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Your 5-minute seat hold has expired."}
                }

            # Valid claim! Mark claimed
            entry.status = "claimed"
            db.commit()

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "message": "Held seat successfully verified for purchase.",
                    "ticket_category_id": entry.ticket_category_id,
                    "quantity": entry.requested_quantity
                }
            }

        return {
            "conversation_id": conv_id,
            "sender": self.name,
            "receiver": sender,
            "performative": "FAILURE",
            "content": {"error": f"Unknown action '{action}' for WaitlistAgent."}
        }
