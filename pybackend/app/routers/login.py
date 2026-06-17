import os
import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime, timedelta
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from sqlalchemy.future import select
from sqlalchemy import update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from jose import jwt, JWTError
from dotenv import load_dotenv
import uuid

from .. import database
# Models mapping to AspNet tables
from ..models.users_refresh import AspNetUsers
from ..models.roles import AspNetRoles
from ..models.user_roles import AspNetUserRoles
from ..models.user import User

load_dotenv()

# =========================================================
# CONFIGURATION
# =========================================================
SECRET_KEY = os.getenv("SECRET_KEY", "YourSecretKey") 
VALID_ISSUER = os.getenv("JWT_VALID_ISSUER", "http://localhost:5000")
VALID_AUDIENCE = os.getenv("JWT_VALID_AUDIENCE", "http://localhost:5000")
TOKEN_VALIDITY_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_VALIDITY_DAYS = int(os.getenv("REFRESH_TOKEN_VALIDITY_DAYS", "7"))

ALGORITHM = "HS256"

router = APIRouter(
    prefix="/api/Authenticate",
    tags=["Authenticate"]
)

# =========================================================
# SCHEMAS
# =========================================================

class LoginModel(BaseModel):
    Username: str
    Password: str

class RegisterModel(BaseModel):
    Username: str
    Email: str
    Password: str

class TokenModel(BaseModel):
    AccessToken: Optional[str] = None
    RefreshToken: Optional[str] = None

# =========================================================
# HELPERS: PASSWORD HASHING
# =========================================================

def verify_aspnet_password(hashed_password_b64: str, provided_password: str) -> bool:
    """
    Verifies a password against ASP.NET Core Identity (V2/V3) AND Plaintext fallback.
    """
    if not hashed_password_b64:
        return False
    
    # 1. Plaintext Fallback (Common in UAT/Dev environments)
    if hashed_password_b64 == provided_password:
        return True

    try:
        decoded_hash = base64.b64decode(hashed_password_b64)
    except:
        return False

    if len(decoded_hash) == 0:
        return False

    try:
        version = decoded_hash[0]
        
        # --- V3 Logic (Default for .NET Core) ---
        if version == 0x01:
            if len(decoded_hash) < 13:
                return False
            
            prf_byte = decoded_hash[1]
            if prf_byte == 0:
                hash_alg = hashlib.sha1
            elif prf_byte == 1:
                hash_alg = hashlib.sha256
            elif prf_byte == 2:
                hash_alg = hashlib.sha512
            else:
                return False

            iter_count = struct.unpack(">I", decoded_hash[2:6])[0]
            salt_len = struct.unpack(">I", decoded_hash[6:10])[0]

            if len(decoded_hash) < 10 + salt_len:
                return False

            salt = decoded_hash[10:10 + salt_len]
            stored_subkey = decoded_hash[10 + salt_len:]

            derived_subkey = hashlib.pbkdf2_hmac(
                hash_alg().name, 
                provided_password.encode('utf-8'), 
                salt, 
                iter_count, 
                dklen=32
            )

            return hmac.compare_digest(derived_subkey, stored_subkey)

        # --- V2 Logic (Legacy / .NET Framework) ---
        elif version == 0x00:
            if len(decoded_hash) != 49:
                return False
                
            salt = decoded_hash[1:17]
            stored_subkey = decoded_hash[17:49]
            
            derived_subkey = hashlib.pbkdf2_hmac(
                'sha1',
                provided_password.encode('utf-8'),
                salt,
                1000,
                dklen=32
            )
            
            return hmac.compare_digest(derived_subkey, stored_subkey)

        else:
            return False

    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def hash_aspnet_password(password: str) -> str:
    # V3 Hash
    prf_byte = 1 # SHA256
    iter_count = 10000
    salt_size = 128 // 8
    salt = secrets.token_bytes(salt_size)
    subkey = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iter_count, dklen=32)
    
    output = bytearray()
    output.append(0x01)
    output.append(prf_byte)
    output.extend(struct.pack(">I", iter_count))
    output.extend(struct.pack(">I", salt_size))
    output.extend(salt)
    output.extend(subkey)
    
    return base64.b64encode(output).decode('ascii')

# =========================================================
# HELPERS: TOKEN UTILS
# =========================================================

def create_token(auth_claims: dict):
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_VALIDITY_MINUTES)
    to_encode = auth_claims.copy()
    to_encode.update({"exp": expire, "iss": VALID_ISSUER, "aud": VALID_AUDIENCE})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

def generate_refresh_token():
    return base64.b64encode(secrets.token_bytes(64)).decode('utf-8')

def get_principal_from_expired_token(token: str):
    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM], 
            options={"verify_exp": False, "verify_aud": False, "verify_iss": False}
        )
        return payload
    except JWTError:
        return None

# =========================================================
# API ENDPOINTS
# =========================================================

@router.post("/login")
async def login(model: LoginModel, db: AsyncSession = Depends(database.get_db)):
    print(f"Login Attempt: {model.Username}")

    # 1. Find User
    stmt = select(AspNetUsers).where(
        (AspNetUsers.UserName == model.Username) | 
        (AspNetUsers.NormalizedUserName == model.Username.upper())
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        # ILIKE Fallback
        stmt = select(AspNetUsers).where(func.lower(AspNetUsers.UserName) == model.Username.lower())
        result = await db.execute(stmt)
        user = result.scalars().first()

    if not user:
        print("User not found in DB")
        return {
            "data": {
                "token": "",
                "refreshToken": "",
                "expiration": "",
                "userId": "",
                "isAdmin": 0
            },
            "message": "Login Failure",
            "status": False,
            "statusCode": 0
        }

    print(f"User found: {user.UserName}, Checking password...")
    
    # 2. Check Password
    password_valid = False
    if user.PasswordHash:
        password_valid = verify_aspnet_password(user.PasswordHash, model.Password)
    else:
        print("User has no PasswordHash")

    # 2.1 Fallback: Check 'users' table if AspNetUsers password failed
    # User mentioned that 'users' table has plaintext password
    if not password_valid:
        if user.userid:
             print(f"Primary hash check failed. Checking fallback 'users' table for user ID: {user.userid}")
             stmt_legacy = select(User).where(User.Id == user.userid)
             result_legacy = await db.execute(stmt_legacy)
             legacy_user = result_legacy.scalars().first()
             
             if legacy_user:
                 # Check plaintext password
                 if legacy_user.Password == model.Password:
                     print("Fallback login successful via 'users' table (Plaintext match)")
                     password_valid = True
                 else:
                     print("Fallback 'users' table password mismatch")
             else:
                 print("No corresponding user found in 'users' table")
        else:
             print("No 'userid' link to 'users' table")

    if not password_valid:
        print("Password verification failed")
        return {
            "data": {
                "token": "",
                "refreshToken": "",
                "expiration": "",
                "userId": "",
                "isAdmin": 0
            },
            "message": "Login Failure",
            "status": False,
            "statusCode": 0
        }

    # Check IsActive
    if hasattr(user, 'IsActive') and user.IsActive is False:
         print("User account is inactive")
         return {
            "data": {
                "token": "",
                "refreshToken": "",
                "expiration": "",
                "userId": "",
                "isAdmin": 0
            },
            "message": "This account has been deactivated",
            "status": False
        }

    # 3. Get Roles
    roles_stmt = select(AspNetRoles.Name)\
        .join(AspNetUserRoles, AspNetUserRoles.RoleId == AspNetRoles.Id)\
        .where(AspNetUserRoles.UserId == user.Id)
    
    roles_result = await db.execute(roles_stmt)
    user_roles = roles_result.scalars().all()

    # 4. Build Claims
    auth_claims = {
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": user.UserName,
        "sub": user.UserName,
        "uid": str(user.userid) if user.userid else None,
        "jti": str(uuid.uuid4()),
        "http://schemas.microsoft.com/ws/2008/06/identity/claims/role": user_roles if len(user_roles) > 1 else (user_roles[0] if user_roles else None)
    }

    token, expiration = create_token(auth_claims)
    refresh_token = generate_refresh_token()

    # 5. Update User Refresh Token
    user.RefreshToken = refresh_token
    user.RefreshTokenExpiryTime = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_VALIDITY_DAYS)
    
    await db.commit()
    await db.refresh(user)

    # 6. Admin Flags
    is_admin = 0
    if "Admin" in user_roles:
        is_admin = 1
    elif "User" in user_roles:
        is_admin = 0
    
    super_is_admin = 0
    if "SuperAdmin" in user_roles:
        super_is_admin = 1
    
    # 7. Get Department Info from users table
    department_id = None
    department_name = None
    if user.userid:
        stmt_user = select(User).where(User.Id == user.userid)
        result_user = await db.execute(stmt_user)
        user_record = result_user.scalars().first()
        if user_record:
            department_id = user_record.DepartmentId
            department_name = user_record.Department
    
    print("Login Success")
    return {
        "data": {
            "token": token,
            "refreshToken": refresh_token,
            "expiration": expiration,
            "userId": user.Id,
            "isAdmin": is_admin,
            "u_Id": user.userid,
            "superIsAdmin": super_is_admin,
            "roleName": user_roles[0] if user_roles else "",
            "departmentId": department_id,
            "department": department_name
        },
        "status": True,
        "message": "Success",
        "statusCode": 0
    }

@router.post("/register")
async def register(model: RegisterModel, db: AsyncSession = Depends(database.get_db)):
    # Check Exists
    stmt = select(AspNetUsers).where(AspNetUsers.NormalizedUserName == model.Username.upper())
    result = await db.execute(stmt)
    if result.scalars().first():
        return HTTPException(status_code=500, detail={"Status": "Error", "Message": "User already exists!"})

    new_user_id = str(uuid.uuid4())
    new_user = AspNetUsers(
        Id=new_user_id,
        Email=model.Email,
        SecurityStamp=str(uuid.uuid4()),
        UserName=model.Username,
        NormalizedUserName=model.Username.upper(),
        NormalizedEmail=model.Email.upper() if model.Email else None,
        PasswordHash=hash_aspnet_password(model.Password),
        CreatedDate=datetime.utcnow(),
        IsActive=True
    )
    
    db.add(new_user)
    
    role_res = await db.execute(select(AspNetRoles).where(AspNetRoles.Name == "User"))
    role = role_res.scalars().first()
    
    if not role:
        role_id = str(uuid.uuid4())
        role = AspNetRoles(Id=role_id, Name="User", NormalizedName="USER")
        db.add(role)
        await db.flush()
    
    user_role = AspNetUserRoles(UserId=new_user.Id, RoleId=role.Id)
    db.add(user_role)
    
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        return HTTPException(status_code=500, detail={"Status": "Error", "Message": "User creation failed!"})

    return {"Status": "Success", "Message": "User created successfully!"}

@router.post("/register-admin")
async def register_admin(model: RegisterModel, db: AsyncSession = Depends(database.get_db)):
    stmt = select(AspNetUsers).where(AspNetUsers.NormalizedUserName == model.Username.upper())
    result = await db.execute(stmt)
    if result.scalars().first():
        return HTTPException(status_code=500, detail={"Status": "Error", "Message": "User already exists!"})

    new_user_id = str(uuid.uuid4())
    new_user = AspNetUsers(
        Id=new_user_id,
        Email=model.Email,
        SecurityStamp=str(uuid.uuid4()),
        UserName=model.Username,
        NormalizedUserName=model.Username.upper(),
        PasswordHash=hash_aspnet_password(model.Password),
        CreatedDate=datetime.utcnow(),
        IsActive=True
    )
    db.add(new_user)

    for role_name in ["Admin", "User"]:
        role_res = await db.execute(select(AspNetRoles).where(AspNetRoles.Name == role_name))
        role = role_res.scalars().first()
        
        if not role:
            role = AspNetRoles(Id=str(uuid.uuid4()), Name=role_name, NormalizedName=role_name.upper())
            db.add(role)
            await db.flush()
        
        db.add(AspNetUserRoles(UserId=new_user.Id, RoleId=role.Id))
    
    try:
        await db.commit()
    except:
        await db.rollback()
        return HTTPException(status_code=500, detail={"Status": "Error", "Message": "User creation failed!"})

    return {"Status": "Success", "Message": "User created successfully!"}

@router.post("/refresh-token")
async def refresh_token_endpoint(token_model: TokenModel, db: AsyncSession = Depends(database.get_db)):
    if not token_model or not token_model.AccessToken or not token_model.RefreshToken:
        return {
            "data": None,
            "message": "Invalid client request",
            "status": False
        }

    principal = get_principal_from_expired_token(token_model.AccessToken)
    if not principal:
         return {
            "data": None,
            "message": "Invalid access token or refresh token",
            "status": False
        }

    username = principal.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
    if not username:
        username = principal.get("sub")
    
    if not username:
         return {
            "data": None,
            "message": "Invalid access token or refresh token",
            "status": False
        }

    stmt = select(AspNetUsers).where(
        (AspNetUsers.UserName == username) | 
        (AspNetUsers.NormalizedUserName == username.upper())
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or user.RefreshToken != token_model.RefreshToken or user.RefreshTokenExpiryTime <= datetime.utcnow():
         return {
            "data": None,
            "message": "Invalid access token or refresh token",
            "status": False
        }

    new_claims = principal.copy()
    if 'exp' in new_claims: del new_claims['exp']
    if 'iat' in new_claims: del new_claims['iat']
    if 'nbf' in new_claims: del new_claims['nbf']
    
    new_access_token, _ = create_token(new_claims)
    new_refresh_token = generate_refresh_token()

    user.RefreshToken = new_refresh_token
    await db.commit()

    return {
        "data": {
            "accessToken": new_access_token,
            "refreshToken": new_refresh_token
        },
        "message": "Success",
        "status": True
    }

@router.post("/revoke/{username}")
async def revoke(username: str, db: AsyncSession = Depends(database.get_db)):
    stmt = select(AspNetUsers).where(AspNetUsers.UserName == username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        return HTTPException(status_code=400, detail="Invalid user name")

    user.RefreshToken = None
    await db.commit()

    return status.HTTP_204_NO_CONTENT

@router.post("/revoke-all")
async def revoke_all(db: AsyncSession = Depends(database.get_db)):
    await db.execute(update(AspNetUsers).values(RefreshToken=None))
    await db.commit()
    return status.HTTP_204_NO_CONTENT
