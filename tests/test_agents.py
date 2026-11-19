from datetime import datetime, timedelta
import pytest
from app.agents import (
    venue_agent, booking_agent, ticket_agent, waitlist_agent, notification_agent, message_bus
)
from app.models import Venue, Event, TicketCategory, User, WaitlistEntry, Booking, Ticket

def test_venue_agent_turnaround_buffer_clash(db, demo_users):
    """VenueAgent Test: Validates that activities within the 60m turnaround buffer are refused."""
    venue = Venue(name="Acoustic Hall", location="East Campus", capacity=200, hourly_rate=100.0, is_open_for_private_hire=True)
    db.add(venue)
    db.commit()

    now = datetime.utcnow()
    e_start = now + timedelta(days=2, hours=10)
    e_end = e_start + timedelta(hours=2)

    # First event agreed
    res1 = venue_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-va-1",
            "sender": "Test",
            "performative": "REQUEST",
            "content": {
                "action": "validate_event_slot",
                "venue_id": venue.id,
                "start_time": e_start.isoformat(),
                "end_time": e_end.isoformat(),
                "total_tickets": 100
            }
        },
        bus=message_bus
    )
    assert res1["performative"] == "AGREE"

    # Commit event to DB
    ev = Event(title="Event 1", category="Workshop", venue_id=venue.id, start_time=e_start, end_time=e_end, status="published")
    db.add(ev)
    db.commit()

    # Try to schedule a second event 30 mins after event 1 (violates 60m turnaround buffer)
    clash_start = e_end + timedelta(minutes=30)
    clash_end = clash_start + timedelta(hours=2)

    res2 = venue_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-va-2",
            "sender": "Test",
            "performative": "REQUEST",
            "content": {
                "action": "validate_event_slot",
                "venue_id": venue.id,
                "start_time": clash_start.isoformat(),
                "end_time": clash_end.isoformat(),
                "total_tickets": 50
            }
        },
        bus=message_bus
    )
    assert res2["performative"] == "REFUSE"
    assert "turnaround buffer" in res2["content"]["reason"]

def test_venue_agent_pricing_and_counter_proposal(db, demo_users):
    """VenueAgent Test: Checks weekend/peak pricing and counter-proposal generation on clash."""
    v1 = Venue(name="Grand Arena", location="Central", capacity=300, hourly_rate=100.0, is_open_for_private_hire=True)
    v2 = Venue(name="Alternate Hall", location="North", capacity=300, hourly_rate=80.0, is_open_for_private_hire=True)
    db.add_all([v1, v2])
    db.commit()

    # Weekend (Saturday) + Peak hour (starts 19:00)
    sat_start = datetime(2026, 11, 21, 19, 0) # Saturday 7pm
    sat_end = sat_start + timedelta(hours=3) # 3 hours

    price_info = venue_agent.calculate_hire_price(v1, sat_start, sat_end, guest_count=50)
    # Base = 3h * 100 = 300
    # Weekend * 1.25 = 375
    # Peak * 1.20 = 450
    assert price_info["is_weekend"] is True
    assert price_info["is_peak"] is True
    assert price_info["total_price"] == 450.0

    # Book a clash on v1
    ev_clash = Event(title="Occupying Event", category="Concert", venue_id=v1.id, start_time=sat_start, end_time=sat_end, status="published")
    db.add(ev_clash)
    db.commit()

    # Request private hire on clashing slot -> should receive PROPOSE with alternatives
    res = venue_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-va-3",
            "sender": "Test",
            "performative": "REQUEST",
            "content": {
                "action": "request_private_hire",
                "venue_id": v1.id,
                "user_id": demo_users["attendee"].id,
                "start_time": sat_start.isoformat(),
                "end_time": sat_end.isoformat(),
                "guest_count": 50,
                "purpose": "Alumni Party"
            }
        },
        bus=message_bus
    )
    assert res["performative"] == "PROPOSE"
    assert "alternatives" in res["content"]
    assert len(res["content"]["alternatives"]["available_venues"]) >= 1

def test_booking_agent_max_tickets_and_stated_refunds(db, demo_users):
    """BookingAgent Test: Enforces max 6 tickets per booking rule and verifies stated refund tiers."""
    # Test Rule BA-1: Reject > 6 tickets
    res_exceed = booking_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-ba-1",
            "sender": "Test",
            "performative": "REQUEST",
            "content": {
                "action": "book_tickets",
                "user_id": demo_users["attendee"].id,
                "ticket_category_id": 999,
                "quantity": 7 # Exceeds limit
            }
        },
        bus=message_bus
    )
    assert res_exceed["performative"] == "REFUSE"
    assert "capped at 6 tickets" in res_exceed["content"]["reason"]

    # Test Stated Refund Tiers (Rule BA-4)
    now = datetime.utcnow()
    # >= 48 hours -> 100% refund
    rf_full = booking_agent.calculate_refund(now + timedelta(hours=50), total_paid=100.0)
    assert rf_full["percentage"] == 100
    assert rf_full["amount"] == 100.0

    # 24-48 hours -> 50% refund
    rf_half = booking_agent.calculate_refund(now + timedelta(hours=30), total_paid=100.0)
    assert rf_half["percentage"] == 50
    assert rf_half["amount"] == 50.0

    # < 24 hours -> 0% refund
    rf_none = booking_agent.calculate_refund(now + timedelta(hours=10), total_paid=100.0)
    assert rf_none["percentage"] == 0
    assert rf_none["amount"] == 0.0

    # Organiser Event Cancellation -> 100% full refund
    rf_cancel = booking_agent.calculate_refund(now + timedelta(hours=5), total_paid=100.0, is_event_cancelled=True)
    assert rf_cancel["percentage"] == 100
    assert rf_cancel["amount"] == 100.0

def test_ticket_agent_issue_and_unique_qr(db, demo_users):
    """TicketAgent Test: Generates unguessable unique codes and SVG QR codes."""
    res = ticket_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-ta-1",
            "sender": "Test",
            "performative": "REQUEST",
            "content": {
                "action": "issue_tickets",
                "booking_id": 1,
                "ticket_category_id": 1,
                "user_id": demo_users["attendee"].id,
                "event_id": 1,
                "quantity": 2
            }
        },
        bus=message_bus
    )
    assert res["performative"] == "AGREE"
    tickets = res["content"]["tickets"]
    assert len(tickets) == 2
    assert tickets[0]["unique_code"] != tickets[1]["unique_code"]
    assert "<svg" in tickets[0]["qr_code_svg"]

def test_waitlist_agent_queue_and_proactive_sweep(db, demo_users):
    """WaitlistAgent Test: Enforces FIFO waitlist holds and triggers proactive expiry sweep."""
    v = Venue(name="Lab Hall", location="South", capacity=50, hourly_rate=50.0)
    db.add(v)
    db.commit()

    ev = Event(title="Agent Workshop", category="Workshop", venue_id=v.id, start_time=datetime.utcnow() + timedelta(days=2), end_time=datetime.utcnow() + timedelta(days=2, hours=3), status="published")
    db.add(ev)
    db.commit()

    cat = TicketCategory(event_id=ev.id, name="General", price=10.0, total_quantity=10, remaining_quantity=0)
    db.add(cat)
    db.commit()

    # User 1 joins waitlist
    res_join = waitlist_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-wa-1",
            "sender": "Test",
            "performative": "REQUEST",
            "content": {
                "action": "join_waitlist",
                "user_id": demo_users["attendee"].id,
                "ticket_category_id": cat.id,
                "requested_quantity": 1
            }
        },
        bus=message_bus
    )
    assert res_join["performative"] == "AGREE"
    assert res_join["content"]["queue_position"] == 1

    entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == res_join["content"]["entry_id"]).first()
    assert entry.status == "waiting"

    # Seats released INFORM -> WaitlistAgent sets timed hold
    waitlist_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-wa-2",
            "sender": "BookingAgent",
            "performative": "INFORM",
            "content": {
                "action": "seats_released",
                "ticket_category_id": cat.id,
                "quantity": 1
            }
        },
        bus=message_bus
    )
    db.refresh(entry)
    assert entry.status == "offered"
    assert entry.hold_expires_at is not None

    # Simulate expiry: artificially backdate hold_expires_at
    entry.hold_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    # Trigger proactive sweep -> entry marked expired
    waitlist_agent.proactive_expiry_sweep(db=db, bus=message_bus)
    db.refresh(entry)
    assert entry.status == "expired"

def test_notification_agent_reactive_broadcast(db, demo_users):
    """NotificationAgent Test: Delivers in-app alerts, simulated email logs, and reacts to broadcast INFORM."""
    res = notification_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-na-1",
            "sender": "BookingAgent",
            "performative": "REQUEST",
            "content": {
                "user_id": demo_users["attendee"].id,
                "title": "Booking Confirmation",
                "message": "Your booking BK-100 is confirmed.",
                "type": "booking"
            }
        },
        bus=message_bus
    )
    assert res["performative"] == "INFORM"
    assert res["content"]["delivered"] is True
    assert res["content"]["email_sent"] is True

    # Test broadcast INFORM listener
    res_bc = notification_agent.handle_message(
        db=db,
        message={
            "conversation_id": "test-na-2",
            "sender": "VenueAgent",
            "performative": "INFORM",
            "content": {"event": "new_venue_registered"}
        },
        bus=message_bus
    )
    assert res_bc["performative"] == "INFORM"
    assert res_bc["content"]["status"] == "broadcast_logged"
