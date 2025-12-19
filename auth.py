# auth.py
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from functools import wraps
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import database as db

# Configuration
SECRET_KEY = secrets.token_hex(32)  # In production, use environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 1 week

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Hash password using SHA256 with salt"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{pwd_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash"""
    try:
        salt, pwd_hash = stored_hash.split(':')
        return hashlib.sha256((password + salt).encode()).hexdigest() == pwd_hash
    except ValueError:
        return False

def create_access_token(user_id: int, username: str) -> tuple[str, datetime]:
    """Create JWT access token"""
    expires_at = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expires_at,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, expires_at

def decode_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    # Check for forwarded headers (if behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    return request.client.host if request.client else "unknown"

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[dict]:
    """Get current user from JWT token (dependency for protected routes)"""
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = decode_token(token)
    
    if not payload:
        return None
    
    # Check if session is still valid in database
    session = db.get_session(token)
    if not session:
        return None
    
    # Get user
    user = db.get_user_by_id(payload["user_id"])
    if not user or not user["is_active"]:
        return None
    
    # Log IP access
    ip_address = get_client_ip(request)
    db.log_user_ip(user["id"], ip_address)
    
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "token": token
    }

async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Require authentication (raises exception if not authenticated)"""
    user = await get_current_user(request, credentials)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user

def register_user(username: str, email: str, password: str) -> dict:
    """Register a new user"""
    # Validate input
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    if "@" not in email:
        raise ValueError("Invalid email address")
    
    # Hash password and create user
    password_hash = hash_password(password)
    user_id = db.create_user(username, email, password_hash)
    
    return {
        "id": user_id,
        "username": username,
        "email": email
    }

def login_user(username: str, password: str, ip_address: str, user_agent: str) -> dict:
    """Authenticate user and return token"""
    # Get user
    user = db.get_user_by_username(username)
    if not user:
        raise ValueError("Invalid username or password")
    
    # Verify password
    if not verify_password(password, user["password_hash"]):
        raise ValueError("Invalid username or password")
    
    # Check if user is active
    if not user["is_active"]:
        raise ValueError("Account is disabled")
    
    # Create token
    token, expires_at = create_access_token(user["id"], user["username"])
    
    # Create session
    db.create_session(user["id"], token, ip_address, user_agent, expires_at)
    
    # Update last login
    db.update_last_login(user["id"])
    
    # Log IP
    db.log_user_ip(user["id"], ip_address)
    
    return {
        "token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"]
        }
    }

def logout_user(token: str):
    """Logout user by invalidating session"""
    db.invalidate_session(token)
