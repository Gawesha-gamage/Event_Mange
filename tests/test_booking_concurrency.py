import pytest
import concurrent.futures
from datetime import datetime, timedelta
from app.models import Venue, Event, TicketCategory, Ticket, Booking
from app.agents import booking_agent, message_bus
from tests.conftest import TestingSessionLocal

def test_overbooking_prevention_under_concurrency(db, demo_users):
    """
    Concurrency & Overbooking Prevention Test:
    Ensures that when multiple requests attempt to book the last remaining tickets simultaneously,
    the system never sells more tickets than exist.
    """
    venue = Venue(name="Limited Capacity Room", location="Floor 2", capacity=50, hourly_rate=50.0)
    db.add(venue)
    db.commit()

    ev = Event(
        title="Exclusive Masterclass",
        category="Seminar",
        venue_id=venue.id,
        start_time=datetime.utcnow() + timedelta(days=3),
        end_time=datetime.utcnow() + timedelta(days=3, hours=2),
        status="published"
    )
    db.add(ev)
    db.commit()

    # Exactly 2 tickets remaining!
    cat = TicketCategory(event_id=ev.id, name="Rare Seat", price=50.0, total_quantity=2, remaining_quantity=2)
    db.add(cat)
    db.commit()

    # Extract IDs outside of thread closure to prevent cross-thread session access
    attendee_id = demo_users["attendee"].id
    category_id = cat.id

    # Function executing a booking attempt
    def attempt_booking(request_idx):
        thread_db = TestingSessionLocal()
        try:
            res = booking_agent.handle_message(
                db=thread_db,
                message={
                    "conversation_id": f"conv-concurrent-{request_idx}",
                    "sender": f"User-{request_idx}",
                    "performative": "REQUEST",
                    "content": {
                        "action": "book_tickets",
                        "user_id": attendee_id,
                        "ticket_category_id": category_id,
                        "quantity": 1,
                        "payment_reference": f"CONCUR-PAY-{request_idx}"
                    }
                },
                bus=message_bus
            )
            return res.get("performative")
        except Exception as e:
            return "REFUSE"
        finally:
            thread_db.close()

    # Run 5 concurrent attempts for the 2 available seats!
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_booking, i) for i in range(5)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Verify: Exactly 2 AGREE (successful bookings) and 3 REFUSE
    agreed_count = results.count("AGREE")
    refused_count = results.count("REFUSE")

    assert agreed_count == 2, f"Expected exactly 2 agreed bookings, but got {agreed_count}"
    assert refused_count == 3, f"Expected 3 refused bookings due to capacity, but got {refused_count}"

    # Verify database state
    db.refresh(cat)
    assert cat.remaining_quantity == 0, "Remaining quantity should be 0, never negative"

    total_tickets_issued = db.query(Ticket).filter(Ticket.ticket_category_id == cat.id).count()
    assert total_tickets_issued == 2, f"Total tickets issued must be exactly 2, got {total_tickets_issued}"
