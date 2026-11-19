import pytest
from fastapi import HTTPException
from app.routers.auth import register, login
from app.schemas import UserRegister, UserLogin
from app.auth import verify_password, require_admin, require_staff_or_admin
from app.models import User

def test_user_registration_and_password_hashing(db):
    """Accounts & Roles Test: Attendees can register and login; passwords stored hashed."""
    reg_in = UserRegister(
        name="Bob Martin",
        email="bob@university.ac.uk",
        password="SecretPassword@123",
        role="attendee"
    )
    res = register(user_in=reg_in, db=db)
    assert res["email"] == "bob@university.ac.uk"
    assert "access_token" in res

    # Verify password in database is hashed, never plain text
    user = db.query(User).filter(User.email == "bob@university.ac.uk").first()
    assert user is not None
    assert user.hashed_password != "SecretPassword@123"
    assert verify_password("SecretPassword@123", user.hashed_password) is True

    # Test login
    login_in = UserLogin(email="bob@university.ac.uk", password="SecretPassword@123")
    login_res = login(login_data=login_in, db=db)
    assert "access_token" in login_res

def test_role_enforcement_admin_and_staff(demo_users):
    """Accounts & Roles Test: Admin and scanner routes refuse users without the right role."""
    attendee_user = demo_users["attendee"]
    staff_user = demo_users["staff"]
    admin_user = demo_users["admin"]

    # 1. require_admin: Attendee must be refused with 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        require_admin(current_user=attendee_user)
    assert exc_info.value.status_code == 403
    assert "lacks permission" in exc_info.value.detail

    # Staff must be refused with 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        require_admin(current_user=staff_user)
    assert exc_info.value.status_code == 403

    # Admin must be admitted
    assert require_admin(current_user=admin_user) == admin_user

    # 2. require_staff_or_admin: Attendee must be refused with 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        require_staff_or_admin(current_user=attendee_user)
    assert exc_info.value.status_code == 403

    # Staff and Admin must both be admitted
    assert require_staff_or_admin(current_user=staff_user) == staff_user
    assert require_staff_or_admin(current_user=admin_user) == admin_user
