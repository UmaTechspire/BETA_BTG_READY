from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, update, insert
from typing import List, Optional, Any
from datetime import datetime, date
from pydantic import BaseModel
from ... import database, auth
from ...models.user import User as UserModel
from ...models.users_refresh import AspNetUsers
from ...models.roles import AspNetRoles
from ...models.user_roles import AspNetUserRoles
import uuid
import secrets
import hashlib
import base64
import struct

# Helper: Password Hashing (Matches login.py V3 Logic)
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


router = APIRouter(
    prefix="/api/MasterUsers",
    tags=["MasterUsers"]
)

# =====================================================
# REQUEST SCHEMAS
# =====================================================

class CreateUserCommand(BaseModel):
    """Matches CreateUserCommand from .NET"""
    userid: Optional[str] = None # Used as string ID in .NET Identity, optional here
    Id: Optional[int] = 0
    UserName: str
    EmailID: Optional[str] = None
    MobileNo: Optional[str] = None
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    Password: Optional[str] = None
    Role: Optional[str] = None
    RoleName: Optional[str] = None
    Department: Optional[str] = None
    FromDate: Optional[datetime] = None
    ToDate: Optional[datetime] = None
    MiddleName: Optional[str] = None
    Remark: Optional[str] = None
    BranchId: Optional[int] = None
    # CreatedBy is purposely omitted from schema; populated from Auth Token

class UpdatePasswordUserCommand(BaseModel):
    """Matches UpdatePasswordUserCommand from .NET"""
    userid: Optional[str] = None
    Id: Optional[int] = None
    Password: str
    oldPassword: Optional[str] = None

class UserStatusQuery(BaseModel):
    """Matches UserStatusQuery from .NET"""
    UserId: int
    Remark: Optional[str] = ""
    IsActive: bool
    BranchId: Optional[int] = None

class GetAllUserQuery(BaseModel):
    """Matches GetAllUserQuery from .NET"""
    ProdId: Optional[int] = None
    FromDate: Optional[str] = None
    ToDate: Optional[str] = None
    BranchId: Optional[int] = None
    Username: Optional[str] = None
    Keyword: Optional[str] = None
    PageNumber: Optional[int] = None
    PageSize: Optional[int] = None

class UserDto(BaseModel):
    Id: int
    UserName: Optional[str] = None
    Email: Optional[str] = None
    PhoneNumber: Optional[str] = None
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    MiddleName: Optional[str] = None
    Role: Optional[str] = None
    Department: Optional[str] = None
    BranchId: Optional[int] = None
    OrgId: Optional[int] = None
    IsActive: Optional[bool] = None
    FromDate: Optional[date] = None
    ToDate: Optional[date] = None
    Remarks: Optional[str] = None
    
    class Config:
        from_attributes = True

class GetUserByIdQuery(BaseModel):
    """Matches GetUserByIdQuery from .NET"""
    UserId: int
    BranchId: int

# =====================================================
# RESPONSE SCHEMAS
# =====================================================

class ResponseModel(BaseModel):
    """Standard Response Model"""
    Data: Optional[Any] = None
    Message: str
    Status: bool
    StatusCode: int

# =====================================================
# API ENDPOINTS
# =====================================================

@router.post("/create-update", response_model=ResponseModel)
async def create_user(
    command: CreateUserCommand,
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: UserModel = Depends(auth.get_current_user)
):
    try:
        # Determine User ID from Token for CreatedBy/LastModifiedBy
        actor_id = current_user.Id
        client_ip = request.client.host if request.client else "127.0.0.1"

        # 1. Determine if we are updating or creating
        existing_user = None
        if command.Id and command.Id > 0:
            result = await db.execute(select(UserModel).where(UserModel.Id == command.Id))
            existing_user = result.scalars().first()

        # Fallback: Check by UserName if not found by ID (Upsert Logic)
        if not existing_user and command.UserName:
            stmt_name = select(UserModel).where(UserModel.UserName == command.UserName)
            result_name = await db.execute(stmt_name)
            existing_user = result_name.scalars().first()
            if existing_user:
                print(f"User found by Name: {existing_user.UserName} (ID: {existing_user.Id}). Switching to Update.")

        # 2. UPDATE SCENARIO
        if existing_user:
            # Update Fields
            existing_user.UserName = command.UserName
            existing_user.Email = command.EmailID
            existing_user.PhoneNumber = command.MobileNo
            existing_user.FirstName = command.FirstName
            existing_user.LastName = command.LastName
            existing_user.MiddleName = command.MiddleName
            existing_user.Role = command.RoleName or command.Role # .NET uses RoleName sometimes
            existing_user.Department = command.Department
            existing_user.Remarks = command.Remark
            existing_user.OrgId = 1 # Default or from token? Assuming default for now logic isn't clear in .NET controller
            existing_user.BranchId = command.BranchId
            
            if command.FromDate:
                existing_user.FromDate = command.FromDate.date()
            if command.ToDate:
                existing_user.ToDate = command.ToDate.date()

            # Audit Fields
            existing_user.LastModifiedBy = actor_id
            existing_user.LastModifiedDate = datetime.utcnow()
            existing_user.LastModifiedIP = client_ip

            # Update Password (if provided)
            new_password_hash = None
            if command.Password is not None:
                existing_user.Password = command.Password
                new_password_hash = hash_aspnet_password(command.Password)

            # =========================================================
            # SYNC ASPNETUSERS (Matches .NET Controller Logic)
            # =========================================================
            # Find Identity User by 'userid' (Link to users table)
            stmt_identity = select(AspNetUsers).where(AspNetUsers.userid == existing_user.Id)
            res_identity = await db.execute(stmt_identity)
            identity_user = res_identity.scalars().first()
            
            if not identity_user:
                # Try finding by UserName if link checks fail or legacy mismatch
                stmt_identity = select(AspNetUsers).where(AspNetUsers.UserName == command.UserName)
                res_identity = await db.execute(stmt_identity)
                identity_user = res_identity.scalars().first()

            if identity_user:
                identity_user.Email = command.EmailID
                identity_user.NormalizedEmail = command.EmailID.upper() if command.EmailID else None
                identity_user.PhoneNumber = command.MobileNo
                identity_user.UserName = command.UserName
                identity_user.NormalizedUserName = command.UserName.upper()
                identity_user.userid = existing_user.Id # Ensure link is tight
                
                if new_password_hash:
                    identity_user.PasswordHash = new_password_hash
                    identity_user.SecurityStamp = str(uuid.uuid4())

                # Update Role
                role_name = command.RoleName or command.Role
                if role_name:
                    # 1. Get/Create Role
                    stmt_role = select(AspNetRoles).where(AspNetRoles.Name == role_name)
                    res_role = await db.execute(stmt_role)
                    role_obj = res_role.scalars().first()
                    
                    if not role_obj:
                         role_obj = AspNetRoles(Id=str(uuid.uuid4()), Name=role_name, NormalizedName=role_name.upper())
                         db.add(role_obj)
                         await db.flush() # Get ID
                    
                    # 2. Check Existing UserRole
                    stmt_ur = select(AspNetUserRoles).where(AspNetUserRoles.UserId == identity_user.Id)
                    res_ur = await db.execute(stmt_ur)
                    current_links = res_ur.scalars().all()
                    
                    # Remove old (naive approach: remove all, add new)
                    # .NET logic: RemoveFromRoleAsync then AddToRoleAsync
                    if current_links:
                        for link in current_links:
                             if link.RoleId != role_obj.Id:
                                 await db.delete(link)

                    # Add new if not exists
                    exists_stmt = select(AspNetUserRoles).where(
                        and_(AspNetUserRoles.UserId == identity_user.Id, AspNetUserRoles.RoleId == role_obj.Id)
                    )
                    if not (await db.execute(exists_stmt)).scalars().first():
                         db.add(AspNetUserRoles(UserId=identity_user.Id, RoleId=role_obj.Id))

            await db.commit()
            await db.refresh(existing_user)

            return ResponseModel(
                Data=existing_user.Id,
                Message="User updated successfully",
                Status=True,
                StatusCode=200
            )

        # 3. CREATE SCENARIO
        else:
            new_user = UserModel(
                UserName=command.UserName,
                Email=command.EmailID,
                PhoneNumber=command.MobileNo,
                FirstName=command.FirstName,
                LastName=command.LastName,
                MiddleName=command.MiddleName,
                Role=command.RoleName or command.Role,
                Department=command.Department,
                Remarks=command.Remark,
                BranchId=command.BranchId,
                OrgId=1, # Default
                IsActive=True,
                
                # Audit
                CreatedBy=actor_id,
                CreatedDate=datetime.utcnow(),
                CreatedIP=client_ip,
                LastModifiedBy=actor_id,
                LastModifiedDate=datetime.utcnow(),
                LastModifiedIP=client_ip,
                
                
            # Password
                Password=command.Password # Store exactly what is passed (e.g. "" or "secret")
            )

            if command.FromDate:
                new_user.FromDate = command.FromDate.date()
            if command.ToDate:
                new_user.ToDate = command.ToDate.date()

            db.add(new_user)
            await db.flush() # Get ID for linkage

            # =========================================================
            # SYNC ASPNETUSERS (Create)
            # =========================================================
            
            # Check if username exists in AspNetUsers to avoid conflict
            stmt_chk = select(AspNetUsers).where(AspNetUsers.UserName == command.UserName)
            if (await db.execute(stmt_chk)).scalars().first():
                 # Handle Edge Case: User exists in Identity but not in 'users'. 
                 # For now, we proceed to try to link or error? .NET creates new.
                 pass 

            new_identity_id = str(uuid.uuid4())
            identity_user = AspNetUsers(
                Id=new_identity_id,
                Email=command.EmailID,
                NormalizedEmail=command.EmailID.upper() if command.EmailID else None,
                PhoneNumber=command.MobileNo,
                UserName=command.UserName,
                NormalizedUserName=command.UserName.upper(),
                SecurityStamp=str(uuid.uuid4()),
                ConcurrencyStamp=str(uuid.uuid4()), # Standard Identity field
                RefreshToken="", # Initialize to empty
                RefreshTokenExpiryTime=datetime.utcnow(), # Initialize to now (not null)
                EmailConfirmed=False,
                PhoneNumberConfirmed=False,
                TwoFactorEnabled=False,
                LockoutEnabled=True,
                AccessFailedCount=0,
                CreatedDate=datetime.utcnow(),
                IsActive=True,
                userid=new_user.Id, # CRITICAL LINK
                CreatedBy=actor_id,
                OrgId=1, # Default as per users table
                LastModifiedBy=actor_id,
                LastModifiedDate=datetime.utcnow()
            )

            if command.Password is not None:
                 identity_user.PasswordHash = hash_aspnet_password(command.Password)
            
            db.add(identity_user)
            
            # Role
            role_name = command.RoleName or command.Role
            if role_name:
                stmt_role = select(AspNetRoles).where(AspNetRoles.Name == role_name)
                role_obj = (await db.execute(stmt_role)).scalars().first()
                if not role_obj:
                     role_obj = AspNetRoles(Id=str(uuid.uuid4()), Name=role_name, NormalizedName=role_name.upper())
                     db.add(role_obj)
                     await db.flush()
                
                db.add(AspNetUserRoles(UserId=identity_user.Id, RoleId=role_obj.Id))

            await db.commit()
            await db.refresh(new_user)

            return ResponseModel(
                Data=new_user.Id,
                Message="User created successfully",
                Status=True,
                StatusCode=200
            )

    except Exception as e:
        print(f"Error in create_user: {str(e)}")
        await db.rollback()
        return ResponseModel(
            Message=f"Error: {str(e)}",
            Status=False,
            StatusCode=500
        )


@router.post("/update-password", response_model=ResponseModel)
async def update_password(
    command: UpdatePasswordUserCommand,
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: UserModel = Depends(auth.get_current_user)
):
    try:
        if not command.Id or command.Id <= 0:
             return ResponseModel(
                Message="Invalid User ID",
                Status=False,
                StatusCode=400
            )

        result = await db.execute(select(UserModel).where(UserModel.Id == command.Id))
        existing_user = result.scalars().first()

        if not existing_user:
            return ResponseModel(
                Message="User not found",
                Status=False,
                StatusCode=404
            )

        # Update Password
        existing_user.Password = command.Password
        
        # Audit
        existing_user.LastModifiedBy = current_user.Id
        existing_user.LastModifiedDate = datetime.utcnow()
        existing_user.LastModifiedIP = request.client.host if request.client else "127.0.0.1"

        # SYNC ASPNETUSERS
        stmt_ident = select(AspNetUsers).where(AspNetUsers.userid == existing_user.Id)
        identity_user = (await db.execute(stmt_ident)).scalars().first()
        if identity_user:
             identity_user.PasswordHash = hash_aspnet_password(command.Password)
             identity_user.SecurityStamp = str(uuid.uuid4())

        await db.commit()

        return ResponseModel(
            Data=existing_user.Id,
            Message="Password updated successfully",
            Status=True,
            StatusCode=200
        )

    except Exception as e:
        print(f"Error in update_password: {str(e)}")
        await db.rollback()
        return ResponseModel(
            Message=f"Error: {str(e)}",
            Status=False,
            StatusCode=500
        )


@router.get("/getlist", response_model=ResponseModel)
async def get_all_users(
    ProdId: int = Query(...),
    FromDate: str = Query(...),
    ToDate: str = Query(...),
    BranchId: int = Query(...),
    UserName: Optional[str] = Query(None),
    db: AsyncSession = Depends(database.get_db),
    current_user: UserModel = Depends(auth.get_current_user)
):
    try:
        # Build Query
        stmt = select(UserModel)
        
        # Apply Filters (Basic implementation)
        if BranchId > 0:
            stmt = stmt.where(UserModel.BranchId == BranchId)
        
        if UserName:
            # Case insensitive search
            stmt = stmt.where(UserModel.UserName.ilike(f"%{UserName}%"))

        # Add Date filters if format matches YYYY-MM-DD
        # if FromDate and ToDate:
        #    stmt = stmt.where(UserModel.CreatedDate.between(FromDate, ToDate))

        result = await db.execute(stmt)
        users = result.scalars().all()
        
        # Verify if .NET returns a wrapper or list directly. 
        # The controller says `return Ok(result)` where result is from mediator.
        # usually mediator returns a list or a list wrapped in data.
        # The Python ResponseModel expects Data to be Any.
        
        return ResponseModel(
            Data=[UserDto.model_validate(u) for u in users],
            Message="Success",
            Status=True,
            StatusCode=200
        )

    except Exception as e:
        print(f"Error in get_all_users: {str(e)}")
        return ResponseModel(
            Message=f"Error: {str(e)}",
            Status=False,
            StatusCode=500
        )


@router.get("/getbyId", response_model=ResponseModel)
async def get_user_by_id(
    userID: int = Query(...),
    branchId: int = Query(...),
    db: AsyncSession = Depends(database.get_db),
    current_user: UserModel = Depends(auth.get_current_user)
):
    try:
        result = await db.execute(select(UserModel).where(UserModel.Id == userID))
        user = result.scalars().first()

        if not user:
             return ResponseModel(
                Message="User not found",
                Status=False,
                StatusCode=404
            )

        return ResponseModel(
            Data=UserDto.model_validate(user),
            Message="Success",
            Status=True,
            StatusCode=200
        )

    except Exception as e:
        print(f"Error in get_user_by_id: {str(e)}")
        return ResponseModel(
            Message=f"Error: {str(e)}",
            Status=False,
            StatusCode=500
        )


@router.post("/update-status", response_model=ResponseModel)
async def update_status(
    command: UserStatusQuery,
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: UserModel = Depends(auth.get_current_user)
):
    try:
        print(f"UpdateStatus: UserID={command.UserId}, NewStatus={command.IsActive}")
        
        # 1. Check if user exists
        result = await db.execute(select(UserModel).where(UserModel.Id == command.UserId))
        user = result.scalars().first()

        if not user:
             return ResponseModel(
                Message="User not found",
                Status=False,
                StatusCode=404
            )

        # 2. Update 'users' table using explicit UPDATE statement
        stmt_update_user = (
            update(UserModel)
            .where(UserModel.Id == command.UserId)
            .values(
                IsActive=command.IsActive,
                LastModifiedBy=current_user.Id,
                LastModifiedDate=datetime.utcnow(),
                LastModifiedIP=request.client.host if request.client else "127.0.0.1"
            )
        )
        await db.execute(stmt_update_user)

        # 3. Update 'AspNetUsers' table
        # Try by userid OR UserName (Fallback)
        target_username = user.UserName
        
        stmt_update_identity = (
            update(AspNetUsers)
            .where(
                or_(
                    AspNetUsers.userid == command.UserId,
                    and_(AspNetUsers.userid == None, AspNetUsers.UserName == target_username)
                )
            )
            .values(IsActive=command.IsActive)
        )
        
        result_ident = await db.execute(stmt_update_identity)
        print(f"UpdateStatus: AspNetUsers rows affected: {result_ident.rowcount}")

        await db.commit()
        print("UpdateStatus: Commit successful")

        return ResponseModel(
            Data=command.UserId,
            Message="User status updated successfully",
            Status=True,
            StatusCode=200
        )
        
    except Exception as e:
        print(f"Error in update_status: {str(e)}")
        await db.rollback()
        return ResponseModel(
            Message=f"Error: {str(e)}",
            Status=False,
            StatusCode=500
        )
