from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.schemas import UserRegister, UserLogin, TokenResponse, UserOut
from app.services.auth_service import register_user, authenticate_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user."""
    return register_user(
        db, email=payload.email, username=payload.username, password=payload.password, full_name=payload.full_name
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    result = authenticate_user(db, username=payload.username, password=payload.password)
    return TokenResponse(**result)
