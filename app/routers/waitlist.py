from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import WaitlistEntry, TicketCategory, Event, User
from app.schemas import WaitlistJoinRequest, WaitlistEntryResponse
from app.auth import get_current_user
from app.agents import message_bus, waitlist_agent

router = APIRouter(prefix="/api/waitlist", tags=["Waitlist System"])

@router.post("/join")
def join_waitlist(
    waitlist_in: WaitlistJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Attendee: Join waitlist for sold-out ticket category.
    Handled by WaitlistAgent.
    """
    res = message_bus.send(
        db=db,
        sender="WaitlistRouter",
        receiver="WaitlistAgent",
        performative="REQUEST",
        content={
            "action": "join_waitlist",
            "user_id": current_user.id,
            "ticket_category_id": waitlist_in.ticket_category_id,
            "requested_quantity": waitlist_in.requested_quantity
        }
    )

    if res.get("performative") == "REFUSE":
        raise HTTPException(status_code=400, detail=res.get("content", {}).get("reason"))

    return res.get("content", {})

@router.get("/my", response_model=List[WaitlistEntryResponse])
def get_my_waitlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Attendee: Check waitlist position and active timed seat holds.
    Includes remaining countdown in seconds for claimed seats.
    """
    entries = db.query(WaitlistEntry).filter(
        WaitlistEntry.user_id == current_user.id
    ).order_by(WaitlistEntry.created_at.desc()).all()

    now = datetime.utcnow()
    results = []
    for e in entries:
        category = db.query(TicketCategory).filter(TicketCategory.id == e.ticket_category_id).first()
        event = db.query(Event).filter(Event.id == e.event_id).first()

        remaining_secs = 0
        if e.status == "offered" and e.hold_expires_at:
            delta = (e.hold_expires_at - now).total_seconds()
            remaining_secs = max(0, int(delta))

        results.append({
            "id": e.id,
            "event_id": e.event_id,
            "event_title": event.title if event else "",
            "ticket_category_id": e.ticket_category_id,
            "category_name": category.name if category else "",
            "requested_quantity": e.requested_quantity,
            "status": e.status,
            "priority": e.priority,
            "offered_at": e.offered_at,
            "hold_expires_at": e.hold_expires_at,
            "seconds_remaining": remaining_secs,
            "created_at": e.created_at
        })

    return results

@router.post("/claim/{entry_id}")
def claim_seat(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Attendee: Claim and verify offered seat within the 5-minute countdown window.
    """
    res = message_bus.send(
        db=db,
        sender="WaitlistRouter",
        receiver="WaitlistAgent",
        performative="REQUEST",
        content={
            "action": "claim_seat",
            "user_id": current_user.id,
            "waitlist_entry_id": entry_id
        }
    )

    if res.get("performative") == "REFUSE":
        raise HTTPException(status_code=400, detail=res.get("content", {}).get("reason"))

    return res.get("content", {})

@router.post("/sweep")
def trigger_proactive_sweep(db: Session = Depends(get_db)):
    """
    Trigger the proactive expiry sweep (proactive agent behavior).
    Exposes timer sweep for manual triggering and automated workers.
    """
    reallocated = waitlist_agent.proactive_expiry_sweep(db=db, bus=message_bus)
    return {
        "status": "sweep_completed",
        "seats_reallocated": reallocated,
        "timestamp": datetime.utcnow().isoformat()
    }
