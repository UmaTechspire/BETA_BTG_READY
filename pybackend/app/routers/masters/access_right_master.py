from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.future import select
from sqlalchemy import insert, update, delete, and_, or_
from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel

from ... import database, auth
from ...models.access_rights_header import MasterAccessRightsHeader
from ...models.access_rights_details import MasterAccessRightsDetails
from ...models.user import User
from ...models.roles import AspNetRoles
from ...models.users_refresh import AspNetUsers

# We'll define a minimal Department model here if not exists, for dropdowns
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String

Base = declarative_base()
# Assuming master_department exists in DB_NAME_MASTER
class MasterDepartment(Base):
    __tablename__ = "master_department"
    __table_args__ = {"schema": database.DB_NAME_USER}
    DepartmentId = Column(Integer, primary_key=True)
    DepartmentName = Column(String(100))

router = APIRouter(
    prefix="/api/AccessRights",
    tags=["AccessRights"]
)


# =========================================================
# SCHEMAS (Refined to match .NET DTOs)
# =========================================================

class PermissionsDto(BaseModel):
    View: bool = False
    Edit: bool = False
    Delete: bool = False
    Post: bool = False
    Save: bool = False
    Print: bool = False
    ViewRate: bool = False
    SendMail: bool = False
    ViewDetails: bool = False
    RecordsPerPage: int = 0

class ScreenPermissionsDto(BaseModel):
    ModuleId: int
    ScreenId: int
    ScreenName: str
    Permissions: PermissionsDto

class ModuleScreensDto(BaseModel):
    ModuleName: str
    Screens: List[ScreenPermissionsDto]

class AccessRightsSaveRequestDto(BaseModel):
    HeaderId: int = 0
    DepartmentId: int
    Role: str
    Department: str
    EffectiveDate: Optional[datetime] = None
    IsHOD: bool = False
    IsActive: Optional[bool] = None
    RoleId: Optional[str] = None
    Modules: List[ModuleScreensDto] = []

class SaveAccessRightsCommand(BaseModel):
    Header: AccessRightsSaveRequestDto

class UpdateAccessRightsRequest(BaseModel):
    HeaderId: int # Included in URL but .NET command has Request object
    # The .NET UpdateAccessRightsCommand only has 'Request' property of type AccessRightsSaveRequest
    # But the Controller method signature is UpdateAccessRights(int headerId, [FromBody] UpdateAccessRightsCommand command)
    # And then it sets command.Request.HeaderId = headerId

class UpdateAccessRightsCommand(BaseModel):
    Request: AccessRightsSaveRequestDto

# =========================================================
# API ENDPOINTS
# =========================================================

@router.get("/GetRolesDropdown")
async def get_roles_dropdown(
    branchId: int, 
    orgId: int, 
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        stmt = select(AspNetRoles).where(AspNetRoles.Name != 'SuperAdmin')
        result = await db.execute(stmt)
        roles = result.scalars().all()
        
        data = [{"Id": r.Id, "Name": r.Name} for r in roles]
        return ResponseModel(Data=data, Message="Success", Status=True, StatusCode=200)
    except Exception as e:
        return ResponseModel(Message=f"Error: {str(e)}", Status=False, StatusCode=500)

@router.get("/GetDepartmentsDropdown")
async def get_departments_dropdown(
    branchId: int,
    orgId: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        stmt = select(MasterDepartment)
        result = await db.execute(stmt)
        depts = result.scalars().all()
        
        data = [{"Id": d.DepartmentId, "Name": d.DepartmentName} for d in depts]
        return ResponseModel(Data=data, Message="Success", Status=True, StatusCode=200)
    except Exception as e:
        return ResponseModel(Message=f"Error: {str(e)}", Status=False, StatusCode=500)

@router.post("/SaveAccessRights")
async def save_access_rights(
    command: SaveAccessRightsCommand,
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        req = command.Header
        if not req or not req.Role:
             return ResponseModel(Message="Invalid request", Status=False, StatusCode=400)
        
        # Check Existence
        sql_exist = text(f"""
            SELECT count(*) FROM {database.DB_NAME_MASTER}.master_accessrights_header 
            WHERE RoleId = :RoleId AND DepartmentId = :DepartmentId AND IsActive = 1 AND ifnull(Hod,0) = :Hod
        """)
        exist_res = await db.execute(sql_exist, {"RoleId": req.RoleId, "DepartmentId": req.DepartmentId, "Hod": req.IsHOD})
        count = exist_res.scalars().first()
        
        if count == 0:
            # INSERT HEADER
            sql_insert_header = text(f"""
                INSERT INTO {database.DB_NAME_MASTER}.master_accessrights_header
                (Role, Department, DepartmentId, Hod, BranchId, OrgId, IsActive, CreatedBy, CreatedDate, CreatedIP, EffectiveFrom, RoleId)
                VALUES
                (:Role, :Department, :DepartmentId, :Hod, :BranchId, :OrgId, :IsActive, :CreatedBy, :CreatedDate, :CreatedIP, :EffectiveFrom, :RoleId)
            """)
            
            created_date = datetime.utcnow()
            client_ip = request.client.host if request.client else "127.0.0.1"
            
            await db.execute(sql_insert_header, {
                "Role": req.Role,
                "Department": req.Department,
                "DepartmentId": req.DepartmentId,
                "Hod": req.IsHOD,
                "BranchId": 1,
                "OrgId": 1,
                "IsActive": 1,
                "CreatedBy": current_user.Id,
                "CreatedDate": created_date,
                "CreatedIP": client_ip,
                "EffectiveFrom": req.EffectiveDate if req.EffectiveDate else created_date,
                "RoleId": req.RoleId
            })
            
            # Get ID
            id_res = await db.execute(text("SELECT LAST_INSERT_ID()"))
            header_id = id_res.scalars().first()
            
            # INSERT DETAILS
            sql_insert_detail = text(f"""
                INSERT INTO {database.DB_NAME_MASTER}.master_accessrights_details
                (HeaderId, ModuleId, Module, ScreenId, Screen, `View`, `Edit`, `Delete`, `Post`, `Save`, `Print`, ViewRate, SendMail, ViewDetails, Records, IsActive)
                VALUES
                (:HeaderId, :ModuleId, :Module, :ScreenId, :Screen, :View, :Edit, :Delete, :Post, :Save, :Print, :ViewRate, :SendMail, :ViewDetails, :Records, :IsActive)
            """)
            
            for module in req.Modules:
                for screen in module.Screens:
                    p = screen.Permissions
                    await db.execute(sql_insert_detail, {
                        "HeaderId": header_id,
                        "ModuleId": screen.ModuleId,
                        "Module": module.ModuleName,
                        "ScreenId": screen.ScreenId,
                        "Screen": screen.ScreenName,
                        "View": p.View,
                        "Edit": p.Edit,
                        "Delete": p.Delete,
                        "Post": p.Post,
                        "Save": p.Save,
                        "Print": p.Print,
                        "ViewRate": p.ViewRate,
                        "SendMail": p.SendMail,
                        "ViewDetails": p.ViewDetails,
                        "Records": p.RecordsPerPage,
                        "IsActive": True
                    })
            
            await db.commit()
            
            # Construct Specific Response Body matching .NET camelCase
            return {
                "header": {
                    "headerId": header_id,
                    "departmentId": req.DepartmentId,
                    "role": req.Role,
                    "department": req.Department,
                    "effectiveDate": req.EffectiveDate,
                    "isHOD": req.IsHOD,
                    "isActive": True, # Created is always true initially
                    "roleId": req.RoleId,
                    "modules": [
                        {
                            "moduleName": m.ModuleName,
                            "screens": [
                                {
                                    "moduleId": s.ModuleId,
                                    "screenId": s.ScreenId,
                                    "screenName": s.ScreenName,
                                    "permissions": {
                                        "view": s.Permissions.View,
                                        "edit": s.Permissions.Edit,
                                        "delete": s.Permissions.Delete,
                                        "post": s.Permissions.Post,
                                        "save": s.Permissions.Save,
                                        "print": s.Permissions.Print,
                                        "viewRate": s.Permissions.ViewRate,
                                        "sendMail": s.Permissions.SendMail,
                                        "viewDetails": s.Permissions.ViewDetails,
                                        "recordsPerPage": s.Permissions.RecordsPerPage
                                    }
                                } for s in m.Screens
                            ]
                        } for m in req.Modules
                    ]
                }
            }
            
        else:
             return {
                "Status": False,
                "Message": "Already used this Role And Department",
                "Data": None
            }

    except Exception as e:
        await db.rollback()
        return ResponseModel(Message=f"Error saving access rights: {str(e)}", Status=False, StatusCode=500)

@router.put("/UpdateAccessRights/{headerId}")
async def update_access_rights(
    headerId: int,
    command: UpdateAccessRightsCommand,
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        req = command.Request
        if not req or not req.Role:
             return { "Status": False, "Message": "Invalid request for update", "Data": None }
        
        req.HeaderId = headerId # Ensure sync
        
        if headerId <= 0:
             return { "Status": False, "Message": "Invalid HeaderId for update", "Data": None }
             
        # Check Existence (Update check logic)
        sql_exist = text(f"""
            SELECT count(*) FROM {database.DB_NAME_MASTER}.master_accessrights_header 
            WHERE RoleId = :RoleId AND DepartmentId = :DepartmentId AND IsActive = 1 AND ifnull(Hod,0) = :Hod AND Id != :Id
        """)
        exist_res = await db.execute(sql_exist, {
            "RoleId": req.RoleId, 
            "DepartmentId": req.DepartmentId, 
            "Hod": req.IsHOD,
            "Id": headerId
        })
        count = exist_res.scalars().first()
        
        if count == 0:
            # Update Header
            # Get current IsActive
            curr_active_res = await db.execute(text(f"SELECT IsActive FROM {database.DB_NAME_MASTER}.master_accessrights_header WHERE Id = :Id"), {"Id": headerId})
            db_is_active = curr_active_res.scalars().first()
            
            final_active = 1 if req.IsActive is True else 0 # Simplification of .NET logic
            if req.IsActive is None:
                final_active = db_is_active
            
            updated_date = datetime.utcnow()
            client_ip = request.client.host if request.client else "127.0.0.1"

            sql_update_header = text(f"""
                UPDATE {database.DB_NAME_MASTER}.master_accessrights_header
                SET 
                    Role = :Role,
                    Department = :Department,
                    Hod = :Hod,
                    BranchId = :BranchId,
                    OrgId = :OrgId,
                    ModifiedBy = :ModifiedBy,
                    LastModifiedDate = :LastModifiedDate,
                    ModifiedIP = :ModifiedIP,
                    EffectiveFrom = :EffectiveFrom,
                    IsActive = :IsActive
                WHERE Id = :Id
            """)
            
            await db.execute(sql_update_header, {
                "Role": req.Role,
                "Department": req.Department,
                "Hod": req.IsHOD,
                "BranchId": 1,
                "OrgId": 1,
                "ModifiedBy": current_user.Id,
                "LastModifiedDate": updated_date,
                "ModifiedIP": client_ip,
                "EffectiveFrom": req.EffectiveDate if req.EffectiveDate else updated_date,
                "IsActive": final_active,
                "Id": headerId
            })
            
            # Logic Loop for Details
            sql_check_detail = text(f"SELECT COUNT(*) FROM {database.DB_NAME_MASTER}.master_accessrights_details WHERE HeaderId=:HeaderId AND Module=:Module AND Screen=:Screen")
            sql_del_detail = text(f"DELETE FROM {database.DB_NAME_MASTER}.master_accessrights_details WHERE HeaderId=:HeaderId AND Module=:Module AND Screen=:Screen")
            sql_update_detail = text(f"""
                UPDATE {database.DB_NAME_MASTER}.master_accessrights_details
                SET `View`=:View, `Edit`=:Edit, `Delete`=:Delete, `Post`=:Post, `Save`=:Save, `Print`=:Print,
                    ViewRate=:ViewRate, SendMail=:SendMail, ViewDetails=:ViewDetails, Records=:Records, IsActive=1
                WHERE HeaderId=:HeaderId AND Module=:Module AND Screen=:Screen
            """)
            sql_insert_detail = text(f"""
                INSERT INTO {database.DB_NAME_MASTER}.master_accessrights_details
                (HeaderId, ModuleId, Module, ScreenId, Screen, `View`, `Edit`, `Delete`, `Post`, `Save`, `Print`, ViewRate, SendMail, ViewDetails, Records, IsActive)
                VALUES
                (:HeaderId, :ModuleId, :Module, :ScreenId, :Screen, :View, :Edit, :Delete, :Post, :Save, :Print, :ViewRate, :SendMail, :ViewDetails, :Records, :IsActive)
            """)

            for module in req.Modules:
                for screen in module.Screens:
                    p = screen.Permissions
                    
                    # Check exists
                    d_count_res = await db.execute(sql_check_detail, {
                        "HeaderId": headerId, "Module": module.ModuleName, "Screen": screen.ScreenName
                    })
                    total_d = d_count_res.scalars().first()
                    
                    # All False Check
                    all_false = not (p.View or p.Edit or p.Delete or p.Post or p.Save or p.Print or p.ViewRate or p.SendMail or p.ViewDetails)
                    
                    if all_false:
                        if total_d > 0:
                            await db.execute(sql_del_detail, {
                                "HeaderId": headerId, "Module": module.ModuleName, "Screen": screen.ScreenName
                            })
                        continue
                    
                    # Upsert
                    params_d = {
                        "HeaderId": headerId,
                        "ModuleId": screen.ModuleId,
                        "Module": module.ModuleName,
                        "ScreenId": screen.ScreenId,
                        "Screen": screen.ScreenName,
                        "View": p.View,
                        "Edit": p.Edit,
                        "Delete": p.Delete,
                        "Post": p.Post,
                        "Save": p.Save,
                        "Print": p.Print,
                        "ViewRate": p.ViewRate,
                        "SendMail": p.SendMail,
                        "ViewDetails": p.ViewDetails,
                        "Records": p.RecordsPerPage,
                        "IsActive": True
                    }
                    
                    if total_d > 0:
                        await db.execute(sql_update_detail, params_d)
                    else:
                        await db.execute(sql_insert_detail, params_d)
                        
            await db.commit()
            
            # Construct Specific Response Body matching .NET camelCase
            return {
                "header": {
                    "headerId": headerId,
                    "departmentId": req.DepartmentId,
                    "role": req.Role,
                    "department": req.Department,
                    "effectiveDate": req.EffectiveDate,
                    "isHOD": req.IsHOD,
                    "isActive": bool(final_active),
                    "roleId": req.RoleId,
                    "modules": [
                        {
                            "moduleName": m.ModuleName,
                            "screens": [
                                {
                                    "moduleId": s.ModuleId,
                                    "screenId": s.ScreenId,
                                    "screenName": s.ScreenName,
                                    "permissions": {
                                        "view": s.Permissions.View,
                                        "edit": s.Permissions.Edit,
                                        "delete": s.Permissions.Delete,
                                        "post": s.Permissions.Post,
                                        "save": s.Permissions.Save,
                                        "print": s.Permissions.Print,
                                        "viewRate": s.Permissions.ViewRate,
                                        "sendMail": s.Permissions.SendMail,
                                        "viewDetails": s.Permissions.ViewDetails,
                                        "recordsPerPage": s.Permissions.RecordsPerPage
                                    }
                                } for s in m.Screens
                            ]
                        } for m in req.Modules
                    ]
                }
            }
            
        else:
             return {
                "Status": False,
                "Message": "Already used this Role And Department",
                "Data": None
            }

    except Exception as e:
        await db.rollback()
        return ResponseModel(Message=f"Error updating access rights: {str(e)}", Status=False, StatusCode=500)

# =========================================================
# HELPER FOR SP EXECUTION
# =========================================================
async def execute_sp(db: AsyncSession, sp_name: str, params: dict):
    # MySQL syntax: CALL sp_name(:param1, :param2, ...)
    keys = list(params.keys())
    args_str = ", ".join([f":{k}" for k in keys])
    stmt = text(f"CALL {sp_name}({args_str})")
    
    result = await db.execute(stmt, params)
    # Stored procedures can return multiple result sets.
    # We'll fetch all rows from the first set.
    rows = result.mappings().all() 
    return [dict(row) for row in rows]

# =========================================================
# COMPLETED GET ENDPOINTS
# =========================================================

@router.get("/GetMenusDetails")
async def get_menus_details(
    userid: int,
    branchId: int,
    orgid: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        # Access raw aiomysql/asyncmy connection to handle multiple result sets (Modules, Screens, HomePage)
        connection = await db.connection()
        raw_conn = await connection.get_raw_connection()
        driver_conn = raw_conn.driver_connection
        
        # Ensure we have a cursor that supports nextset
        cursor = await driver_conn.cursor()
        
        try:
            # CALL SP
            await cursor.execute(f"CALL {database.DB_NAME_MASTER}.proc_AccessRights(1, {userid}, {branchId}, {orgid}, 0, 0)")
            
            # --- Result Set 1: Modules ---
            columns_m = [desc[0] for desc in cursor.description] if cursor.description else []
            rows_m = await cursor.fetchall()
            modules_list = [dict(zip(columns_m, row)) for row in rows_m]
            
            # --- Result Set 2: Screens ---
            await cursor.nextset()
            columns_s = [desc[0] for desc in cursor.description] if cursor.description else []
            rows_s = await cursor.fetchall()
            screens_list = [dict(zip(columns_s, row)) for row in rows_s]
            
            # --- Result Set 3: HomePage ---
            await cursor.nextset()
            home_page = ""
            row_h = await cursor.fetchone()
            if row_h:
                home_page = row_h[0]
                
        finally:
            await cursor.close()

        # --- Process Data (Replicating C# Hierarchy Logic) ---
        
        # Helper to get value case-insensitively
        def get_val(d, key, default=None):
            for k in d.keys():
                if k.lower() == key.lower():
                    return d[k]
            return default

        # 1. Initialize Containers
        module_lookup = {}
        for m in modules_list:
            m_id = get_val(m, 'ModuleId')
            if m_id is not None:
                module_lookup[m_id] = m
            # Initialize children lists matching .NET structure
            m['Screen'] = [] 
            # Submodules (C# adds them to Screen.Module, but let's prep)
            
        # 2. Attach Screens to Modules
        for s in screens_list:
            s['Module'] = [] # Screens can hold sub-modules
            m_id = get_val(s, 'ModuleId')
            if m_id in module_lookup:
                module_lookup[m_id]['Screen'].append(s)

        # 3. Sort Screens
        for m in modules_list:
            m['Screen'].sort(key=lambda x: get_val(x, 'MenuOrder', 0))

        # 4. Attach Sub-Modules to Parent's Screens
        for m in modules_list:
            p_id = get_val(m, 'ParentModuleId')
            if p_id and p_id in module_lookup:
                parent = module_lookup[p_id]
                sorted_screens = parent['Screen']
                
                # Logic: Find nearest screen with MenuOrder <= Module.MenuOrder
                if sorted_screens:
                    m_order = get_val(m, 'MenuOrder', 0)
                    attach_screen = sorted_screens[0] # Fallback
                    
                    # Find last screen where Screen.MenuOrder <= Module.MenuOrder
                    candidates = [s for s in sorted_screens if get_val(s, 'MenuOrder', 0) <= m_order]
                    if candidates:
                        attach_screen = candidates[-1]
                    
                    attach_screen['Module'].append(m)

        # 5. Sort Sub-Modules
        for m in modules_list:
            for s in m['Screen']:
                s['Module'].sort(key=lambda x: get_val(x, 'MenuOrder', 0))

        # 6. Filter Top Level Modules (No Parent)
        top_level = [m for m in modules_list if not get_val(m, 'ParentModuleId') and m['Screen']]
        top_level.sort(key=lambda x: get_val(x, 'MenuOrder', 0))

        response_data = {
            "Menus": top_level,
            "HomePage": home_page
        }

        return ResponseModel(Data=response_data, Message="Success", Status=True, StatusCode=200)

    except Exception as e:
        return ResponseModel(Message=f"Error: {str(e)}", Status=False, StatusCode=500)

@router.get("/GetApprovalSettings")
async def get_approval_settings(
    userid: int,
    branchId: int,
    orgid: int,
    screenid: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        # Calls proc_AccessRights @opt=2
        params = {
            "opt": 2,
            "userid": userid,
            "branchid": branchId,
            "orgid": orgid,
            "ScreenId": screenid,
            "HeaderId": 0
        }
        rows = await execute_sp(db, f"{database.DB_NAME_MASTER}.proc_AccessRights", params)
        return ResponseModel(Data=rows, Message="Success", Status=True, StatusCode=200)

    except Exception as e:
        return ResponseModel(Message=f"Error: {str(e)}", Status=False, StatusCode=500)

@router.get("/GetModuleScreens")
async def get_module_screens(
    branchId: int,
    orgId: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        # Calls proc_RolesAccess @opt=5
        params = {
            "opt": 5,
            "userid": 0,
            "branchid": branchId,
            "orgid": orgId,
            "ScreenId": 0,
            "HeaderId": 0
        }
        rows = await execute_sp(db, f"{database.DB_NAME_MASTER}.proc_RolesAccess", params)
        return ResponseModel(Data=rows, Message="Success", Status=True, StatusCode=200)

    except Exception as e:
        return ResponseModel(Message=f"Error: {str(e)}", Status=False, StatusCode=500)

# REPLACING ORM GetAllAccessRights with SP Logic (opt=6)
@router.get("/GetAllAccessRights")
async def get_all_access_rights(
    branchId: int, 
    orgId: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: User = Depends(auth.get_current_user)
):
    try:
        # Calls proc_RolesAccess @opt=6
        params = {
            "opt": 6,
            "userid": 0,
            "branchid": branchId,
            "orgid": orgId,
            "ScreenId": 0,
            "HeaderId": 0
        }
        
        flat_rows = await execute_sp(db, f"{database.DB_NAME_MASTER}.proc_RolesAccess", params)
        
        # Logic to Group: Header -> Modules -> Screens
        # Replicating .NET "GetAccessRightsByBranchOrg" grouping logic
        
        grouped_data = {}
        
        for row in flat_rows:
            h_id = row.get("HeaderId")
            if not h_id: continue
            
            if h_id not in grouped_data:
                grouped_data[h_id] = {
                    "headerId": h_id,
                    "role": row.get("Role"),
                    "department": row.get("Department"),
                    "effectiveDate": row.get("EffectiveFrom"), # DateTime object typically
                    "isHOD": bool(row.get("Hod")),
                    "isActive": bool(row.get("IsActive")),
                    "modules": {} # Temp dict for modules
                }
            
            # Module
            m_id = row.get("ModuleId")
            m_name = row.get("Module")
            
            if m_id is not None:
                if m_id not in grouped_data[h_id]["modules"]:
                    grouped_data[h_id]["modules"][m_id] = {
                        "moduleName": m_name,
                        "moduleId": m_id,
                        "screens": []
                    }
                
                # Screen
                s_id = row.get("ScreenId")
                if s_id is not None:
                    screen_obj = {
                        "screenName": row.get("Screen"),
                        "screenId": s_id,
                        "permissions": [{
                            "view": bool(row.get("View")),
                            "edit": bool(row.get("Edit")),
                            "delete": bool(row.get("Delete")),
                            "post": bool(row.get("Post")),
                            "save": bool(row.get("Save")),
                            "print": bool(row.get("Print")),
                            "viewRate": bool(row.get("ViewRate")),
                            "sendMail": bool(row.get("SendMail")),
                            "viewDetails": bool(row.get("ViewDetails")),
                            "records": row.get("Records")
                        }]
                    }
                    grouped_data[h_id]["modules"][m_id]["screens"].append(screen_obj)

        # Final Formatting
        final_list = []
        for h_val in grouped_data.values():
            h_val["modules"] = list(h_val["modules"].values())
            final_list.append(h_val)

        return ResponseModel(Data=final_list, Message="Success", Status=True, StatusCode=200)

    except Exception as e:
        return ResponseModel(Message=f"Error: {str(e)}", Status=False, StatusCode=500)
