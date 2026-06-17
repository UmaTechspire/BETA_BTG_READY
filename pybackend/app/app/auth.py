import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from .database import get_db
from .models.user import User

load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
VALID_ISSUER = os.getenv("JWT_VALID_ISSUER", "http://localhost:5000")
VALID_AUDIENCE = os.getenv("JWT_VALID_AUDIENCE", "http://localhost:5000")

# Password Hashing
# Note: ASP.NET Identity often uses PBKDF2. 
# passlib's 'bcrypt' works for new hashes if we migrate to bcrypt.
# If validating existing .NET hashes, we might need a custom verifier.
# For now, we assume we use bcrypt for new/updated passwords.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Use HTTPBearer for simple token pasting in Swagger
security = HTTPBearer()

# Removed OAuth2PasswordBearer to avoid the complex username/password form in Swagger
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

def verify_password(plain_password, hashed_password):
    # 1. Try secure hash verification (bcrypt, etc.)
    try:
        if pwd_context.verify(plain_password, hashed_password):
            return True
    except Exception:
        pass
    
    # 2. Fallback: Check for Plaintext (Legacy/Migration support)
    # The database currently contains plaintext passwords (e.g., 'Password@12345')
    if plain_password == hashed_password:
        return True
        
    return False

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_db)):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM],
            audience=VALID_AUDIENCE,
            issuer=VALID_ISSUER
        )
        username: str = payload.get("sub")
        uid: str = payload.get("uid")
        
        if username is None and uid is None:
            print("Auth Error: Token missing sub and uid")
            raise credentials_exception
    except JWTError as e:
        print(f"Auth Error: JWT Decode Invalid: {e}")
        raise credentials_exception
        
    # Query DB
    user = None
    if uid:
        # Prioritize lookup by integer ID (more reliable)
        print(f"Auth Loopup: Checking User ID {uid}")
        try:
            result = await db.execute(select(User).where(User.Id == int(uid)))
            user = result.scalars().first()
        except Exception as e:
            print(f"Auth Error: DB Lookup by ID failed: {e}")

    if not user and username:
        # Fallback to username
        print(f"Auth Loopup: Checking Username {username}")
        result = await db.execute(select(User).where(User.UserName == username))
        user = result.scalars().first()
    
    if user is None:
        print("Auth Error: User not found in DB")
        raise credentials_exception
        
    return user
