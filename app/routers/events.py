from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import Event, Venue, TicketCategory, User
from app.schemas import EventCreate, EventUpdate, EventResponse
from app.auth import require_admin
from app.agents import message_bus

router = APIRouter(prefix="/api/events", tags=["Events Management & Browsing"])

def serialize_event(event: Event) -> dict:
    total_cap = sum(cat.total_quantity for cat in event.ticket_categories)
    remaining = sum(cat.remaining_quantity for cat in event.ticket_categories)
    return {
        "id": event.id,
        "title": event.title,
        "category": event.category,
        "venue_id": event.venue_id,
        "venue_name": event.venue.name if event.venue else None,
        "venue_location": event.venue.location if event.venue else None,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "description": event.description,
        "image_url": event.image_url,
        "status": event.status,
        "total_capacity": total_cap,
        "total_remaining_tickets": remaining,
        "ticket_categories": [
            {
                "id": cat.id,
                "event_id": cat.event_id,
                "name": cat.name,
                "price": cat.price,
                "total_quantity": cat.total_quantity,
                "remaining_quantity": cat.remaining_quantity
            } for cat in event.ticket_categories
        ],
        "created_at": event.created_at
    }

@router.get("", response_model=List[EventResponse])
def list_events(
    search: Optional[str] = None,
    category: Optional[str] = None,
    venue_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status_filter: Optional[str] = "published",
    db: Session = Depends(get_db)
):
    """
    Search and filter events for attendees and organisers.
    Supports keyword search, category filter, and Advanced Search (dates, venue, price range).
    """
    query = db.query(Event)

    if status_filter != "all":
        query = query.filter(Event.status == status_filter)

    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.filter(
            (Event.title.ilike(search_fmt)) |
            (Event.description.ilike(search_fmt)) |
            (Event.category.ilike(search_fmt))
        )

    if category and category != "All":
        query = query.filter(Event.category == category)

    if venue_id:
        query = query.filter(Event.venue_id == venue_id)

    if start_date:
        query = query.filter(Event.start_time >= start_date)

    if end_date:
        query = query.filter(Event.end_time <= end_date)

    events = query.order_by(Event.start_time.asc()).all()

    # Filter by price range if requested
    results = []
    for e in events:
        serialized = serialize_event(e)
        if min_price is not None or max_price is not None:
            prices = [c["price"] for c in serialized["ticket_categories"]]
            if not prices:
                continue
            event_min = min(prices)
            event_max = max(prices)
            if min_price is not None and event_max < min_price:
                continue
            if max_price is not None and event_min > max_price:
                continue
        results.append(serialized)

    return results

@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """Retrieve event details including tickets left per category."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    return serialize_event(event)

@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    event_in: EventCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin: Create and schedule a new event.
    Consults VenueAgent via Agent Message Bus to enforce turnaround buffer and capacity bounds.
    """
    if event_in.end_time <= event_in.start_time:
        raise HTTPException(status_code=400, detail="Event end time must be after start time.")

    if not event_in.ticket_categories:
        raise HTTPException(status_code=400, detail="An event must have at least one ticket category.")

    total_tickets = sum(cat.total_quantity for cat in event_in.ticket_categories)

    # Communicate with VenueAgent via structured message!
    agent_res = message_bus.send(
        db=db,
        sender="EventRouter",
        receiver="VenueAgent",
        performative="REQUEST",
        content={
            "action": "validate_event_slot",
            "venue_id": event_in.venue_id,
            "start_time": event_in.start_time.isoformat(),
            "end_time": event_in.end_time.isoformat(),
            "total_tickets": total_tickets
        }
    )

    if agent_res.get("performative") == "REFUSE":
        raise HTTPException(
            status_code=400,
            detail=agent_res.get("content", {}).get("reason", "VenueAgent refused the scheduling request.")
        )

    # VenueAgent agreed; create event record
    new_event = Event(
        title=event_in.title.strip(),
        category=event_in.category.strip(),
        venue_id=event_in.venue_id,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        description=event_in.description,
        image_url=event_in.image_url,
        status=event_in.status or "published"
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    # Create ticket categories
    for cat_in in event_in.ticket_categories:
        cat = TicketCategory(
            event_id=new_event.id,
            name=cat_in.name.strip(),
            price=cat_in.price,
            total_quantity=cat_in.total_quantity,
            remaining_quantity=cat_in.total_quantity
        )
        db.add(cat)
    db.commit()
    db.refresh(new_event)

    return serialize_event(new_event)

@router.put("/{event_id}", response_model=EventResponse)
def update_event(
    event_id: int,
    event_in: EventUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Edit an event."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    update_data = event_in.dict(exclude_unset=True)
    for field, val in update_data.items():
        setattr(event, field, val)

    db.commit()
    db.refresh(event)
    return serialize_event(event)

@router.post("/{event_id}/cancel")
def cancel_event(
    event_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin: Cancel a published event.
    Instructs BookingAgent via Agent Message Bus to trigger full 100% refunds.
    """
    agent_res = message_bus.send(
        db=db,
        sender="EventRouter",
        receiver="BookingAgent",
        performative="REQUEST",
        content={
            "action": "cancel_event",
            "event_id": event_id
        }
    )

    if agent_res.get("performative") == "REFUSE":
        raise HTTPException(status_code=400, detail=agent_res.get("content", {}).get("reason"))

    return {
        "message": f"Event {event_id} has been cancelled.",
        "details": agent_res.get("content", {})
    }
