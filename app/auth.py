"""
JWT Authentication & Multi-Tenant Identity Provider for MoveInSync.
Guarantees that employee identity and company context are strictly extracted
from the verified cryptographic token, never from model output or user input.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from app.models import AuthenticatedUser

security = HTTPBearer(auto_error=False)

def create_access_token(
    employee_id: str,
    company_id: str,
    role: str = "employee",
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generates a signed JWT with strict tenant and user claims."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=JWT_EXPIRATION_HOURS)

    payload = {
        "sub": employee_id,
        "company_id": company_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }
    encoded_jwt = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> AuthenticatedUser:
    """Decodes and validates JWT claims."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        employee_id: str = payload.get("sub")
        company_id: str = payload.get("company_id")
        role: str = payload.get("role", "employee")

        if not employee_id or not company_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required identity claims (sub/company_id)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthenticatedUser(
            employee_id=employee_id,
            company_id=company_id,
            role=role
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency that extracts authenticated user from Bearer token.
    Identity is NEVER passed in the body or query params.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid Bearer scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)

def get_current_employee(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Ensures caller has an employee or manager role."""
    return user

def get_current_manager(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Ensures caller is a transport manager."""
    if user.role != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager privileges required for this action"
        )
    return user

