from datetime import datetime, timedelta
import uuid
from app.database import SessionLocal, engine, Base
from app.models import (
    User, Venue, Event, TicketCategory, Booking, Ticket,
    VenueHireRequest, WaitlistEntry, AgentBelief
)
from app.auth import get_password_hash
from app.agents import ticket_agent

def seed():
    print("Initializing EventSphere database schema...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Creating demo accounts...")
        # 1. Demo Accounts (Requirement 7 & Part A)
        admin_user = User(
            name="Dr. Eleanor Vance (Admin Organiser)",
            email="admin@eventsphere.ac.uk",
            hashed_password=get_password_hash("Admin@123"),
            role="admin"
        )
        staff_user = User(
            name="Marcus Brody (Entrance Gate Staff)",
            email="staff@eventsphere.ac.uk",
            hashed_password=get_password_hash("Staff@123"),
            role="staff"
        )
        attendee_user = User(
            name="Sophie Turner (Student Attendee)",
            email="attendee@eventsphere.ac.uk",
            hashed_password=get_password_hash("Attendee@123"),
            role="attendee"
        )
        attendee_user2 = User(
            name="James Wilson (Public Attendee)",
            email="james@eventsphere.ac.uk",
            hashed_password=get_password_hash("James@123"),
            role="attendee"
        )
        db.add_all([admin_user, staff_user, attendee_user, attendee_user2])
        db.commit()

        print("Creating campus venues...")
        # 2. Venues
        v1 = Venue(
            name="University Great Hall",
            location="Main Quadrangle, Building 1",
            capacity=400,
            hourly_rate=150.0,
            description="Historic auditorium with grand acoustics, proscenium stage, and full AV suite.",
            image_url="https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&auto=format&fit=crop&q=60",
            is_open_for_private_hire=True
        )
        v2 = Venue(
            name="Alan Turing Tech Theatre",
            location="Computer Science Complex, North Wing",
            capacity=180,
            hourly_rate=95.0,
            description="Tiered smart lecture theatre equipped with dual 4K laser projectors and live recording.",
            image_url="https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800&auto=format&fit=crop&q=60",
            is_open_for_private_hire=True
        )
        v3 = Venue(
            name="Arts & Music Pavilion",
            location="West Gardens, Riverside",
            capacity=120,
            hourly_rate=80.0,
            description="Acoustically tuned recital space with scenic views of university lakes and botanical gardens.",
            image_url="https://images.unsplash.com/photo-1469488865564-c2de10f69f96?w=800&auto=format&fit=crop&q=60",
            is_open_for_private_hire=True
        )
        v4 = Venue(
            name="Council Chambers (Executive)",
            location="Senate House, Level 4",
            capacity=50,
            hourly_rate=200.0,
            description="Executive boardroom for solemn academic ceremonies and high-level symposia.",
            image_url="https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop&q=60",
            is_open_for_private_hire=False  # Closed for private hire
        )
        db.add_all([v1, v2, v3, v4])
        db.commit()

        print("Scheduling university events & ticket categories...")
        # 3. Events & Ticket Categories
        now = datetime.utcnow()

        # Event 1: Tech Conference
        e1_start = now + timedelta(days=5, hours=10)
        e1_end = e1_start + timedelta(hours=6)
        e1 = Event(
            title="Global AI & Agent-Based Computing Summit 2026",
            category="Conference",
            venue_id=v1.id,
            start_time=e1_start,
            end_time=e1_end,
            description="Leading researchers and industry pioneers gather to demonstrate multi-agent architectures, autonomous reasoning, and decentralized systems.",
            image_url="https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=800&auto=format&fit=crop&q=60",
            status="published"
        )
        db.add(e1)
        db.commit()

        cat1_std = TicketCategory(event_id=e1.id, name="General Admission", price=25.0, total_quantity=150, remaining_quantity=148)
        cat1_vip = TicketCategory(event_id=e1.id, name="VIP & Dinner Pass", price=60.0, total_quantity=40, remaining_quantity=40)
        cat1_stu = TicketCategory(event_id=e1.id, name="Student Pass", price=10.0, total_quantity=100, remaining_quantity=99)
        db.add_all([cat1_std, cat1_vip, cat1_stu])

        # Event 2: Philharmonic Concert
        e2_start = now + timedelta(days=2, hours=18)
        e2_end = e2_start + timedelta(hours=3)
        e2 = Event(
            title="Autumn Philharmonic Symphony: Holst & Beethoven",
            category="Concert",
            venue_id=v1.id,
            start_time=e2_start,
            end_time=e2_end,
            description="University Symphony Orchestra performing Gustav Holst's The Planets and Beethoven's Symphony No. 7.",
            image_url="https://images.unsplash.com/photo-1465847899084-d164df4dedc6?w=800&auto=format&fit=crop&q=60",
            status="published"
        )
        db.add(e2)
        db.commit()

        cat2_std = TicketCategory(event_id=e2.id, name="Stalls Standard", price=20.0, total_quantity=200, remaining_quantity=199)
        cat2_vip = TicketCategory(event_id=e2.id, name="Balcony Premium", price=35.0, total_quantity=50, remaining_quantity=50)
        db.add_all([cat2_std, cat2_vip])

        # Event 3: Sold out workshop (for Waitlist testing!)
        e3_start = now + timedelta(days=3, hours=14)
        e3_end = e3_start + timedelta(hours=4)
        e3 = Event(
            title="Hands-on FastAPI & Distributed Agent Systems Workshop",
            category="Workshop",
            venue_id=v2.id,
            start_time=e3_start,
            end_time=e3_end,
            description="Build robust asynchronous microservices with FastAPI, Pydantic, and FIPA performative agent message buses.",
            image_url="https://images.unsplash.com/photo-1531482615713-2afd69097998?w=800&auto=format&fit=crop&q=60",
            status="published"
        )
        db.add(e3)
        db.commit()

        cat3_soldout = TicketCategory(event_id=e3.id, name="Workshop Seat (Sold Out)", price=15.0, total_quantity=30, remaining_quantity=0)
        db.add(cat3_soldout)
        db.commit()

        print("Issuing demo bookings & digital tickets with QR codes...")
        # 4. Demo Bookings & QR Tickets for attendee
        b1 = Booking(
            user_id=attendee_user.id,
            event_id=e1.id,
            total_amount=50.0,
            payment_reference="SIM-PAY-987412A",
            status="confirmed"
        )
        db.add(b1)
        db.commit()

        code1 = "TICK-DEMO-VALID-01"
        code2 = "TICK-DEMO-VALID-02"
        t1 = Ticket(
            booking_id=b1.id,
            ticket_category_id=cat1_std.id,
            user_id=attendee_user.id,
            event_id=e1.id,
            unique_code=code1,
            qr_code_svg=ticket_agent.generate_qr_svg(code1),
            status="valid"
        )
        t2 = Ticket(
            booking_id=b1.id,
            ticket_category_id=cat1_std.id,
            user_id=attendee_user.id,
            event_id=e1.id,
            unique_code=code2,
            qr_code_svg=ticket_agent.generate_qr_svg(code2),
            status="valid"
        )
        db.add_all([t1, t2])

        # Demo used ticket (already admitted)
        b2 = Booking(
            user_id=attendee_user.id,
            event_id=e2.id,
            total_amount=20.0,
            payment_reference="SIM-PAY-882194B",
            status="confirmed"
        )
        db.add(b2)
        db.commit()

        code_used = "TICK-DEMO-USED-99"
        t_used = Ticket(
            booking_id=b2.id,
            ticket_category_id=cat2_std.id,
            user_id=attendee_user.id,
            event_id=e2.id,
            unique_code=code_used,
            qr_code_svg=ticket_agent.generate_qr_svg(code_used),
            status="used",
            scanned_at=now - timedelta(minutes=45),
            scan_count=1
        )
        db.add(t_used)

        print("Seeding private venue hire requests...")
        # 5. Private Venue Hire Requests
        hire1 = VenueHireRequest(
            user_id=attendee_user.id,
            venue_id=v3.id,
            start_time=now + timedelta(days=7, hours=19),
            end_time=now + timedelta(days=7, hours=23),
            purpose="Acoustic Society Live Jam & Alumni Reception",
            guest_count=60,
            status="confirmed",
            calculated_price=384.0,
            decision_reason="Routine private hire request automatically confirmed by VenueAgent."
        )
        hire2_escalated = VenueHireRequest(
            user_id=attendee_user2.id,
            venue_id=v1.id,
            start_time=now + timedelta(days=10, hours=18),
            end_time=now + timedelta(days=10, hours=23),
            purpose="International Students Union Cultural Gala Dinner",
            guest_count=250,
            status="escalated",
            calculated_price=1175.0,
            decision_reason="Escalated for administrative approval due to high scale: 250 guests (threshold: 100) and/or £1175.0 total value."
        )
        db.add_all([hire1, hire2_escalated])

        print("Initializing persistent agent beliefs...")
        # 6. Persistent Agent Beliefs
        b_venue = AgentBelief(agent_name="VenueAgent", belief_key="turnaround_buffer_mins", belief_value=60)
        b_booking = AgentBelief(agent_name="BookingAgent", belief_key="max_tickets_per_order", belief_value=6)
        b_ticket = AgentBelief(agent_name="TicketAgent", belief_key="suspicious_scans_total", belief_value=0)
        b_waitlist = AgentBelief(agent_name="WaitlistAgent", belief_key="hold_duration_seconds", belief_value=300)
        db.add_all([b_venue, b_booking, b_ticket, b_waitlist])

        db.commit()
        print("EventSphere database successfully seeded with demo accounts and data!")
        print("Demo Accounts:")
        print(" - Admin Organiser: admin@eventsphere.ac.uk / Admin@123")
        print(" - Gate Staff:      staff@eventsphere.ac.uk / Staff@123")
        print(" - Student Attendee: attendee@eventsphere.ac.uk / Attendee@123")
        print(f"Sample Ticket Codes ready for QR Scanner: {code1}, {code2}, {code_used} (already used)")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
