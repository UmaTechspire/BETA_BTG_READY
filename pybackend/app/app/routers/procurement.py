from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import mysql.connector
import re
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(
    prefix="/procurement",
    tags=["Procurement"]
)

class ReplyRequest(BaseModel):
    pr_id: int
    org_id: int
    branch_id: int
    user_id: int

class SavePRReplyRequest(BaseModel):
    pr_id: int
    reply: str
    name: str
    sender: str

def get_db_connection_sync():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME_PURCHASE'),
        ssl_disabled=True
    )

@router.post("/save_pr_reply")
async def save_pr_reply(req: SavePRReplyRequest):
    print("Received data:", req.dict())

    pr_id = req.pr_id
    reply = req.reply.strip()
    name = req.name
    sender = req.sender

    if not pr_id or not reply:
        raise HTTPException(status_code=400, detail="Missing pr_id or reply")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reply_entry = f"[{name} at {timestamp}]: {reply}"

    # Determine flags based on sender
    # If GM replies: mark as discussed at GM level (pr_gm_isdiscussed=1), status remains 'S', IsSubmitted=0
    # If User replies: mark as submitted for GM review (IsSubmitted=1), status='Posted'
    if sender == "GM":
        is_submitted = 0
        is_gm_discussed = 1
        status_value = 'S'
    else:
        is_submitted = 1
        is_gm_discussed = 0
        status_value = 'Posted'

    conn = None
    cursor = None

    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()

        # Get current pr_comment
        cursor.execute("SELECT pr_comment FROM tbl_PurchaseRequisition_Header WHERE PRId = %s", (pr_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"PR not found with ID {pr_id}")

        current_comment = row[0] or ""
        new_comment = current_comment + "\n" + reply_entry if current_comment else reply_entry

        # Update pr_comment, IsSubmitted, and pr_gm_isdiscussed flag
        update_query = """
            UPDATE tbl_PurchaseRequisition_Header
            SET pr_comment = %s, IsSubmitted = %s, pr_gm_isdiscussed = %s
            WHERE PRId = %s
        """
        cursor.execute(update_query, (new_comment, is_submitted, is_gm_discussed, pr_id))

        if cursor.rowcount == 0:
            # Should not happen if select found it, unless race condition
            pass 

        conn.commit()
        print(f"PR {pr_id} updated: pr_comment updated, IsSubmitted={is_submitted}, pr_gm_isdiscussed={is_gm_discussed}")
        return {
            "success": True,
            "message": "Reply saved",
            "reply_saved": True,
            "submitted": is_submitted == 1,
            "is_gm_discussed": is_gm_discussed == 1,
            "status": status_value
        }

    except mysql.connector.Error as e:
        print("MYSQL ERROR >>>", repr(e))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    except Exception as e:
        print("GENERIC ERROR >>>", repr(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

    finally:
        if conn:
            conn.close()


class SaveDirectorDiscussionRequest(BaseModel):
    pr_id: int
    reply: str
    name: str
    sender: str  # "Director" or "GM"

@router.post("/save_director_discussion")
async def save_director_discussion(req: SaveDirectorDiscussionRequest):
    pr_id = req.pr_id
    reply = req.reply.strip()
    name = req.name
    sender = req.sender

    if not pr_id or not reply:
        raise HTTPException(status_code=400, detail="Missing pr_id or reply")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reply_entry = f"[{sender} at {timestamp}]: {reply}"

    conn = None
    cursor = None

    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()

        # Get current pr_dir_comment
        cursor.execute("SELECT pr_dir_comment FROM tbl_PurchaseRequisition_Header WHERE PRId = %s", (pr_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"PR not found with ID {pr_id}")

        current_comment = row[0] or ""
        new_comment = current_comment + "\n" + reply_entry if current_comment else reply_entry

        # Update pr_dir_comment and pr_director_isdiscussed status
        # If Director sends, pr_director_isdiscussed becomes 1.
        # If GM replies, we must ensuring PR is visible to Director, so we force updated flags.
        # We also reset pr_director_isapproved to 0 to ensure it's not hidden in an 'Approved' filter.
        # CRITICAL: We also set pr_gm_isapproved = 1 to ensure it is visible at Director Level (Level 2).
        
        is_discussed = 1 
        is_approved = 0 # Force reset approval to ensure it appears as "Discussed" (Orange)
        gm_approved = 1 # Force GM approval to ensure it reaches Director
        
        update_query = """
            UPDATE tbl_PurchaseRequisition_Header
            SET pr_dir_comment = %s, pr_director_isdiscussed = %s, pr_director_isapproved = %s, pr_gm_isapproved = %s
            WHERE PRId = %s
        """
        cursor.execute(update_query, (new_comment, is_discussed, is_approved, gm_approved, pr_id))
        conn.commit()

        return {
            "success": True,
            "message": "Director discussion saved",
            "new_comment": new_comment
        }

    except mysql.connector.Error as e:
        print("MYSQL ERROR >>>", repr(e))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    except Exception as e:
        print("GENERIC ERROR >>>", repr(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@router.get("/get_director_comments/{pr_id}")
async def get_director_comments(pr_id: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        cursor.execute("SELECT pr_dir_comment FROM tbl_PurchaseRequisition_Header WHERE PRId = %s", (pr_id,))
        row = cursor.fetchone()
        if not row:
             return {"comments": ""}
        return {"comments": row[0] or ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/get_remarks_history")
async def get_remarks_history(prid: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        cursor.execute("SELECT pr_comment FROM tbl_PurchaseRequisition_Header WHERE PRId = %s", (prid,))
        row = cursor.fetchone()
        
        history = []
        if row and row[0]:
            raw_comments = row[0]
            lines = raw_comments.split('\n')
            
            parsed_entries = []
            current_entry = None
            
            for line in lines:
                # Match pattern: [Username at YYYY-MM-DD HH:MM:SS]: Message
                match = re.search(r'^\[(.*?) at (.*?)\]: (.*)$', line)
                if match:
                    if current_entry:
                        parsed_entries.append(current_entry)
                        
                    current_entry = {
                        "username": match.group(1),
                        "logdate": match.group(2),
                        "raw_line": line
                    }
                else:
                    # Continuation of previous message
                    if current_entry:
                        current_entry["raw_line"] += "\n" + line
                    elif line.strip():
                        # Orphaned line without header
                        current_entry = {
                            "username": "System",
                            "logdate": "",
                            "raw_line": line
                        }
            
            if current_entry:
                parsed_entries.append(current_entry)
                
            # Build cumulative snapshots for diff logic in frontend
            cumulative_comment = ""
            for idx, entry in enumerate(parsed_entries):
                if idx > 0:
                     cumulative_comment += "\n" + entry["raw_line"]
                else:
                     cumulative_comment = entry["raw_line"]
                
                history.append({
                    "username": entry["username"],
                    "logdate": entry["logdate"], 
                    "pr_comment": cumulative_comment
                })
        
        print(f"Remarks history for PR {prid}:", history)
        return history  # Return array directly, not wrapped in status

    except Exception as e:
        print("ERROR converting remarks:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@router.get("/GetGRNsByPO")
async def get_grns_by_po(poid: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT
            gh.grnno AS GRNNo,
            im.groupid,
            ig.groupname AS ItemGroup,
            im.itemname AS ItemName,
            gd.grnQty AS Qty,
            um.UOM AS Uom,
            gd.UnitPrice AS UnitPrice,
            gd.TotalAmount AS TotalAmount,
            IFNULL(por.discountperc, 0) AS DiscountPerc,
            IFNULL(por.discountvalue, 0) AS DiscountValue,
            IFNULL(por.qty, 0) AS POQty,
            IFNULL(por.taxperc, 0) AS TaxPerc,
            IFNULL(por.vatperc, 0) AS VatPerc
        FROM tbl_grn_detail gd
        JOIN tbl_grn_header gh ON gh.grnid = gd.grnid
        LEFT JOIN tbl_purchaseorder_requisitions por ON gd.porid = por.porid
        LEFT JOIN btggasify_masterpanel_live.master_item im ON im.itemid = gd.itemid
        LEFT JOIN btggasify_masterpanel_live.master_itemgroup ig ON ig.groupid = im.groupid
        LEFT JOIN btggasify_live.master_uom um ON um.Id = gd.uomid
        WHERE gd.poid = %s AND gh.IsSubmitted = 1 AND gd.isactive = 1 AND gh.isactive = 1
        """
        cursor.execute(query, (poid,))
        results = cursor.fetchall()
        return {"status": True, "data": results}
    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

