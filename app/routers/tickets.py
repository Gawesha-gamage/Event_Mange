from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import Ticket, Event, User, TicketScanLog
from app.schemas import TicketScanRequest, TicketScanResponse
from app.auth import get_current_user, require_staff_or_admin
from app.agents import message_bus

router = APIRouter(prefix="/api/tickets", tags=["Digital Tickets & Gate Scanning"])

@router.get("/my")
def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve attendee's active digital tickets with individual unique QR codes."""
    tickets = db.query(Ticket).filter(
        Ticket.user_id == current_user.id
    ).order_by(Ticket.created_at.desc()).all()

    return [
        {
            "id": t.id,
            "unique_code": t.unique_code,
            "event_id": t.event_id,
            "event_title": t.event.title if t.event else "",
            "venue_name": t.event.venue.name if (t.event and t.event.venue) else "",
            "venue_location": t.event.venue.location if (t.event and t.event.venue) else "",
            "start_time": t.event.start_time if t.event else None,
            "category_name": t.category.name if t.category else "",
            "price": t.category.price if t.category else 0.0,
            "status": t.status,
            "qr_code_svg": t.qr_code_svg,
            "scanned_at": t.scanned_at
        } for t in tickets
    ]

@router.get("/{unique_code}/qr")
def get_ticket_qr(unique_code: str, db: Session = Depends(get_db)):
    """Serve embedded SVG QR code for direct browser viewing."""
    ticket = db.query(Ticket).filter(Ticket.unique_code == unique_code.upper()).first()
    if not ticket or not ticket.qr_code_svg:
        raise HTTPException(status_code=404, detail="Ticket QR not found.")
    return Response(content=ticket.qr_code_svg, media_type="image/svg+xml")

@router.post("/scan", response_model=TicketScanResponse)
def scan_ticket(
    scan_in: TicketScanRequest,
    current_staff: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db)
):
    """
    Gate Staff Scanner endpoint.
    Refuses unauthorized users without staff or admin role.
    Delegates validation and repeated scan detection to TicketAgent via Message Bus.
    """
    res = message_bus.send(
        db=db,
        sender="GateScannerRouter",
        receiver="TicketAgent",
        performative="REQUEST",
        content={
            "action": "verify_ticket",
            "ticket_code": scan_in.ticket_code.strip(),
            "scanner_user_id": current_staff.id,
            "event_id": scan_in.event_id
        }
    )

    content = res.get("content", {})
    performative = res.get("performative")

    is_success = (performative == "AGREE")
    result_code = content.get("result", "failure")
    message_text = content.get("message") or content.get("reason", "Scan processed.")

    return {
        "success": is_success,
        "result": result_code,
        "message": message_text,
        "ticket_code": scan_in.ticket_code.strip(),
        "attendee_name": content.get("attendee_name"),
        "event_title": content.get("event_title"),
        "category_name": content.get("category_name"),
        "is_suspicious": content.get("is_suspicious", False),
        "scanned_at": content.get("scanned_at")
    }

@router.get("/scan-logs")
def get_recent_scans(
    limit: int = 50,
    current_staff: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db)
):
    """Staff: View live gate scan history and suspicious activity alerts."""
    logs = db.query(TicketScanLog).order_by(TicketScanLog.scan_time.desc()).limit(limit).all()
    return logs
