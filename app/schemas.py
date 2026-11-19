from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

# User Schemas
class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=180)
    password: str = Field(..., min_length=6)
    role: Optional[str] = "attendee"  # admin, staff, attendee

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    name: str
    email: str
    role: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime
    class Config:
        from_attributes = True

# Venue Schemas
class VenueBase(BaseModel):
    name: str
    location: str
    capacity: int = Field(..., gt=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    hourly_rate: float = Field(..., ge=0)
    is_open_for_private_hire: bool = True

class VenueCreate(VenueBase):
    pass

class VenueUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    capacity: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    hourly_rate: Optional[float] = None
    is_open_for_private_hire: Optional[bool] = None

class VenueResponse(VenueBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

# Ticket Category Schemas
class TicketCategoryCreate(BaseModel):
    name: str
    price: float = Field(..., ge=0)
    total_quantity: int = Field(..., gt=0)

class TicketCategoryResponse(BaseModel):
    id: int
    event_id: int
    name: str
    price: float
    total_quantity: int
    remaining_quantity: int
    class Config:
        from_attributes = True

# Event Schemas
class EventCreate(BaseModel):
    title: str
    category: str
    venue_id: int
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    image_url: Optional[str] = None
    ticket_categories: List[TicketCategoryCreate]
    status: Optional[str] = "published"  # draft or published

class EventUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    venue_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    status: Optional[str] = None

class EventResponse(BaseModel):
    id: int
    title: str
    category: str
    venue_id: int
    venue_name: Optional[str] = None
    venue_location: Optional[str] = None
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    image_url: Optional[str] = None
    status: str
    total_capacity: int = 0
    total_remaining_tickets: int = 0
    ticket_categories: List[TicketCategoryResponse] = []
    created_at: datetime
    class Config:
        from_attributes = True

# Cart Hold Schemas (Part C)
class CartHoldCreate(BaseModel):
    ticket_category_id: int
    quantity: int = Field(..., gt=0, le=6)

class CartHoldResponse(BaseModel):
    hold_id: str
    ticket_category_id: int
    quantity: int
    expires_at: datetime
    seconds_remaining: int

# Booking Schemas
class BookingCreate(BaseModel):
    ticket_category_id: int
    quantity: int = Field(..., gt=0, le=6)
    cart_hold_id: Optional[str] = None
    cardholder_name: Optional[str] = "Simulated User"
    payment_method: Optional[str] = "simulated_card"  # Simulated only!

class TicketSummary(BaseModel):
    id: int
    unique_code: str
    category_name: str
    qr_code_svg: Optional[str] = None
    status: str
    class Config:
        from_attributes = True

class BookingResponse(BaseModel):
    id: int
    booking_reference: str
    event_id: int
    event_title: Optional[str] = None
    venue_name: Optional[str] = None
    start_time: Optional[datetime] = None
    total_amount: float
    payment_reference: str
    status: str
    refund_amount: float
    created_at: datetime
    tickets: List[TicketSummary] = []
    class Config:
        from_attributes = True

class CancelBookingResponse(BaseModel):
    booking_id: int
    status: str
    refund_amount: float
    refund_percentage: int
    message: str

# Check-in / Ticket Scan Schemas
class TicketScanRequest(BaseModel):
    ticket_code: str
    event_id: Optional[int] = None  # Specific gate event filter

class TicketScanResponse(BaseModel):
    success: bool
    result: str  # admit, already_used, wrong_event, cancelled, outside_checkin_time
    message: str
    ticket_code: str
    attendee_name: Optional[str] = None
    event_title: Optional[str] = None
    category_name: Optional[str] = None
    is_suspicious: bool = False
    scanned_at: Optional[datetime] = None

# Private Venue Hire Schemas
class VenueHireCreate(BaseModel):
    venue_id: int
    start_time: datetime
    end_time: datetime
    purpose: str
    guest_count: int = Field(..., gt=0)

class VenueHireDecision(BaseModel):
    request_id: int
    status: str  # confirmed, escalated, rejected, counter_proposal
    calculated_price: float
    decision_reason: str
    counter_proposal: Optional[Dict[str, Any]] = None

class VenueHireAdminAction(BaseModel):
    action: str  # approve or reject
    notes: Optional[str] = None

# Waitlist Schemas
class WaitlistJoinRequest(BaseModel):
    ticket_category_id: int
    requested_quantity: int = Field(1, ge=1, le=4)

class WaitlistEntryResponse(BaseModel):
    id: int
    event_id: int
    event_title: Optional[str] = None
    ticket_category_id: int
    category_name: Optional[str] = None
    requested_quantity: int
    status: str
    priority: int
    offered_at: Optional[datetime] = None
    hold_expires_at: Optional[datetime] = None
    seconds_remaining: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True

# Agent Message & Log Schemas
class AgentMessageSchema(BaseModel):
    id: Optional[int] = None
    conversation_id: str
    sender: str
    receiver: str
    performative: str  # REQUEST, AGREE, REFUSE, PROPOSE, INFORM, FAILURE
    content: Dict[str, Any]
    timestamp: Optional[datetime] = None
    class Config:
        from_attributes = True

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str
    is_read: bool
    created_at: datetime
    class Config:
        from_attributes = True

# Dashboard Stats Schemas
class DashboardStats(BaseModel):
    total_events: int
    total_venues: int
    total_tickets_sold: int
    total_simulated_revenue: float
    total_checkins: int
    active_hire_requests: int
    events_overview: List[Dict[str, Any]]
