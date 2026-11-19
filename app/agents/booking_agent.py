import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.agents.base import BaseAgent
from app.config import settings
from app.models import (
    Event, TicketCategory, Booking, Ticket, CartHold, User
)

class BookingAgent(BaseAgent):
    """
    BookingAgent
    Goal: Sell tickets fairly without overselling.
    Decisions:
    - Accept or refuse ticket requests (quantity bounds, timing, atomic remaining check).
    - Maintain timed cart holds.
    - Calculate cancellation refund amount based on stated policy.
    - Trigger full refunds upon event cancellation.
    - Coordinate with TicketAgent (issuance), WaitlistAgent (seat release), and NotificationAgent.
    """
    def __init__(self):
        super().__init__(
            name="BookingAgent",
            goal="Sell tickets fairly without overselling and enforce booking/refund rules."
        )
        self.decision_rules = [
            "Rule BA-1: Maximum 6 tickets can be booked per request to ensure fair distribution.",
            "Rule BA-2: Reject booking if remaining ticket quantity is insufficient.",
            "Rule BA-3: Reject booking if the event is cancelled, in draft, or has already ended.",
            "Rule BA-4: Cancellation >= 48h prior yields 100% refund; 24-48h yields 50%; < 24h yields 0%.",
            "Rule BA-5: Event cancellation by organiser yields mandatory 100% full refund.",
            "Rule BA-6: Freed seats from cancellation must trigger seat re-allocation via WaitlistAgent."
        ]

    def calculate_refund(self, event_start_time: datetime, total_paid: float, is_event_cancelled: bool = False) -> Dict[str, Any]:
        """Calculates refund according to stated university ticketing policy."""
        if is_event_cancelled:
            return {
                "percentage": 100,
                "amount": round(total_paid, 2),
                "reason": "Full refund issued due to event cancellation by organiser."
            }

        now = datetime.utcnow()
        hours_before = (event_start_time - now).total_seconds() / 3600.0

        if hours_before >= settings.REFUND_FULL_HOURS:
            return {
                "percentage": 100,
                "amount": round(total_paid, 2),
                "reason": f"Cancelled {hours_before:.1f}h before start (>= {settings.REFUND_FULL_HOURS}h threshold): 100% refund."
            }
        elif hours_before >= settings.REFUND_HALF_HOURS:
            half_amount = round(total_paid * 0.50, 2)
            return {
                "percentage": 50,
                "amount": half_amount,
                "reason": f"Cancelled {hours_before:.1f}h before start (between {settings.REFUND_HALF_HOURS}h and {settings.REFUND_FULL_HOURS}h): 50% refund."
            }
        else:
            return {
                "percentage": 0,
                "amount": 0.0,
                "reason": f"Cancelled less than {settings.REFUND_HALF_HOURS}h before start: no refund permitted under policy."
            }

    def handle_message(self, db: Session, message: Dict[str, Any], bus) -> Dict[str, Any]:
        conv_id = message.get("conversation_id")
        sender = message.get("sender")
        performative = message.get("performative")
        content = message.get("content", {})
        action = content.get("action")

        # ----------------------------------------------------
        # Action 1: Create Cart Hold (Part C: Timed Cart Holds)
        # ----------------------------------------------------
        if action == "hold_tickets":
            user_id = content.get("user_id")
            cat_id = content.get("ticket_category_id")
            quantity = content.get("quantity", 1)

            if quantity > settings.TICKET_MAX_PER_BOOKING:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": f"Maximum limit is {settings.TICKET_MAX_PER_BOOKING} tickets per transaction."}
                }

            category = db.query(TicketCategory).filter(TicketCategory.id == cat_id).with_for_update().first()
            if not category:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Ticket category not found."}
                }

            rows_updated = db.query(TicketCategory).filter(
                TicketCategory.id == cat_id,
                TicketCategory.remaining_quantity >= quantity
            ).update(
                {TicketCategory.remaining_quantity: TicketCategory.remaining_quantity - quantity},
                synchronize_session="fetch"
            )
            if rows_updated == 0:
                cat_current = db.query(TicketCategory).filter(TicketCategory.id == cat_id).first()
                rem = cat_current.remaining_quantity if cat_current else 0
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "reason": f"Only {rem} tickets remain for {category.name}.",
                        "remaining": rem
                    }
                }

            expires_at = datetime.utcnow() + timedelta(seconds=settings.CART_HOLD_DURATION_SECONDS)
            hold = CartHold(
                user_id=user_id,
                ticket_category_id=cat_id,
                quantity=quantity,
                expires_at=expires_at,
                status="active"
            )
            db.add(hold)
            db.commit()
            db.refresh(hold)

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "hold_id": hold.id,
                    "expires_at": expires_at.isoformat(),
                    "seconds_remaining": settings.CART_HOLD_DURATION_SECONDS,
                    "quantity": quantity
                }
            }

        # ----------------------------------------------------
        # Action 2: Confirm Booking & Purchase Tickets
        # ----------------------------------------------------
        elif action == "book_tickets":
            user_id = content.get("user_id")
            cat_id = content.get("ticket_category_id")
            quantity = content.get("quantity", 1)
            hold_id = content.get("cart_hold_id")
            payment_ref = content.get("payment_reference", f"PAY-{uuid.uuid4().hex[:10].upper()}")

            # Rule BA-1: Max tickets rule
            if quantity > settings.TICKET_MAX_PER_BOOKING:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": f"Refused: Bookings are capped at {settings.TICKET_MAX_PER_BOOKING} tickets to ensure fair public access."}
                }

            # Atomic database lock on category to guarantee zero overselling under concurrency!
            category = db.query(TicketCategory).filter(TicketCategory.id == cat_id).with_for_update().first()
            if not category:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Selected ticket category does not exist."}
                }

            event = db.query(Event).filter(Event.id == category.event_id).first()
            if not event:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Associated event not found."}
                }

            # Rule BA-3: Event status & timing check
            if event.status != "published":
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": f"Event '{event.title}' is currently {event.status} and cannot be booked."}
                }

            if event.end_time < datetime.utcnow():
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Event has already concluded."}
                }

            # Check if using an active cart hold
            is_held = False
            if hold_id:
                hold = db.query(CartHold).filter(
                    CartHold.id == hold_id,
                    CartHold.user_id == user_id,
                    CartHold.ticket_category_id == cat_id,
                    CartHold.status == "active"
                ).first()
                if hold and hold.expires_at > datetime.utcnow() and hold.quantity >= quantity:
                    is_held = True
                    hold.status = "completed"

            # If not held, verify atomic availability via conditional update
            if not is_held:
                rows_updated = db.query(TicketCategory).filter(
                    TicketCategory.id == cat_id,
                    TicketCategory.remaining_quantity >= quantity
                ).update(
                    {TicketCategory.remaining_quantity: TicketCategory.remaining_quantity - quantity},
                    synchronize_session="fetch"
                )
                if rows_updated == 0:
                    cat_current = db.query(TicketCategory).filter(TicketCategory.id == cat_id).first()
                    rem = cat_current.remaining_quantity if cat_current else 0
                    return {
                        "conversation_id": conv_id,
                        "sender": self.name,
                        "receiver": sender,
                        "performative": "REFUSE",
                        "content": {
                            "reason": f"Capacity reached: Only {rem} seats available for '{category.name}'.",
                            "remaining": rem,
                            "can_join_waitlist": True
                        }
                    }

            total_amount = round(category.price * quantity, 2)

            # Create Booking
            booking = Booking(
                user_id=user_id,
                event_id=event.id,
                total_amount=total_amount,
                payment_reference=payment_ref,
                status="confirmed"
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)

            # Delegate ticket generation to TicketAgent via MessageBus!
            ticket_res = bus.send(
                db=db,
                sender=self.name,
                receiver="TicketAgent",
                performative="REQUEST",
                content={
                    "action": "issue_tickets",
                    "booking_id": booking.id,
                    "ticket_category_id": category.id,
                    "user_id": user_id,
                    "event_id": event.id,
                    "quantity": quantity
                },
                conversation_id=conv_id
            )

            # Delegate attendee notification to NotificationAgent
            bus.send(
                db=db,
                sender=self.name,
                receiver="NotificationAgent",
                performative="REQUEST",
                content={
                    "user_id": user_id,
                    "title": f"Tickets Confirmed: {event.title}",
                    "message": f"Your booking {booking.booking_reference} for {quantity}x {category.name} is confirmed. Payment reference: {payment_ref}.",
                    "type": "booking"
                },
                conversation_id=conv_id
            )

            issued_tickets = ticket_res.get("content", {}).get("tickets", []) if ticket_res else []

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "booking_id": booking.id,
                    "booking_reference": booking.booking_reference,
                    "event_id": event.id,
                    "event_title": event.title,
                    "total_amount": total_amount,
                    "payment_reference": payment_ref,
                    "tickets": issued_tickets
                }
            }

        # ----------------------------------------------------
        # Action 3: Cancel Booking & Process Refund
        # ----------------------------------------------------
        elif action == "cancel_booking":
            booking_id = content.get("booking_id")
            user_id = content.get("user_id")

            booking = db.query(Booking).filter(Booking.id == booking_id).first()
            if not booking:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Booking record not found."}
                }

            if booking.status == "cancelled":
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Booking has already been cancelled."}
                }

            event = db.query(Event).filter(Event.id == booking.event_id).first()
            refund_calc = self.calculate_refund(event.start_time, booking.total_amount)

            # Mark booking cancelled
            booking.status = "cancelled"
            booking.refund_amount = refund_calc["amount"]
            booking.cancelled_at = datetime.utcnow()

            # Invalidate all associated tickets via TicketAgent
            for ticket in booking.tickets:
                ticket.status = "cancelled"

            # Count released seats per category
            cat_counts = {}
            for t in booking.tickets:
                cat_counts[t.ticket_category_id] = cat_counts.get(t.ticket_category_id, 0) + 1

            # Restore remaining quantities and alert WaitlistAgent!
            for c_id, count in cat_counts.items():
                cat = db.query(TicketCategory).filter(TicketCategory.id == c_id).first()
                if cat:
                    cat.remaining_quantity += count
                    db.commit()

                    # Proactive release notification to WaitlistAgent
                    bus.send(
                        db=db,
                        sender=self.name,
                        receiver="WaitlistAgent",
                        performative="INFORM",
                        content={
                            "action": "seats_released",
                            "event_id": event.id,
                            "ticket_category_id": c_id,
                            "quantity": count
                        },
                        conversation_id=conv_id
                    )

            db.commit()

            # Notify user
            bus.send(
                db=db,
                sender=self.name,
                receiver="NotificationAgent",
                performative="REQUEST",
                content={
                    "user_id": user_id,
                    "title": f"Booking Cancelled: {event.title}",
                    "message": f"Your booking {booking.booking_reference} has been cancelled. Refund: £{refund_calc['amount']} ({refund_calc['percentage']}%). {refund_calc['reason']}",
                    "type": "booking"
                },
                conversation_id=conv_id
            )

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "booking_id": booking.id,
                    "status": "cancelled",
                    "refund_amount": refund_calc["amount"],
                    "refund_percentage": refund_calc["percentage"],
                    "reason": refund_calc["reason"]
                }
            }

        # ----------------------------------------------------
        # Action 4: Mass Event Cancellation
        # ----------------------------------------------------
        elif action == "cancel_event":
            event_id = content.get("event_id")
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Event not found."}
                }

            event.status = "cancelled"
            
            # Full refunds for all confirmed bookings
            affected_bookings = db.query(Booking).filter(
                Booking.event_id == event_id,
                Booking.status == "confirmed"
            ).all()

            for b in affected_bookings:
                b.status = "cancelled"
                b.refund_amount = b.total_amount
                b.cancelled_at = datetime.utcnow()
                for t in b.tickets:
                    t.status = "cancelled"
                
                # Notify attendee
                bus.send(
                    db=db,
                    sender=self.name,
                    receiver="NotificationAgent",
                    performative="REQUEST",
                    content={
                        "user_id": b.user_id,
                        "title": f"Event Cancelled: {event.title}",
                        "message": f"Event '{event.title}' was cancelled by organisers. A full 100% refund of £{b.total_amount} has been processed.",
                        "type": "booking"
                    },
                    conversation_id=conv_id
                )

            db.commit()

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "event_id": event.id,
                    "status": "cancelled",
                    "refunded_bookings_count": len(affected_bookings)
                }
            }

        return {
            "conversation_id": conv_id,
            "sender": self.name,
            "receiver": sender,
            "performative": "FAILURE",
            "content": {"error": f"Unknown action '{action}' for BookingAgent."}
        }
