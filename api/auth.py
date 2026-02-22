import os
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

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
