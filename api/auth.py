import os
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from sqlmodel import Session
from api.database import get_session
from api.models import User, UserRole

load_dotenv()

# Initialize Firebase Admin
# Ensure GOOGLE_APPLICATION_CREDENTIALS is set in your env or pass a dict to Certificate
if not firebase_admin._apps:
    cred = credentials.Certificate(
        os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_credentials.json")
    )
    firebase_admin.initialize_app(cred)

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Verifies the Firebase JWT and returns the decoded token (dict).
    """
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_admin_user(
    token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> User:
    """
    Verifies that the user exists in the DB and has the ADMIN role.
    """
    uid = token.get("uid")
    user = session.get(User, uid)

    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
