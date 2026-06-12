import os
import json
import logging
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
    firebase_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_json_str:
        # Running on Railway: Parse the JSON string from the environment variable
        cred_dict = json.loads(firebase_json_str)
        cred = credentials.Certificate(cred_dict)
    else:
        # Running locally: Load from the local generic JSON file
        cred = credentials.Certificate(
            os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_credentials.json")
        )
    firebase_admin.initialize_app(cred)

security = HTTPBearer()

logger = logging.getLogger(__name__)


def verify_token(token: str) -> dict:
    """
    Verifies a Firebase JWT and returns the decoded token (dict).
    Raises HTTPException(401) on failure without leaking verifier internals.
    """
    try:
        return auth.verify_id_token(token)
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Verifies the Firebase JWT from the Authorization header.
    """
    return verify_token(credentials.credentials)


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
