from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import VenueHireRequest, Venue, User
from app.schemas import VenueHireCreate, VenueHireDecision, VenueHireAdminAction
from app.auth import get_current_user, require_admin
from app.agents import message_bus

router = APIRouter(prefix="/api/venue-hire", tags=["Private Venue Hire"])

@router.post("", response_model=VenueHireDecision, status_code=status.HTTP_201_CREATED)
def request_venue_hire(
    hire_in: VenueHireCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Attendee: Submit private venue hire request.
    Decided autonomously by VenueAgent:
    - Routine requests confirmed immediately.
    - Clashes receive counter-proposals with alternative times or venues.
    - Large scale requests escalated for administrative sign-off.
    """
    if hire_in.end_time <= hire_in.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    # Create pending hire record
    hire_record = VenueHireRequest(
        user_id=current_user.id,
        venue_id=hire_in.venue_id,
        start_time=hire_in.start_time,
        end_time=hire_in.end_time,
        purpose=hire_in.purpose.strip(),
        guest_count=hire_in.guest_count,
        status="pending",
        calculated_price=0.0
    )
    db.add(hire_record)
    db.commit()
    db.refresh(hire_record)

    # Communicate with VenueAgent
    res = message_bus.send(
        db=db,
        sender="VenueHireRouter",
        receiver="VenueAgent",
        performative="REQUEST",
        content={
            "action": "request_private_hire",
            "hire_id": hire_record.id,
            "venue_id": hire_in.venue_id,
            "user_id": current_user.id,
            "start_time": hire_in.start_time.isoformat(),
            "end_time": hire_in.end_time.isoformat(),
            "guest_count": hire_in.guest_count,
            "purpose": hire_in.purpose.strip()
        }
    )

    performative = res.get("performative")
    content = res.get("content", {})

    if performative == "REFUSE":
        hire_record.status = "rejected"
        hire_record.decision_reason = content.get("reason")
        db.commit()
        raise HTTPException(status_code=400, detail=content.get("reason"))

    elif performative == "PROPOSE":
        hire_record.status = "counter_proposal"
        hire_record.calculated_price = content.get("calculated_price", 0.0)
        hire_record.decision_reason = content.get("reason")
        hire_record.counter_proposal = content.get("alternatives")
        db.commit()
        return {
            "request_id": hire_record.id,
            "status": "counter_proposal",
            "calculated_price": hire_record.calculated_price,
            "decision_reason": content.get("reason", "Slot unavailable. Alternatives proposed."),
            "counter_proposal": content.get("alternatives")
        }

    else:
        # AGREE or INFORM (escalated)
        decision_status = content.get("decision", "confirmed")
        hire_record.status = decision_status
        hire_record.calculated_price = content.get("calculated_price", 0.0)
        hire_record.decision_reason = content.get("reason")
        db.commit()

        return {
            "request_id": hire_record.id,
            "status": decision_status,
            "calculated_price": hire_record.calculated_price,
            "decision_reason": content.get("reason", "Venue hire processed."),
            "counter_proposal": None
        }

@router.get("/my")
def get_my_hire_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Attendee: View personal private venue hire requests and decisions."""
    requests = db.query(VenueHireRequest).filter(
        VenueHireRequest.user_id == current_user.id
    ).order_by(VenueHireRequest.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "venue_id": r.venue_id,
            "venue_name": r.venue.name if r.venue else "",
            "start_time": r.start_time,
            "end_time": r.end_time,
            "purpose": r.purpose,
            "guest_count": r.guest_count,
            "status": r.status,
            "calculated_price": r.calculated_price,
            "decision_reason": r.decision_reason,
            "counter_proposal": r.counter_proposal,
            "created_at": r.created_at
        } for r in requests
    ]

@router.get("")
def list_all_hire_requests(
    status_filter: Optional[str] = None,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Monitor all private hire applications and escalated requests."""
    query = db.query(VenueHireRequest)
    if status_filter:
        query = query.filter(VenueHireRequest.status == status_filter)
    
    requests = query.order_by(VenueHireRequest.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "attendee_name": r.user.name if r.user else "Unknown",
            "attendee_email": r.user.email if r.user else "",
            "venue_id": r.venue_id,
            "venue_name": r.venue.name if r.venue else "",
            "start_time": r.start_time,
            "end_time": r.end_time,
            "purpose": r.purpose,
            "guest_count": r.guest_count,
            "status": r.status,
            "calculated_price": r.calculated_price,
            "decision_reason": r.decision_reason,
            "created_at": r.created_at
        } for r in requests
    ]

@router.post("/{hire_id}/action")
def admin_hire_action(
    hire_id: int,
    action_in: VenueHireAdminAction,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Approve or reject an escalated venue hire request."""
    hire = db.query(VenueHireRequest).filter(VenueHireRequest.id == hire_id).first()
    if not hire:
        raise HTTPException(status_code=404, detail="Hire request not found.")

    new_status = "approved" if action_in.action == "approve" else "rejected"
    hire.status = new_status
    if action_in.notes:
        hire.decision_reason = f"{hire.decision_reason or ''} [Admin Notes: {action_in.notes}]".strip()
    db.commit()

    # Inform user via NotificationAgent
    message_bus.send(
        db=db,
        sender="AdminAction",
        receiver="NotificationAgent",
        performative="REQUEST",
        content={
            "user_id": hire.user_id,
            "title": f"Venue Hire Decision: {new_status.capitalize()}",
            "message": f"Your escalated request for {hire.venue.name if hire.venue else 'Venue'} has been {new_status} by university administration.",
            "type": "hire"
        }
    )

    return {"message": f"Hire request {hire_id} marked as {new_status}."}
