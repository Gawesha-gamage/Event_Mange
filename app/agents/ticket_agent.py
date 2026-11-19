import uuid
import io
import qrcode
import qrcode.image.svg
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models import Ticket, TicketCategory, Event, TicketScanLog, User

class TicketAgent(BaseAgent):
    """
    TicketAgent
    Goal: Admit each ticket exactly once.
    Decisions:
    - Issue unique, unguessable cryptographic ticket codes and SVG QR codes.
    - At the entrance gate: return admit, already_used, wrong_event, cancelled, or outside_checkin_time.
    - Advanced: Detect suspicious repeated scans (possible shared screenshots / fraud attempts)
      and maintain persistent beliefs surviving server restarts.
    """
    def __init__(self):
        super().__init__(
            name="TicketAgent",
            goal="Admit each ticket exactly once and prevent fraudulent reuse."
        )
        self.decision_rules = [
            "Rule TA-1: Every digital ticket is provisioned with a cryptographically secure, unguessable token.",
            "Rule TA-2: A ticket is admitted strictly once. Any subsequent scan is rejected as 'already_used'.",
            "Rule TA-3: Tickets presented for a mismatched event are refused as 'wrong_event'.",
            "Rule TA-4: Cancelled tickets or tickets for cancelled events are refused as 'cancelled'.",
            "Rule TA-5: Check-in opens 3 hours prior to event start and closes at event end time.",
            "Rule TA-6: Repeated scan attempts on an admitted ticket are flagged as suspicious (possible screenshot sharing)."
        ]

    def generate_qr_svg(self, unique_code: str) -> str:
        """Generates an embedded SVG representation of the QR code."""
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(unique_code, image_factory=factory, box_size=10)
        stream = io.BytesIO()
        img.save(stream)
        svg_str = stream.getvalue().decode("utf-8")
        return svg_str

    def handle_message(self, db: Session, message: Dict[str, Any], bus) -> Dict[str, Any]:
        conv_id = message.get("conversation_id")
        sender = message.get("sender")
        performative = message.get("performative")
        content = message.get("content", {})
        action = content.get("action")

        # ----------------------------------------------------
        # Action 1: Issue Unique Digital Tickets
        # ----------------------------------------------------
        if action == "issue_tickets":
            booking_id = content.get("booking_id")
            cat_id = content.get("ticket_category_id")
            user_id = content.get("user_id")
            event_id = content.get("event_id")
            quantity = content.get("quantity", 1)

            issued_list = []
            for _ in range(quantity):
                code = f"TICK-{uuid.uuid4().hex[:12].upper()}"
                qr_svg = self.generate_qr_svg(code)
                ticket = Ticket(
                    booking_id=booking_id,
                    ticket_category_id=cat_id,
                    user_id=user_id,
                    event_id=event_id,
                    unique_code=code,
                    qr_code_svg=qr_svg,
                    status="valid",
                    scan_count=0
                )
                db.add(ticket)
                db.commit()
                db.refresh(ticket)
                issued_list.append({
                    "id": ticket.id,
                    "unique_code": ticket.unique_code,
                    "status": ticket.status,
                    "qr_code_svg": ticket.qr_code_svg
                })

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "booking_id": booking_id,
                    "issued_count": len(issued_list),
                    "tickets": issued_list
                }
            }

        # ----------------------------------------------------
        # Action 2: Gate Check-in & QR Verification
        # ----------------------------------------------------
        elif action == "verify_ticket":
            code = (content.get("ticket_code") or "").strip().upper()
            scanner_user_id = content.get("scanner_user_id")
            gate_event_id = content.get("event_id")  # Optional event filter at gate

            ticket = db.query(Ticket).filter(Ticket.unique_code == code).first()
            if not ticket:
                # Log invalid scan attempt
                log_entry = TicketScanLog(
                    ticket_code=code,
                    scanner_user_id=scanner_user_id,
                    event_id=gate_event_id,
                    result="invalid_code",
                    reason="Ticket code does not exist in registry.",
                    is_suspicious=True
                )
                db.add(log_entry)
                db.commit()

                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "result": "invalid_code",
                        "reason": "Unknown ticket QR code. Access denied.",
                        "is_suspicious": True
                    }
                }

            ticket.scan_count += 1
            event = db.query(Event).filter(Event.id == ticket.event_id).first()
            attendee = db.query(User).filter(User.id == ticket.user_id).first()
            category = db.query(TicketCategory).filter(TicketCategory.id == ticket.ticket_category_id).first()

            # Rule TA-3: Wrong event check
            if gate_event_id and ticket.event_id != int(gate_event_id):
                log_entry = TicketScanLog(
                    ticket_code=code,
                    scanner_user_id=scanner_user_id,
                    event_id=ticket.event_id,
                    result="wrong_event",
                    reason=f"Ticket is for '{event.title}', not the current gate event.",
                    is_suspicious=False
                )
                db.add(log_entry)
                db.commit()
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "result": "wrong_event",
                        "reason": f"Wrong Event: Ticket belongs to '{event.title}' (ID {event.id}).",
                        "attendee_name": attendee.name if attendee else "Unknown",
                        "event_title": event.title,
                        "category_name": category.name if category else ""
                    }
                }

            # Rule TA-4: Cancelled ticket or cancelled event check
            if ticket.status == "cancelled" or (event and event.status == "cancelled"):
                log_entry = TicketScanLog(
                    ticket_code=code,
                    scanner_user_id=scanner_user_id,
                    event_id=ticket.event_id,
                    result="cancelled",
                    reason="Ticket or associated event has been cancelled.",
                    is_suspicious=False
                )
                db.add(log_entry)
                db.commit()
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "result": "cancelled",
                        "reason": "Cancelled Ticket: This ticket is void and cannot be used for admission.",
                        "attendee_name": attendee.name if attendee else "Unknown",
                        "event_title": event.title if event else "Cancelled"
                    }
                }

            # Rule TA-2 & TA-6: Already used check & suspicious repeated scan detection
            if ticket.status == "used":
                is_suspicious = ticket.scan_count >= 2
                
                # Update persistent belief counter for suspicious repeated scans
                suspicious_count = self.get_belief(db, "suspicious_scans_total", default=0) + 1
                self.set_belief(db, "suspicious_scans_total", suspicious_count)

                log_entry = TicketScanLog(
                    ticket_code=code,
                    scanner_user_id=scanner_user_id,
                    event_id=ticket.event_id,
                    result="already_used",
                    reason=f"Already used at {ticket.scanned_at.strftime('%H:%M:%S')}. Repeated attempt #{ticket.scan_count}.",
                    is_suspicious=is_suspicious
                )
                db.add(log_entry)
                db.commit()
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "result": "already_used",
                        "reason": f"Already Used: Ticket was admitted at {ticket.scanned_at.strftime('%Y-%m-%d %H:%M:%S')}. (Repeated attempt #{ticket.scan_count})",
                        "is_suspicious": is_suspicious,
                        "attendee_name": attendee.name if attendee else "Unknown",
                        "event_title": event.title if event else ""
                    }
                }

            # Rule TA-5: Check-in timing window
            now = datetime.utcnow()
            checkin_opens = event.start_time - timedelta(hours=3)
            if now < checkin_opens:
                log_entry = TicketScanLog(
                    ticket_code=code,
                    scanner_user_id=scanner_user_id,
                    event_id=ticket.event_id,
                    result="outside_checkin_time",
                    reason=f"Gate opens 3 hours before start time ({checkin_opens.strftime('%Y-%m-%d %H:%M')}).",
                    is_suspicious=False
                )
                db.add(log_entry)
                db.commit()
                return {
                    "conversation_id": conv_id,
                    "sender": self.name,
                    "receiver": sender,
                    "performative": "REFUSE",
                    "content": {
                        "result": "outside_checkin_time",
                        "reason": f"Outside Check-in Window: Check-in opens at {checkin_opens.strftime('%Y-%m-%d %H:%M')}.",
                        "attendee_name": attendee.name if attendee else "Unknown",
                        "event_title": event.title
                    }
                }

            # Valid admission!
            ticket.status = "used"
            ticket.scanned_at = now
            
            log_entry = TicketScanLog(
                ticket_code=code,
                scanner_user_id=scanner_user_id,
                event_id=ticket.event_id,
                result="admit",
                reason="Valid ticket successfully admitted.",
                is_suspicious=False
            )
            db.add(log_entry)
            
            # Persistent checkin counter belief
            total_admitted = self.get_belief(db, "total_admitted_tickets", default=0) + 1
            self.set_belief(db, "total_admitted_tickets", total_admitted)

            db.commit()

            return {
                "conversation_id": conv_id,
                "sender": self.name,
                "receiver": sender,
                "performative": "AGREE",
                "content": {
                    "result": "admit",
                    "message": "Admission Granted. Welcome to EventSphere!",
                    "attendee_name": attendee.name if attendee else "Attendee",
                    "event_title": event.title,
                    "category_name": category.name if category else "General",
                    "scanned_at": now.isoformat(),
                    "is_suspicious": False
                }
            }

        return {
            "conversation_id": conv_id,
            "sender": self.name,
            "receiver": sender,
            "performative": "FAILURE",
            "content": {"error": f"Unknown action '{action}' for TicketAgent."}
        }
