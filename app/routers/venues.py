from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import Venue, User
from app.schemas import VenueCreate, VenueUpdate, VenueResponse
from app.auth import require_admin

router = APIRouter(prefix="/api/venues", tags=["Venues Management"])

@router.get("", response_model=List[VenueResponse])
def list_venues(
    open_for_hire_only: bool = False,
    min_capacity: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List venues for event creation and private hire browsing."""
    query = db.query(Venue)
    if open_for_hire_only:
        query = query.filter(Venue.is_open_for_private_hire == True)
    if min_capacity is not None:
        query = query.filter(Venue.capacity >= min_capacity)
    return query.order_by(Venue.name.asc()).all()

@router.get("/{venue_id}", response_model=VenueResponse)
def get_venue(venue_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a single venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    return venue

@router.post("", response_model=VenueResponse, status_code=status.HTTP_201_CREATED)
def create_venue(
    venue_in: VenueCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Register a new venue."""
    venue = Venue(
        name=venue_in.name.strip(),
        location=venue_in.location.strip(),
        capacity=venue_in.capacity,
        description=venue_in.description,
        image_url=venue_in.image_url,
        hourly_rate=venue_in.hourly_rate,
        is_open_for_private_hire=venue_in.is_open_for_private_hire
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return venue

@router.put("/{venue_id}", response_model=VenueResponse)
def update_venue(
    venue_id: int,
    venue_in: VenueUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Update an existing venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")

    update_data = venue_in.dict(exclude_unset=True)
    for field, val in update_data.items():
        setattr(venue, field, val)

    db.commit()
    db.refresh(venue)
    return venue

@router.delete("/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_venue(
    venue_id: int,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin: Remove a venue."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found.")
    db.delete(venue)
    db.commit()
    return None
