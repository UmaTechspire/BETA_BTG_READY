from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import text
from ..database import engine 
import os
from dotenv import load_dotenv

load_dotenv()

DB_NAME_USER = os.getenv('DB_NAME_USER', 'btggasify_live')

router = APIRouter()

# --- Models ---
class GasCodeRequest(BaseModel):
    Id: Optional[int] = 0
    GasCode: str
    GasName: str
    Volume: str
    Pressure: str
    VolumeId: Optional[int] = 0
    PressureId: Optional[int] = 0
    GasTypeId: int
    test: Optional[int] = 0
    OrgId: int = 1
    BranchId: int = 1
    Descriptions: Optional[str] = ""
    IsActive: bool = True
    UserId: Optional[int] = 1 # Added for CreatedBy/LastModifiedBy
    UserIp: Optional[str] = ""

class ToggleStatusRequest(BaseModel):
    id: int
    isActive: bool

# --- Endpoints ---

@router.get("/GetAllGasListing")
async def get_all_gas_listing(gasName: str = "", volume: str = "", pressure: str = ""):
    try:
        async with engine.connect() as conn:
            # Construct query dynamically based on logic in C# proc
            # C# proc likely filters by LIKE %...% if param is not empty
            
            sql = "CALL proc_GasMaster_GetAll(:gasName, :volume, :pressure)"
            
            params = {
                "gasName": gasName,
                "volume": volume,
                "pressure": pressure
            }
            
            result = await conn.execute(text(sql), params)
            rows = result.fetchall()
            
            # Reformat to match what Frontend expects (if C# returns a specific structure)
            # Frontend seems to expect a list of objects.
            return {"status": True, "data": [dict(row._mapping) for row in rows]}

    except Exception as e:
        print(f"Error fetching gas listing: {e}")
        return {"status": False, "message": str(e), "data": []}

@router.get("/GetByID")
async def get_by_id(gasID: int):
    try:
        async with engine.connect() as conn:
            sql = text("CALL proc_GasMaster_GetById(:id)")
            result = await conn.execute(sql, {"id": gasID})
            row = result.fetchone()
            
            if row:
                return {"status": True, "data": [dict(row._mapping)], "message": "Success"}
            else:
                return {"status": False, "message": "Gas code not found", "data": []}
    except Exception as e:
         return {"status": False, "message": str(e), "data": []}

@router.post("/Create")
async def create_gas(payload: GasCodeRequest):
    try:
        async with engine.begin() as conn:
            sql = text("CALL proc_GasMaster_Create(:code, :name, :vol, :press, :user, :ip, :active, :org, :branch, :desc, :type, :volid, :pressid)")
            
            await conn.execute(sql, {
                "code": payload.GasCode,
                "name": payload.GasName,
                "vol": payload.Volume,
                "press": payload.Pressure,
                "user": payload.UserId,
                "ip": payload.UserIp,
                "active": 1 if payload.IsActive else 0,
                "org": payload.OrgId,
                "branch": payload.BranchId,
                "desc": payload.Descriptions,
                "type": payload.GasTypeId,
                "volid": payload.VolumeId,
                "pressid": payload.PressureId
            })
            
            return {"status": True, "message": "Saved Successfully"}
            
    except Exception as e:
        print(f"Error creating gas: {e}")
        return {"status": False, "message": f"Saving MasterGas failed: {str(e)}"}

@router.put("/Update")
async def update_gas(payload: GasCodeRequest):
    try:
        async with engine.begin() as conn:
             sql = text("CALL proc_GasMaster_Update(:id, :code, :name, :vol, :press, :user, :ip, :active, :org, :branch, :desc, :type, :volid, :pressid)")
             
             result = await conn.execute(sql, {
                "code": payload.GasCode,
                "name": payload.GasName,
                "vol": payload.Volume,
                "press": payload.Pressure,
                "user": payload.UserId,
                "ip": payload.UserIp,
                "active": 1 if payload.IsActive else 0,
                "org": payload.OrgId,
                "branch": payload.BranchId,
                "desc": payload.Descriptions,
                "type": payload.GasTypeId,
                "volid": payload.VolumeId,
                "pressid": payload.PressureId,
                "id": payload.Id
            })
             
             if result.rowcount == 0:
                 return {"status": False, "message": "Update failed: Record not found"}
                 
             return {"status": True, "message": "Updated Successfully"}

    except Exception as e:
        return {"status": False, "message": f"Update failed: {str(e)}"}

@router.put("/ToogleActiveStatus")
async def toggle_active_status(payload: ToggleStatusRequest):
    print(f"Toggle Request: {payload}")
    try:
        async with engine.begin() as conn:
            sql = text("CALL proc_GasMaster_ToggleStatus(:id, :active)")
            
            # Convert bool to int for BIT(1) column
            active_val = 1 if payload.isActive else 0
            
            result = await conn.execute(sql, {"active": active_val, "id": payload.id})
            print(f"Toggle Result: rows={result.rowcount}")
            
            if result.rowcount == 0:
                 return {"status": False, "message": "Toggle failed: Record not found"}
            
            return {"status": True, "message": "Toogle status MasterGas success"}
            
    except Exception as e:
        print(f"Toggle Error: {e}")
        return {"status": False, "message": f"Toggle failed: {str(e)}"}

@router.get("/GetAllGasTypes")
async def get_all_gas_types():
    try:
        async with engine.connect() as conn:
            sql = text("CALL proc_GasMaster_GetAllTypes()")
            result = await conn.execute(sql)
            rows = result.fetchall()
            return {"status": True, "data": [dict(row._mapping) for row in rows]}
    except Exception as e:
        return {"status": False, "message": str(e), "data": []}