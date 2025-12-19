# routers/auth_router.py
"""
Authentication API Router

This module handles all authentication-related endpoints:
- User registration
- User login
- User logout
- Token validation
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

import auth
from auth import require_auth, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============== Pydantic Models ==============

class UserRegisterRequest(BaseModel):
    """Request model for user registration"""
    username: str = Field(
        ..., 
        min_length=3, 
        max_length=50,
        description="Unique username (3-50 characters)",
        example="john_doe"
    )
    email: str = Field(
        ..., 
        description="Valid email address",
        example="john@example.com"
    )
    password: str = Field(
        ..., 
        min_length=6,
        description="Password (minimum 6 characters)",
        example="securePassword123"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "securePassword123"
            }
        }


class UserLoginRequest(BaseModel):
    """Request model for user login"""
    username: str = Field(
        ..., 
        description="Your username",
        example="john_doe"
    )
    password: str = Field(
        ..., 
        description="Your password",
        example="securePassword123"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "securePassword123"
            }
        }


class UserResponse(BaseModel):
    """User information response"""
    id: int
    username: str
    email: str


class LoginResponse(BaseModel):
    """Login success response"""
    success: bool
    token: str
    token_type: str
    expires_at: str
    user: UserResponse


class AuthCheckResponse(BaseModel):
    """Authentication check response"""
    authenticated: bool
    user: Optional[dict] = None


# ============== API Endpoints ==============

@router.post(
    "/register",
    summary="Register a new user",
    description="""
    Create a new user account.
    
    **Requirements:**
    - Username must be unique and 3-50 characters
    - Email must be unique and valid
    - Password must be at least 6 characters
    
    **Returns:** User information on success
    """,
    response_description="Registration successful",
    responses={
        200: {
            "description": "User registered successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "User registered successfully",
                        "user": {
                            "id": 1,
                            "username": "john_doe",
                            "email": "john@example.com"
                        }
                    }
                }
            }
        },
        400: {
            "description": "Registration failed (username/email exists or invalid data)",
            "content": {
                "application/json": {
                    "example": {"detail": "Username already exists"}
                }
            }
        }
    }
)
async def register(user_data: UserRegisterRequest):
    """Register a new user account"""
    try:
        user = auth.register_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password
        )
        return JSONResponse({
            "success": True,
            "message": "User registered successfully",
            "user": user
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/login",
    summary="Login and get access token",
    description="""
    Authenticate with username and password to receive a JWT access token.
    
    **Token Usage:**
    - Include the token in the `Authorization` header for protected endpoints
    - Format: `Bearer <your_token>`
    - Token expires after 7 days
    
    **Note:** Your IP address and User-Agent will be logged for security purposes.
    """,
    response_description="Login successful with access token",
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "expires_at": "2025-01-26T12:00:00",
                        "user": {
                            "id": 1,
                            "username": "john_doe",
                            "email": "john@example.com"
                        }
                    }
                }
            }
        },
        401: {
            "description": "Invalid credentials",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid username or password"}
                }
            }
        }
    }
)
async def login(user_data: UserLoginRequest, request: Request):
    """Authenticate and receive JWT token"""
    try:
        ip_address = auth.get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "unknown")
        
        result = auth.login_user(
            username=user_data.username,
            password=user_data.password,
            ip_address=ip_address,
            user_agent=user_agent
        )
        return JSONResponse({
            "success": True,
            **result
        })
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post(
    "/logout",
    summary="Logout current user",
    description="""
    Invalidate the current access token.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    After logout, the token will no longer be valid.
    """,
    response_description="Logout successful",
    responses={
        200: {
            "description": "Logged out successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Logged out successfully"
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def logout(current_user: dict = Depends(require_auth)):
    """Logout and invalidate token"""
    auth.logout_user(current_user["token"])
    return JSONResponse({
        "success": True,
        "message": "Logged out successfully"
    })


@router.get(
    "/me",
    summary="Get current user info",
    description="""
    Get information about the currently authenticated user.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    """,
    response_description="Current user information",
    responses={
        200: {
            "description": "User information retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "user": {
                            "id": 1,
                            "username": "john_doe",
                            "email": "john@example.com"
                        }
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def get_me(current_user: dict = Depends(require_auth)):
    """Get current authenticated user's information"""
    return JSONResponse({
        "success": True,
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "email": current_user["email"]
        }
    })


@router.get(
    "/check",
    summary="Check authentication status",
    description="""
    Check if the current request is authenticated.
    
    **🔓 No Authentication Required**
    
    This endpoint can be called with or without a token.
    - With valid token: Returns `authenticated: true` with user info
    - Without token or invalid: Returns `authenticated: false`
    
    Useful for frontend to check login status on page load.
    """,
    response_description="Authentication status",
    responses={
        200: {
            "description": "Authentication status",
            "content": {
                "application/json": {
                    "examples": {
                        "authenticated": {
                            "summary": "User is authenticated",
                            "value": {
                                "authenticated": True,
                                "user": {
                                    "id": 1,
                                    "username": "john_doe"
                                }
                            }
                        },
                        "not_authenticated": {
                            "summary": "User is not authenticated",
                            "value": {
                                "authenticated": False
                            }
                        }
                    }
                }
            }
        }
    }
)
async def check_auth(current_user: dict = Depends(get_current_user)):
    """Check if user is authenticated"""
    if current_user:
        return JSONResponse({
            "authenticated": True,
            "user": {
                "id": current_user["id"],
                "username": current_user["username"]
            }
        })
    return JSONResponse({"authenticated": False})
