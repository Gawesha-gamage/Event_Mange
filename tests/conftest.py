import os
os.environ["ENVIRONMENT"] = "testing"
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User, Venue, Event, TicketCategory
from app.auth import get_password_hash, create_access_token
from main import app

TEST_DB_FILE = "test_eventsphere.db"
if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except Exception:
        pass

engine_test = create_engine(
    f"sqlite:///{TEST_DB_FILE}",
    connect_args={"check_same_thread": False, "timeout": 30}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine_test)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine_test)

@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, raise_server_exceptions=True)
    yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def demo_users(db):
    admin = User(
        name="Test Admin",
        email="test_admin@eventsphere.ac.uk",
        hashed_password=get_password_hash("Admin@123"),
        role="admin"
    )
    staff = User(
        name="Test Staff",
        email="test_staff@eventsphere.ac.uk",
        hashed_password=get_password_hash("Staff@123"),
        role="staff"
    )
    attendee = User(
        name="Test Attendee",
        email="test_attendee@eventsphere.ac.uk",
        hashed_password=get_password_hash("Attendee@123"),
        role="attendee"
    )
    db.add_all([admin, staff, attendee])
    db.commit()
    db.refresh(admin)
    db.refresh(staff)
    db.refresh(attendee)
    return {"admin": admin, "staff": staff, "attendee": attendee}

@pytest.fixture
def auth_headers(demo_users):
    def _get_headers(role: str):
        user = demo_users[role]
        token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
        return {"Authorization": f"Bearer {token}"}
    return _get_headers
