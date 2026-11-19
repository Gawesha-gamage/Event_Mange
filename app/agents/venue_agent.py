from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.agents.base import BaseAgent
from app.config import settings
from app.models import Venue, Event, VenueHireRequest

class VenueAgent(BaseAgent):
    """
    VenueAgent
    Goal: Keep every venue's calendar free of clashes.
    Decisions:
    - Accept or refuse an event time slot (with a turnaround buffer).
    - Confirm, escalate, or counter-propose a private hire.
    - Price a hire (including base rate, weekend surcharge, and peak-hour pricing).
    """
    def __init__(self):
        super().__init__(
            name="VenueAgent",
            goal="Keep every venue's calendar free of clashes and manage venue bookings."
        )
        self.decision_rules = [
            "Rule VA-1: Two activities at the same venue must have at least 60 minutes turnaround buffer.",
            "Rule VA-2: Event or Hire requests exceeding venue capacity are REFUSED immediately.",
            "Rule VA-3: Venues marked closed for private hire cannot accept hire requests.",
            "Rule VA-4: Weekend hire incurs 25% peak surcharge; evening slots (18:00-23:00) incur 20% surcharge.",
            "Rule VA-5: Routine hire requests (guests <= 100, cost <= 1000) are confirmed automatically.",
            "Rule VA-6: Large hire requests (guests > 100 or cost > 1000) are escalated for admin review.",
            "Rule VA-7: When a requested slot clashes, PROPOSE usable alternatives (offset slot or other venues)."
        ]

    def calculate_hire_price(self, venue: Venue, start_time: datetime, end_time: datetime, guest_count: int) -> Dict[str, Any]:
        """Calculates hire price applying hourly rate, weekend, and peak-hour pricing."""
        hours = max(1.0, (end_time - start_time).total_seconds() / 3600.0)
        base_price = round(hours * venue.hourly_rate, 2)
        
        # Weekend pricing check (Saturday=5, Sunday=6)
        is_weekend = start_time.weekday() in (5, 6) or end_time.weekday() in (5, 6)
        weekend_multiplier = 1.25 if is_weekend else 1.0

        # Peak hours pricing check (starts or ends between 18:00 and 23:00)
        is_peak = (18 <= start_time.hour < 23) or (18 <= end_time.hour <= 23)
        peak_multiplier = 1.20 if is_peak else 1.0

        total_price = round(base_price * weekend_multiplier * peak_multiplier, 2)
        
        # Cleaning fee for large events
        cleaning_fee = 50.0 if guest_count > 80 else 0.0
        final_price = round(total_price + cleaning_fee, 2)

        return {
            "hours": hours,
            "base_rate": venue.hourly_rate,
            "base_price": base_price,
            "is_weekend": is_weekend,
            "weekend_multiplier": weekend_multiplier,
            "is_peak": is_peak,
            "peak_multiplier": peak_multiplier,
            "cleaning_fee": cleaning_fee,
            "total_price": final_price
        }

    def check_calendar_clash(
        self,
        db: Session,
        venue_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_event_id: Optional[int] = None,
        exclude_hire_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Validates whether the slot overlaps with existing events or hires,
        strictly respecting the turnaround buffer.
        """
        buffer = timedelta(minutes=settings.VENUE_TURNAROUND_BUFFER_MINUTES)
        buffered_start = start_time - buffer
        buffered_end = end_time + buffer

        # Check existing events (draft or published)
        event_query = db.query(Event).filter(
            Event.venue_id == venue_id,
            Event.status != "cancelled",
            Event.start_time < buffered_end,
            Event.end_time > buffered_start
        )
        if exclude_event_id:
            event_query = event_query.filter(Event.id != exclude_event_id)
        
        clashing_event = event_query.first()
        if clashing_event:
            return (
                f"Clashes with event '{clashing_event.title}' scheduled from "
                f"{clashing_event.start_time.strftime('%Y-%m-%d %H:%M')} to "
                f"{clashing_event.end_time.strftime('%Y-%m-%d %H:%M')} "
                f"(including {settings.VENUE_TURNAROUND_BUFFER_MINUTES}m turnaround buffer)."
            )

        # Check existing private hires (confirmed or approved)
        hire_query = db.query(VenueHireRequest).filter(
            VenueHireRequest.venue_id == venue_id,
            VenueHireRequest.status.in_(["confirmed", "approved", "escalated"]),
            VenueHireRequest.start_time < buffered_end,
            VenueHireRequest.end_time > buffered_start
        )
        if exclude_hire_id:
            hire_query = hire_query.filter(VenueHireRequest.id != exclude_hire_id)
            
        clashing_hire = hire_query.first()
        if clashing_hire:
            return (
                f"Clashes with private hire #{clashing_hire.id} ({clashing_hire.purpose}) from "
                f"{clashing_hire.start_time.strftime('%Y-%m-%d %H:%M')} to "
                f"{clashing_hire.end_time.strftime('%Y-%m-%d %H:%M')} "
                f"(including {settings.VENUE_TURNAROUND_BUFFER_MINUTES}m turnaround buffer)."
            )

        return None

    def find_alternatives(
        self,
        db: Session,
        requested_venue: Venue,
        start_time: datetime,
        end_time: datetime,
        guest_count: int
    ) -> Dict[str, Any]:
        """Proposes usable alternative times and alternative venues when a slot is occupied."""
        duration = end_time - start_time
        buffer = timedelta(minutes=settings.VENUE_TURNAROUND_BUFFER_MINUTES)
        
        # 1. Alternative times for same venue (earlier or later)
        suggested_slots = []
        # Check 4 hours earlier
        earlier_start = start_time - duration - buffer
        earlier_end = earlier_start + duration
        if not self.check_calendar_clash(db, requested_venue.id, earlier_start, earlier_end):
            suggested_slots.append({
                "start_time": earlier_start.isoformat(),
                "end_time": earlier_end.isoformat(),
                "label": f"Earlier on same day ({earlier_start.strftime('%H:%M')} - {earlier_end.strftime('%H:%M')})"
            })
        
        # Check 4 hours later
        later_start = end_time + buffer
        later_end = later_start + duration
        if not self.check_calendar_clash(db, requested_venue.id, later_start, later_end):
            suggested_slots.append({
                "start_time": later_start.isoformat(),
                "end_time": later_end.isoformat(),
                "label": f"Later on same day ({later_start.strftime('%H:%M')} - {later_end.strftime('%H:%M')})"
            })

        # Next day same time
        next_day_start = start_time + timedelta(days=1)
        next_day_end = end_time + timedelta(days=1)
        if not self.check_calendar_clash(db, requested_venue.id, next_day_start, next_day_end):
            suggested_slots.append({
                "start_time": next_day_start.isoformat(),
                "end_time": next_day_end.isoformat(),
                "label": f"Following day ({next_day_start.strftime('%Y-%m-%d %H:%M')})"
            })

        # 2. Alternative venues that can fit the guest count
        alt_venues = db.query(Venue).filter(
            Venue.id != requested_venue.id,
            Venue.capacity >= guest_count,
            Venue.is_open_for_private_hire == True
        ).all()
        
        available_venues = []
        for v in alt_venues:
            if not self.check_calendar_clash(db, v.id, start_time, end_time):
                price_info = self.calculate_hire_price(v, start_time, end_time, guest_count)
                available_venues.append({
                    "venue_id": v.id,
                    "name": v.name,
                    "capacity": v.capacity,
                    "hourly_rate": v.hourly_rate,
                    "calculated_price": price_info["total_price"]
                })

        return {
            "suggested_slots": suggested_slots[:2],
            "available_venues": available_venues[:3]
        }

    def handle_message(self, db: Session, message: Dict[str, Any], bus) -> Dict[str, Any]:
        conv_id = message.get("conversation_id")
        sender = message.get("sender")
        performative = message.get("performative")
        content = message.get("content", {})
        action = content.get("action")

        # ----------------------------------------------------
        # Action 1: Check / Validate Event Time Slot
        # ----------------------------------------------------
        if action == "validate_event_slot":
            venue_id = content.get("venue_id")
            start_time = datetime.fromisoformat(content.get("start_time"))
            end_time = datetime.fromisoformat(content.get("end_time"))
            total_tickets = content.get("total_tickets", 0)
            exclude_event_id = content.get("exclude_event_id")

            venue = db.query(Venue).filter(Venue.id == venue_id).first()
            if not venue:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": f"Venue with ID {venue_id} does not exist."}
                }

            # Check capacity rule
            if total_tickets > venue.capacity:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "reason": f"Total tickets ({total_tickets}) exceed venue '{venue.name}' capacity of {venue.capacity}."
                    }
                }

            # Check calendar clash
            clash = self.check_calendar_clash(
                db, venue_id, start_time, end_time, exclude_event_id=exclude_event_id
            )
            if clash:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": clash}
                }

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "message": f"Venue slot confirmed available with {settings.VENUE_TURNAROUND_BUFFER_MINUTES}m turnaround buffer.",
                    "venue_name": venue.name,
                    "capacity": venue.capacity
                }
            }

        # ----------------------------------------------------
        # Action 2: Process Private Venue Hire Request
        # ----------------------------------------------------
        elif action == "request_private_hire":
            hire_id = content.get("hire_id")
            venue_id = content.get("venue_id")
            user_id = content.get("user_id")
            start_time = datetime.fromisoformat(content.get("start_time"))
            end_time = datetime.fromisoformat(content.get("end_time"))
            guest_count = content.get("guest_count", 0)
            purpose = content.get("purpose", "")

            venue = db.query(Venue).filter(Venue.id == venue_id).first()
            if not venue:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": "Specified venue not found."}
                }

            # Rule VA-3: Venue open for hire?
            if not venue.is_open_for_private_hire:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {"reason": f"Venue '{venue.name}' is closed for private hire."}
                }

            # Rule VA-2: Capacity check
            if guest_count > venue.capacity:
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "reason": f"Requested guest count ({guest_count}) exceeds venue capacity ({venue.capacity})."
                    }
                }

            # Rule VA-4: Calculate price
            price_details = self.calculate_hire_price(venue, start_time, end_time, guest_count)
            total_price = price_details["total_price"]

            # Rule VA-1: Check clash
            clash = self.check_calendar_clash(db, venue_id, start_time, end_time, exclude_hire_id=hire_id)
            if clash:
                # Rule VA-7: Propose usable alternatives
                alternatives = self.find_alternatives(db, venue, start_time, end_time, guest_count)
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "PROPOSE",
                    "content": {
                        "reason": f"Requested time slot unavailable: {clash}",
                        "calculated_price": total_price,
                        "pricing_breakdown": price_details,
                        "alternatives": alternatives
                    }
                }

            # Rule VA-6: Escalation check
            if guest_count > 100 or total_price > 1000:
                decision_reason = (
                    f"Escalated for administrative approval due to high scale: "
                    f"{guest_count} guests (threshold: 100) and/or £{total_price} total value."
                )
                status_decision = "escalated"
                performative_choice = "INFORM"
            else:
                # Rule VA-5: Routine automatic confirmation
                decision_reason = "Routine private hire request automatically confirmed by VenueAgent."
                status_decision = "confirmed"
                performative_choice = "AGREE"

            # Notify user via NotificationAgent
            bus.send(
                db=db,
                sender=self.name,
                receiver="NotificationAgent",
                performative="REQUEST",
                content={
                    "user_id": user_id,
                    "title": f"Venue Hire {status_decision.capitalize()}: {venue.name}",
                    "message": f"Your booking for {venue.name} ({purpose}) has been {status_decision}. Total: £{total_price}.",
                    "type": "hire"
                },
                conversation_id=conv_id
            )

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": performative_choice,
                "content": {
                    "decision": status_decision,
                    "calculated_price": total_price,
                    "pricing_breakdown": price_details,
                    "reason": decision_reason
                }
            }

        return {
            "conversation_id": conv_id,
            "sender": self.name,
            "receiver": sender,
            "performative": "FAILURE",
            "content": {"error": f"Unknown action '{action}' for VenueAgent."}
        }
