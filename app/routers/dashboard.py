from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from app.database import get_db
from app.models import (
    Event, Venue, Booking, Ticket, TicketScanLog,
    VenueHireRequest, AgentMessage, AgentBelief, User
)
from app.auth import require_admin

router = APIRouter(prefix="/api/dashboard", tags=["Organiser Dashboard & Agent Logs"])

@router.get("/stats")
def get_dashboard_stats(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Organiser dashboard metrics:
    Tickets sold, simulated revenue, check-ins and capacity per event.
    """
    total_events = db.query(Event).filter(Event.status != "cancelled").count()
    total_venues = db.query(Venue).count()
    
    # Active bookings & tickets
    tickets_sold = db.query(Ticket).filter(Ticket.status.in_(["valid", "used"])).count()
    total_revenue = db.query(func.sum(Booking.total_amount)).filter(Booking.status == "confirmed").scalar() or 0.0
    total_checkins = db.query(Ticket).filter(Ticket.status == "used").count()
    active_hires = db.query(VenueHireRequest).filter(VenueHireRequest.status == "escalated").count()

    events = db.query(Event).order_by(Event.start_time.asc()).all()
    events_overview = []
    for e in events:
        cap = sum(c.total_quantity for c in e.ticket_categories)
        sold = db.query(Ticket).filter(Ticket.event_id == e.id, Ticket.status.in_(["valid", "used"])).count()
        admitted = db.query(Ticket).filter(Ticket.event_id == e.id, Ticket.status == "used").count()
        rev = db.query(func.sum(Booking.total_amount)).filter(Booking.event_id == e.id, Booking.status == "confirmed").scalar() or 0.0
        
        events_overview.append({
            "event_id": e.id,
            "title": e.title,
            "venue_name": e.venue.name if e.venue else "N/A",
            "capacity": cap,
            "tickets_sold": sold,
            "checkins": admitted,
            "simulated_revenue": round(rev, 2),
            "status": e.status,
            "attendance_rate": f"{(admitted / sold * 100):.1f}%" if sold > 0 else "0%"
        })

    return {
        "total_events": total_events,
        "total_venues": total_venues,
        "total_tickets_sold": tickets_sold,
        "total_simulated_revenue": round(total_revenue, 2),
        "total_checkins": total_checkins,
        "active_hire_requests": active_hires,
        "events_overview": events_overview
    }

@router.get("/charts")
def get_dashboard_charts(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Part C: Visual charts data:
    1. Sales per event
    2. Check-ins vs Capacity per event
    3. Ticket status distribution
    4. Hourly scan traffic
    """
    events = db.query(Event).limit(8).all()
    event_titles = [e.title[:20] for e in events]
    sales_data = []
    checkin_data = []
    capacity_data = []

    for e in events:
        sold = db.query(Ticket).filter(Ticket.event_id == e.id, Ticket.status.in_(["valid", "used"])).count()
        admitted = db.query(Ticket).filter(Ticket.event_id == e.id, Ticket.status == "used").count()
        cap = sum(c.total_quantity for c in e.ticket_categories)
        sales_data.append(sold)
        checkin_data.append(admitted)
        capacity_data.append(cap)

    # Status distribution
    valid_count = db.query(Ticket).filter(Ticket.status == "valid").count()
    used_count = db.query(Ticket).filter(Ticket.status == "used").count()
    cancelled_count = db.query(Ticket).filter(Ticket.status == "cancelled").count()

    return {
        "events_chart": {
            "labels": event_titles,
            "sales": sales_data,
            "checkins": checkin_data,
            "capacities": capacity_data
        },
        "ticket_status_chart": {
            "labels": ["Valid (Unused)", "Admitted", "Cancelled"],
            "data": [valid_count, used_count, cancelled_count]
        }
    }

@router.get("/agent-logs")
def get_agent_message_logs(
    conversation_id: Optional[str] = None,
    sender: Optional[str] = None,
    receiver: Optional[str] = None,
    performative: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin dashboard: Readable log of messages exchanged between agents.
    Allows tracing a single user action across multiple cooperating agents by conversation_id!
    """
    query = db.query(AgentMessage)
    if conversation_id:
        query = query.filter(AgentMessage.conversation_id.ilike(f"%{conversation_id}%"))
    if sender:
        query = query.filter(AgentMessage.sender == sender)
    if receiver:
        query = query.filter(AgentMessage.receiver == receiver)
    if performative:
        query = query.filter(AgentMessage.performative == performative)

    messages = query.order_by(AgentMessage.timestamp.desc()).limit(limit).all()

    return [
        {
            "id": m.id,
            "conversation_id": m.conversation_id,
            "sender": m.sender,
            "receiver": m.receiver,
            "performative": m.performative,
            "content": m.content,
            "timestamp": m.timestamp.isoformat()
        } for m in messages
    ]

@router.get("/agent-beliefs")
def get_agent_beliefs(
    agent_name: Optional[str] = None,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Inspect persistent agent beliefs surviving server restarts."""
    query = db.query(AgentBelief)
    if agent_name:
        query = query.filter(AgentBelief.agent_name == agent_name)
    beliefs = query.order_by(AgentBelief.agent_name.asc(), AgentBelief.updated_at.desc()).all()
    return beliefs
