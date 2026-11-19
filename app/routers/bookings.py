import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import Booking, CartHold, TicketCategory, Event, User, Ticket
from app.schemas import (
    CartHoldCreate, CartHoldResponse,
    BookingCreate, BookingResponse, CancelBookingResponse
)
from app.auth import get_current_user
from app.agents import message_bus

router = APIRouter(prefix="/api/bookings", tags=["Bookings & Payments"])

@router.post("/hold", response_model=CartHoldResponse)
def hold_cart_tickets(
    hold_in: CartHoldCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Part C: Place a 5-minute timed hold on tickets while the attendee completes simulated payment.
    Handled by BookingAgent.
    """
    res = message_bus.send(
        db=db,
        sender="BookingRouter",
        receiver="BookingAgent",
        performative="REQUEST",
        content={
            "action": "hold_tickets",
            "user_id": current_user.id,
            "ticket_category_id": hold_in.ticket_category_id,
            "quantity": hold_in.quantity
        }
    )

    if res.get("performative") == "REFUSE":
        raise HTTPException(
            status_code=400,
            detail=res.get("content", {}).get("reason", "Hold refused by BookingAgent.")
        )

    content = res.get("content", {})
    return {
        "hold_id": content["hold_id"],
        "ticket_category_id": hold_in.ticket_category_id,
        "quantity": content["quantity"],
        "expires_at": datetime.fromisoformat(content["expires_at"]),
        "seconds_remaining": content["seconds_remaining"]
    }

@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    booking_in: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Purchase tickets with simulated payment reference.
    Enforces concurrency safety and fair allocation through BookingAgent.
    """
    simulated_payment_ref = f"SIM-PAY-{uuid.uuid4().hex[:8].upper()}"

    res = message_bus.send(
        db=db,
        sender="BookingRouter",
        receiver="BookingAgent",
        performative="REQUEST",
        content={
            "action": "book_tickets",
            "user_id": current_user.id,
            "ticket_category_id": booking_in.ticket_category_id,
            "quantity": booking_in.quantity,
            "cart_hold_id": booking_in.cart_hold_id,
            "payment_reference": simulated_payment_ref
        }
    )

    if res.get("performative") == "REFUSE":
        content = res.get("content", {})
        raise HTTPException(
            status_code=400,
            detail={
                "reason": content.get("reason", "Booking refused."),
                "can_join_waitlist": content.get("can_join_waitlist", False),
                "remaining": content.get("remaining", 0)
            }
        )

    content = res.get("content", {})
    booking_id = content["booking_id"]
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    return {
        "id": booking.id,
        "booking_reference": booking.booking_reference,
        "event_id": booking.event_id,
        "event_title": booking.event.title,
        "venue_name": booking.event.venue.name if booking.event.venue else None,
        "start_time": booking.event.start_time,
        "total_amount": booking.total_amount,
        "payment_reference": booking.payment_reference,
        "status": booking.status,
        "refund_amount": booking.refund_amount,
        "created_at": booking.created_at,
        "tickets": [
            {
                "id": t.id,
                "unique_code": t.unique_code,
                "category_name": t.category.name if t.category else "",
                "qr_code_svg": t.qr_code_svg,
                "status": t.status
            } for t in booking.tickets
        ]
    }

@router.get("/my", response_model=List[BookingResponse])
def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve attendee's full booking history."""
    bookings = db.query(Booking).filter(
        Booking.user_id == current_user.id
    ).order_by(Booking.created_at.desc()).all()

    results = []
    for b in bookings:
        results.append({
            "id": b.id,
            "booking_reference": b.booking_reference,
            "event_id": b.event_id,
            "event_title": b.event.title if b.event else None,
            "venue_name": b.event.venue.name if (b.event and b.event.venue) else None,
            "start_time": b.event.start_time if b.event else None,
            "total_amount": b.total_amount,
            "payment_reference": b.payment_reference,
            "status": b.status,
            "refund_amount": b.refund_amount,
            "created_at": b.created_at,
            "tickets": [
                {
                    "id": t.id,
                    "unique_code": t.unique_code,
                    "category_name": t.category.name if t.category else "",
                    "qr_code_svg": t.qr_code_svg,
                    "status": t.status
                } for t in b.tickets
            ]
        })
    return results

@router.post("/{booking_id}/cancel", response_model=CancelBookingResponse)
def cancel_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel an attendee's booking.
    Calculates refund strictly based on stated policy via BookingAgent,
    and automatically re-offers released seats to the waitlist.
    """
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.user_id == current_user.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    res = message_bus.send(
        db=db,
        sender="BookingRouter",
        receiver="BookingAgent",
        performative="REQUEST",
        content={
            "action": "cancel_booking",
            "booking_id": booking_id,
            "user_id": current_user.id
        }
    )

    if res.get("performative") == "REFUSE":
        raise HTTPException(status_code=400, detail=res.get("content", {}).get("reason"))

    content = res.get("content", {})
    return {
        "booking_id": booking.id,
        "status": content.get("status", "cancelled"),
        "refund_amount": content.get("refund_amount", 0.0),
        "refund_percentage": content.get("refund_percentage", 0),
        "message": content.get("reason", "Booking successfully cancelled.")
    }
