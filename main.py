import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.agents import message_bus, waitlist_agent
from app.routers import (
    auth, venues, events, bookings, tickets, venue_hire, waitlist, dashboard, agent_inbox
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("EventSphereApp")

# Create all database tables
Base.metadata.create_all(bind=engine)

async def proactive_waitlist_worker():
    """
    Proactive agent scheduler:
    Runs in the background with NO user action required.
    Triggers WaitlistAgent's expiry sweep periodically to reallocate unclaimed seats.
    """
    logger.info("Autonomous WaitlistAgent proactive sweep worker started.")
    while True:
        try:
            await asyncio.sleep(settings.WAITLIST_SWEEP_INTERVAL_SECONDS)
            db = SessionLocal()
            try:
                reallocated = waitlist_agent.proactive_expiry_sweep(db=db, bus=message_bus)
                if reallocated > 0:
                    logger.info(f"[PROACTIVE AGENT] Reallocated {reallocated} expired waitlist seat(s).")
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("WaitlistAgent proactive sweep worker stopped.")
            break
        except Exception as e:
            logger.error(f"Error in proactive waitlist sweep worker: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch proactive agent background worker (when not in unit test mode)
    worker_task = None
    is_test = os.environ.get("TESTING") == "1" or os.environ.get("ENVIRONMENT") == "testing"
    if not is_test:
        worker_task = asyncio.create_task(proactive_waitlist_worker())
    yield
    # Shutdown: Cleanly cancel background worker
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

is_test = os.environ.get("TESTING") == "1" or os.environ.get("ENVIRONMENT") == "testing"

app = FastAPI(
    title="EventSphere - Multi-Agent Venue Booking & Digital Ticketing Platform",
    description=(
        "IT4123 Agent Based Computing Practical Assignment. "
        "A full-stack, mobile-friendly venue booking and digital ticketing platform where every booking decision "
        "is made by cooperating autonomous software agents (VenueAgent, BookingAgent, TicketAgent, WaitlistAgent, NotificationAgent)."
    ),
    version="2.0.0",
    lifespan=None if is_test else lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API Routers
app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(bookings.router)
app.include_router(tickets.router)
app.include_router(venue_hire.router)
app.include_router(waitlist.router)
app.include_router(dashboard.router)
app.include_router(agent_inbox.router)

# Ensure static directories exist
os.makedirs("app/static/css", exist_ok=True)
os.makedirs("app/static/js", exist_ok=True)
os.makedirs("app/static/img", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Frontend routes serving mobile-friendly web interfaces
@app.get("/", response_class=FileResponse)
def index_view():
    return FileResponse("app/templates/index.html")

@app.get("/scanner", response_class=FileResponse)
def scanner_view():
    return FileResponse("app/templates/staff.html")

@app.get("/admin", response_class=FileResponse)
def admin_view():
    return FileResponse("app/templates/admin.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
