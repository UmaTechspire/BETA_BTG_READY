from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Any
import mysql.connector
import os
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(
    prefix="/api/procurement_memo",
    tags=["Procurement Memo"]
)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME_PURCHASE'),
        port=int(os.getenv('DB_PORT', 3306)),
        ssl_disabled=True
    )

# --- Pydantic Models (Matching C# DTOs inferred from Repository) ---

class MemoHeader(BaseModel):
    isNew: int = 0
    hod: Optional[str] = None
    hodid: Optional[int] = 0
    IsEmailNotification: int = Field(0, alias="isEmailNotification")
    PM_Type: int = Field(1, alias="pM_Type")
    PM_Number: str = Field(..., alias="pM_Number")
    PMDate: Optional[str] = Field(None, alias="pmDate") # Expecting 'YYYY-MM-DD HH:MM:SS' or similar
    RequestorId: int = Field(0, alias="requestorId")
    DeliveryAddress: str = Field(..., alias="deliveryAddress")
    Remarks: str = Field(..., alias="remarks")
    UserId: int = Field(..., alias="userId")
    IsSubmitted: int = Field(0, alias="isSubmitted")
    OrgId: int = Field(1, alias="orgId")
    BranchId: int = Field(1, alias="branchId")
    Memo_ID: int = Field(0, alias="memo_ID") # For Update

class MemoDetail(BaseModel):
    Memo_dtl_ID: int = Field(0, alias="memo_dtl_ID")
    Memo_ID: int = Field(0, alias="memo_ID")
    ItemId: int = Field(..., alias="itemId")
    DepartmentId: int = Field(..., alias="departmentId")
    UOMId: int = Field(..., alias="uomId")
    Qty: float = Field(..., alias="qty")
    AvailStk: float = Field(..., alias="availStk")
    DeliveryDate: Optional[str] = Field(None, alias="deliveryDate")
    Remarks: Optional[str] = Field("", alias="remarks")
    itemGroupId: int
    
class CreateUpdateMemoCommand(BaseModel):
    # Using lowercase to match Frontend payload
    header: MemoHeader
    details: List[MemoDetail]

class DeleteMemoCommandInner(BaseModel):
    memoId: int
    inActiveBy: Optional[int] = None
    inActiveIP: Optional[str] = None

class DeleteMemoCommand(BaseModel):
    delete: Optional[DeleteMemoCommandInner] = None
    memoId: Optional[int] = None
    userId: Optional[int] = None

# --- Helper Functions ---

def get_seq_number_internal(cursor, id_val, text, type_val, unit, orgid):
    # Calls proc_shared
    args = (1, id_val, text, type_val, unit, orgid)
    cursor.callproc('proc_shared', args)
    
    result = None
    for res in cursor.stored_results():
        result = res.fetchone()
        break
    return result

# --- Routes ---

@router.get("/get_all")
def get_all(requesterid: int = 0, BranchId: int = 1, OrgId: int = 1, pmnumber: str = "", userid: int = 0):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # params: @opt, @pmid, @branchid, @orgid, @reqid, @pmnumber, @user_id
        args = (1, 0, BranchId, OrgId, requesterid, pmnumber, userid)
        cursor.callproc('proc_purchasememo', args)
        
        results = []
        for result in cursor.stored_results():
            results = result.fetchall()
            break 
            
        return {"status": True, "data": results, "message": "Success"}
    except Exception as e:
        print(f"Error in get_all: {e}")
        return {"status": False, "message": str(e), "data": []}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.get("/GetPurchaseMemoSeqNo")
def get_purchase_memo_seq_no(BranchId: int = 1, orgid: int = 1):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # @opt=2 for SeqNo
        args = (2, 0, BranchId, orgid, 0, "", 0)
        cursor.callproc('proc_purchasememo', args)
        
        data = None
        for result in cursor.stored_results():
            data = result.fetchone()
            break
            
        return {"Status": True, "Message": "Success", "Data": data}
    except Exception as e:
        print(f"Error in GetPurchaseMemoSeqNo: {e}")
        return {"Status": False, "Message": str(e), "Data": None}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.get("/GetById")
def get_by_id(pmid: int, OrgId: int = 1):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # @opt=3 for GetById
        args = (3, pmid, 0, OrgId, 0, "", 0)
        cursor.callproc('proc_purchasememo', args)
        
        # Read multiple result sets: Header, Details, Attachments
        result_sets = []
        for result in cursor.stored_results():
            result_sets.append(result.fetchall())
            
        header = {}
        details = []
        attachments = []
        
        if len(result_sets) > 0 and len(result_sets[0]) > 0:
            header = result_sets[0][0]
        if len(result_sets) > 1:
            details = result_sets[1]
        if len(result_sets) > 2:
            attachments = result_sets[2]
        
        # Fetch details directly from table to ensure all fields are populated
        # (ItemGroup, Department, UOM may be missing from stored procedure)
        if details:
            detail_sql = """
                SELECT 
                    d.Memo_dtl_ID, 
                    d.Memo_ID, 
                    d.ItemId, 
                    d.DepartmentId, 
                    d.UOMId, 
                    d.Qty, 
                    d.AvailStk, 
                    d.DeliveryDate, 
                    d.Remarks, 
                    d.itemGroupId, 
                    d.CreatedBy, 
                    d.CreatedDate, 
                    d.IsActive,
                    i.itemname,
                    ig.groupname,
                    dep.departmentname,
                    uom.UOM
                FROM tbl_purchasememo_detail d
                LEFT JOIN btggasify_masterpanel_live.master_item i ON d.ItemId = i.itemid
                LEFT JOIN btggasify_masterpanel_live.master_itemgroup ig ON d.itemGroupId = ig.groupid
                LEFT JOIN btggasify_live.master_department dep ON d.DepartmentId = dep.departmentid
                LEFT JOIN btggasify_live.master_uom uom ON d.UOMId = uom.Id
                WHERE d.Memo_ID = %s AND d.IsActive = 1
            """
            cursor.execute(detail_sql, (pmid,))
            details = cursor.fetchall()
            
        model_list = {
            "header": header,
            "details": details,
            "attachment": attachments
        }
        
        return {"Status": True, "Message": "Success", "Data": model_list}
        
    except Exception as e:
        print(f"Error in GetById: {e}")
        return {"Status": False, "Message": str(e), "Data": None}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/Create")
def create_purchase_memo(command: CreateUpdateMemoCommand):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        header = command.header
        details = command.details
        
        # 1. Validation / Seq Check
        # C# AddAsync checks sequence number using GetSeqNumber (likely proc_shared)
        # Helper function above handles this.
        seq_res = get_seq_number_internal(cursor, 0, header.PM_Number, 1, header.BranchId, header.OrgId)
        
        message_suffix = ""
        
        if seq_res and seq_res.get('result') == 1:
             new_pm_number = seq_res.get('text')
             message_suffix = f" - The current Memo number {header.PM_Number} is taken for another memo so the new memo number ({new_pm_number}) has been generated"
             header.PM_Number = new_pm_number
        
        # 2. Insert Header
        header_sql = """
            INSERT INTO tbl_purchasememo_header
            (isNew, hod, IsEmailNotification, PM_Type, PM_Number, PMDate, RequestorId, DeliveryAddress, Remarks, CreatedBy, CreatedDate, CreatedIP, IsActive, IsSubmitted, OrgId, BranchId)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), '', 1, %s, %s, %s)
        """
        cursor.execute(header_sql, (
            header.isNew, header.hodid, header.IsEmailNotification, header.PM_Type, header.PM_Number, header.PMDate,
            header.RequestorId, header.DeliveryAddress, header.Remarks, header.UserId, header.IsSubmitted, header.OrgId, header.BranchId
        ))
        
        inserted_header_id = cursor.lastrowid
        
        # 3. Insert Details
        detail_sql = """
            INSERT INTO tbl_purchasememo_detail
            (Memo_ID, ItemId, DepartmentId, UOMId, Qty, AvailStk, DeliveryDate, Remarks, CreatedBy, CreatedDate, CreatedIP, IsActive, itemGroupId)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), '', 1, %s)
        """
        
        for d in details:
            cursor.execute(detail_sql, (
                inserted_header_id, d.ItemId, d.DepartmentId, d.UOMId, d.Qty, d.AvailStk, d.DeliveryDate, "",
                header.UserId, d.itemGroupId
            ))
            
        # 4. Update Sequence
        update_seq_sql = "UPDATE master_documentnumber SET Doc_Number = Doc_Number + 1 WHERE Doc_Type = 1 AND Unit = %s"
        cursor.execute(update_seq_sql, (header.BranchId,))
        
        conn.commit()
        
        msg = "Saved Successfully" if header.IsSubmitted == 0 else "Posted Successfully"
        return {
            "Status": True,
            "Message": msg + message_suffix,
            "Data": inserted_header_id
        }
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error in Create: {e}")
        return {"Status": False, "Message": "Something went wrong: " + str(e), "Data": None}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.put("/Update")
def update_purchase_memo(command: CreateUpdateMemoCommand):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        header = command.header
        details = command.details
        
        memo_id = header.Memo_ID
        
        # 1. Update Header
        header_sql = """
            UPDATE tbl_purchasememo_header
            SET IsEmailNotification=%s, PM_Type=%s, RequestorId=%s, DeliveryAddress=%s, Remarks=%s,
            LastModifiedBY=%s, LastModifiedDate=NOW(), LastMOdifiedIP='', IsSubmitted=%s, isNew=%s, hod=%s
            WHERE Memo_ID = %s
        """
        cursor.execute(header_sql, (
            header.IsEmailNotification, header.PM_Type, header.RequestorId, header.DeliveryAddress, header.Remarks,
            header.UserId, header.IsSubmitted, header.isNew, header.hodid, memo_id
        ))
        
        # 2. Deactivate old details
        cursor.execute("UPDATE tbl_purchasememo_detail SET IsActive = 0 WHERE Memo_ID = %s", (memo_id,))
        
        # 3. Insert or Update Details
        for d in details:
            if d.Memo_dtl_ID == 0:
                # Insert new detail
                detail_insert_sql = """
                    INSERT INTO tbl_purchasememo_detail
                    (Memo_ID, ItemId, DepartmentId, UOMId, Qty, AvailStk, DeliveryDate, Remarks, CreatedBy, CreatedDate, CreatedIP, IsActive, itemGroupId)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '', %s, NOW(), '', 1, %s)
                """
                cursor.execute(detail_insert_sql, (
                    memo_id, d.ItemId, d.DepartmentId, d.UOMId, d.Qty, d.AvailStk, d.DeliveryDate, header.UserId, d.itemGroupId
                ))
            else:
                # Update existing detail
                # C# logic: update tbl_purchasememo_detail set ItemId=..., isactive=1 where Memo_dtl_ID=...
                detail_update_sql = """
                    UPDATE tbl_purchasememo_detail 
                    SET ItemId=%s, DepartmentId=%s, UOMId=%s, DeliveryDate=%s, itemGroupId=%s, Qty=%s, IsActive=1
                    WHERE Memo_dtl_ID=%s
                """
                cursor.execute(detail_update_sql, (
                    d.ItemId, d.DepartmentId, d.UOMId, d.DeliveryDate, d.itemGroupId, d.Qty, d.Memo_dtl_ID
                ))
        
        conn.commit()
        
        msg = "Purchase Memo updated successfully" if header.IsSubmitted == 0 else "Purchase Memo posted successfully"
        return {
            "Status": True,
            "Message": msg,
            "Data": memo_id
        }
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error in Update: {e}")
        return {"Status": False, "Message": "Something went wrong: " + str(e), "Data": None}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/Delete")
def delete_memo(command: DeleteMemoCommand):
    conn = None
    cursor = None
    try:
        if command.delete:
            memo_id = command.delete.memoId
        else:
            memo_id = command.memoId
            
        if memo_id is None:
            raise HTTPException(status_code=400, detail="memoId is required")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        sql = "UPDATE tbl_purchasememo_header SET IsActive=0 WHERE Memo_ID = %s"
        cursor.execute(sql, (memo_id,))
        
        conn.commit()
        
        return {"Status": True, "Message": "Deleted Successfully", "Data": 0}
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error in Delete: {e}")
        return {"Status": False, "Message": str(e), "Data": 0}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/upload-doc")
def upload_document(
    file: List[UploadFile] = File(...),
    memoid: int = Form(...),
    BranchId: int = Form(...),
    UserId: int = Form(...)
):
    conn = None
    cursor = None
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        # Determine strict project root
        current_dir = os.path.dirname(os.path.abspath(__file__)) # routers/
        app_dir = os.path.dirname(current_dir) # app/
        python_root = os.path.dirname(app_dir) # Python/
        project_root = os.path.dirname(python_root) # BTG-GASIGY-COMBINED/
        
        upload_base_dir = os.path.join(
            project_root, 
            "API", "UserPanel", "UserPanel", "UploadedFiles", "ProcurementMemo", str(memoid)
        )
        
        if not os.path.exists(upload_base_dir):
            os.makedirs(upload_base_dir)
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        inserted_items = []

        for f in file:
            filename = f.filename
            file_path = os.path.join(upload_base_dir, filename)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            
            # DB Insert
            sql = """
                INSERT INTO tbl_purchasememo_Attachment 
                (Memo_ID, AttachmentName, AttachmentPath, CreatedBy, CreatedDate, CreatedIP, IsActive)
                VALUES (%s, %s, %s, %s, NOW(), '', 1)
            """
            cursor.execute(sql, (memoid, filename, file_path, UserId))
            inserted_items.append(filename)
            
        conn.commit()
        
        return {"Status": True, "Message": "Success", "Data": inserted_items}
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error in upload_document: {e}")
        return {"Status": False, "Message": "Upload failed: " + str(e), "Data": None}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

from fastapi.responses import FileResponse

@router.get("/download-file")
def download_file(file_path: str = Query(...), file_id: int = Query(0)):
    # Replicating logic mainly from the .NET code but adapted for Python/FastAPI
    # and local development environment mapping.
    
    # 1. Determine local project root (same as in upload-doc)
    current_dir = os.path.dirname(os.path.abspath(__file__)) # routers/
    app_dir = os.path.dirname(current_dir) # app/
    python_root = os.path.dirname(app_dir) # Python/
    project_root = os.path.dirname(python_root) # BTG-GASIGY-COMBINED/
    
    # Clean up file path
    clean_path = file_path.lstrip('/\\')
    
    # 2. Try to find the file
    # Possibility A: It is an absolute path (Linux style from DB)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/octet-stream"
        )
        
    # Possibility B: It is relative to the "ContentRootPath" (which in .NET is the project root usually)
    # We try mapping it to our established upload structure: API/UserPanel/UserPanel/UploadedFiles/...
    # But often the path in DB is just "UploadedFiles/ProcurementMemo/..." or absolute.
    
    # Strategy: 
    # Try joining project_root + clean_path
    # Try joining project_root + "API/UserPanel/UserPanel" + clean_path (Standard .NET structure)
    
    potential_paths = [
        os.path.join(project_root, clean_path),
        os.path.join(project_root, "API", "UserPanel", "UserPanel", clean_path)
    ]
    
    # If the path in DB is like "/var/www/.../UploadedFiles/...", try to extract relative part
    if "UploadedFiles" in file_path:
        try:
             # Extract everything after "UploadedFiles"
             relative_part = file_path.split("UploadedFiles", 1)[1]
             relative_part = "UploadedFiles" + relative_part
             potential_paths.append(os.path.join(project_root, "API", "UserPanel", "UserPanel", relative_part.lstrip('/\\')))
        except:
            pass

    for p in potential_paths:
        if os.path.exists(p):
             return FileResponse(
                path=p,
                filename=os.path.basename(p),
                media_type="application/octet-stream"
            )

    raise HTTPException(status_code=404, detail="File not found.")