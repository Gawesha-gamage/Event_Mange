from datetime import datetime, timedelta
import pytest
from app.models import Venue, Event, TicketCategory, Booking, Ticket, TicketScanLog
from app.agents import ticket_agent, message_bus

def test_ticket_admit_once_and_double_checkin_prevention(db, demo_users):
    """
    Check-in & Double Check-in Prevention Test:
    Ensures a ticket is admitted strictly once. A second scan is rejected with 'already_used'.
    A third scan is flagged as a suspicious repeated scan (possible shared screenshots).
    """
    venue = Venue(name="Concert Hall", location="Central", capacity=100, hourly_rate=100.0)
    db.add(venue)
    db.commit()

    now = datetime.utcnow()
    ev = Event(title="Rock Night", category="Concert", venue_id=venue.id, start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=4), status="published")
    db.add(ev)
    db.commit()

    cat = TicketCategory(event_id=ev.id, name="Stalls", price=20.0, total_quantity=10, remaining_quantity=9)
    db.add(cat)
    db.commit()

    b = Booking(user_id=demo_users["attendee"].id, event_id=ev.id, total_amount=20.0, payment_reference="PAY-1", status="confirmed")
    db.add(b)
    db.commit()

    code = "TICK-TEST-CHECKIN-01"
    ticket = Ticket(
        booking_id=b.id,
        ticket_category_id=cat.id,
        user_id=demo_users["attendee"].id,
        event_id=ev.id,
        unique_code=code,
        status="valid",
        scan_count=0
    )
    db.add(ticket)
    db.commit()

    # 1. First Scan: Should ADMIT successfully
    res1 = ticket_agent.handle_message(
        db=db,
        message={
            "conversation_id": "scan-conv-1",
            "sender": "StaffScanner",
            "performative": "REQUEST",
            "content": {
                "action": "verify_ticket",
                "ticket_code": code,
                "scanner_user_id": demo_users["staff"].id,
                "event_id": ev.id
            }
        },
        bus=message_bus
    )
    assert res1["performative"] == "AGREE"
    assert res1["content"]["result"] == "admit"

    # Ticket status should now be used
    db.refresh(ticket)
    assert ticket.status == "used"
    assert ticket.scan_count == 1

    # 2. Second Scan (Double check-in): Should REFUSE with 'already_used'
    res2 = ticket_agent.handle_message(
        db=db,
        message={
            "conversation_id": "scan-conv-2",
            "sender": "StaffScanner",
            "performative": "REQUEST",
            "content": {
                "action": "verify_ticket",
                "ticket_code": code,
                "scanner_user_id": demo_users["staff"].id,
                "event_id": ev.id
            }
        },
        bus=message_bus
    )
    assert res2["performative"] == "REFUSE"
    assert res2["content"]["result"] == "already_used"
    assert "Already Used" in res2["content"]["reason"]

    # 3. Third Scan (Suspicious repeated scan detection): Flagged as suspicious!
    res3 = ticket_agent.handle_message(
        db=db,
        message={
            "conversation_id": "scan-conv-3",
            "sender": "StaffScanner",
            "performative": "REQUEST",
            "content": {
                "action": "verify_ticket",
                "ticket_code": code,
                "scanner_user_id": demo_users["staff"].id,
                "event_id": ev.id
            }
        },
        bus=message_bus
    )
    assert res3["performative"] == "REFUSE"
    assert res3["content"]["is_suspicious"] is True

def test_ticket_wrong_event_and_cancelled_rejection(db, demo_users):
    """
    Check-in Error Cases Test:
    Ensures that tickets presented at the wrong event or cancelled tickets are refused with clear reasons.
    """
    venue = Venue(name="Sports Arena", location="West", capacity=200, hourly_rate=100.0)
    db.add(venue)
    db.commit()

    now = datetime.utcnow()
    ev1 = Event(title="Event A", category="Seminar", venue_id=venue.id, start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=3), status="published")
    ev2 = Event(title="Event B", category="Workshop", venue_id=venue.id, start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=3), status="published")
    db.add_all([ev1, ev2])
    db.commit()

    cat1 = TicketCategory(event_id=ev1.id, name="General", price=10.0, total_quantity=10, remaining_quantity=9)
    db.add(cat1)
    db.commit()

    b1 = Booking(user_id=demo_users["attendee"].id, event_id=ev1.id, total_amount=10.0, payment_reference="PAY-EV1", status="confirmed")
    db.add(b1)
    db.commit()

    t_wrong = Ticket(booking_id=b1.id, ticket_category_id=cat1.id, user_id=demo_users["attendee"].id, event_id=ev1.id, unique_code="TICK-WRONG-EV-01", status="valid")
    t_canc = Ticket(booking_id=b1.id, ticket_category_id=cat1.id, user_id=demo_users["attendee"].id, event_id=ev1.id, unique_code="TICK-CANC-01", status="cancelled")
    db.add_all([t_wrong, t_canc])
    db.commit()

    # Scan Ticket for Event A at gate for Event B -> should reject as wrong_event
    res_wrong = ticket_agent.handle_message(
        db=db,
        message={
            "conversation_id": "scan-wrong-1",
            "sender": "StaffScanner",
            "performative": "REQUEST",
            "content": {
                "action": "verify_ticket",
                "ticket_code": t_wrong.unique_code,
                "event_id": ev2.id # Wrong event filter
            }
        },
        bus=message_bus
    )
    assert res_wrong["performative"] == "REFUSE"
    assert res_wrong["content"]["result"] == "wrong_event"

    # Scan Cancelled Ticket -> should reject as cancelled
    res_canc = ticket_agent.handle_message(
        db=db,
        message={
            "conversation_id": "scan-canc-1",
            "sender": "StaffScanner",
            "performative": "REQUEST",
            "content": {
                "action": "verify_ticket",
                "ticket_code": t_canc.unique_code,
                "event_id": ev1.id
            }
        },
        bus=message_bus
    )
    assert res_canc["performative"] == "REFUSE"
    assert res_canc["content"]["result"] == "cancelled"
