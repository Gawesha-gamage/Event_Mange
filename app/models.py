import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(180), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="attendee")  # admin, staff, attendee
    created_at = Column(DateTime, default=datetime.utcnow)
    
    bookings = relationship("Booking", back_populates="user")
    venue_hires = relationship("VenueHireRequest", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    waitlist_entries = relationship("WaitlistEntry", back_populates="user")

class Venue(Base):
    __tablename__ = "venues"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    location = Column(String(200), nullable=False)
    capacity = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    hourly_rate = Column(Float, nullable=False, default=100.0)
    is_open_for_private_hire = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    events = relationship("Event", back_populates="venue")
    hire_requests = relationship("VenueHireRequest", back_populates="venue")

class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)  # Concert, Workshop, Seminar, Conference, etc.
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    status = Column(String(20), default="draft")  # draft, published, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    
    venue = relationship("Venue", back_populates="events")
    ticket_categories = relationship("TicketCategory", back_populates="event", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="event")
    tickets = relationship("Ticket", back_populates="event")

class TicketCategory(Base):
    __tablename__ = "ticket_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)  # Standard, VIP, Student, Early Bird
    price = Column(Float, nullable=False, default=0.0)
    total_quantity = Column(Integer, nullable=False)
    remaining_quantity = Column(Integer, nullable=False)
    
    event = relationship("Event", back_populates="ticket_categories")
    tickets = relationship("Ticket", back_populates="category")

class CartHold(Base):
    __tablename__ = "cart_holds"
    
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(20), default="active")  # active, completed, expired

class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    booking_reference = Column(String(50), unique=True, index=True, default=lambda: f"BK-{uuid.uuid4().hex[:8].upper()}")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_reference = Column(String(100), nullable=False)
    status = Column(String(20), default="confirmed")  # confirmed, cancelled
    refund_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    cancelled_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="bookings")
    event = relationship("Event", back_populates="bookings")
    tickets = relationship("Ticket", back_populates="booking", cascade="all, delete-orphan")

class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    unique_code = Column(String(64), unique=True, index=True, default=lambda: f"TICK-{uuid.uuid4().hex[:12].upper()}")
    qr_code_svg = Column(Text, nullable=True)
    status = Column(String(20), default="valid")  # valid, used, cancelled
    scanned_at = Column(DateTime, nullable=True)
    scan_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    booking = relationship("Booking", back_populates="tickets")
    category = relationship("TicketCategory", back_populates="tickets")
    event = relationship("Event", back_populates="tickets")

class TicketScanLog(Base):
    __tablename__ = "ticket_scan_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_code = Column(String(64), index=True, nullable=False)
    scanner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    scan_time = Column(DateTime, default=datetime.utcnow)
    result = Column(String(40), nullable=False)  # admit, already_used, wrong_event, cancelled, outside_checkin_time
    reason = Column(String(255), nullable=True)
    is_suspicious = Column(Boolean, default=False)

class VenueHireRequest(Base):
    __tablename__ = "venue_hire_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    purpose = Column(String(255), nullable=False)
    guest_count = Column(Integer, nullable=False)
    status = Column(String(30), default="confirmed")  # confirmed, escalated, approved, rejected, cancelled
    calculated_price = Column(Float, nullable=False)
    decision_reason = Column(Text, nullable=True)
    counter_proposal = Column(JSON, nullable=True)  # Alternative times or venues if clash
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="venue_hires")
    venue = relationship("Venue", back_populates="hire_requests")

class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id", ondelete="CASCADE"), nullable=False)
    requested_quantity = Column(Integer, default=1)
    status = Column(String(20), default="waiting")  # waiting, offered, claimed, expired
    priority = Column(Integer, default=0)
    offered_at = Column(DateTime, nullable=True)
    hold_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="waitlist_entries")

class AgentMessage(Base):
    __tablename__ = "agent_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(64), index=True, nullable=False)
    sender = Column(String(60), nullable=False)
    receiver = Column(String(60), nullable=False)
    performative = Column(String(30), nullable=False)  # REQUEST, AGREE, REFUSE, PROPOSE, INFORM, FAILURE
    content = Column(JSON, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class AgentBelief(Base):
    __tablename__ = "agent_beliefs"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(60), index=True, nullable=False)
    belief_key = Column(String(100), index=True, nullable=False)
    belief_value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), default="system")
    is_read = Column(Boolean, default=False)
    simulated_email_sent = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="notifications")
