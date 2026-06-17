from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import mysql.connector
import os
from datetime import datetime
from dotenv import load_dotenv
from typing import List  # <--- Added for List[int]

load_dotenv()

router = APIRouter(
    prefix="/api/claim",
    tags=["Claim Payment Discussion"]
)

# --- Existing Models ---
class HodDiscussionRequest(BaseModel):
    claim_id: int
    comment: str
    hod_name: str

class ApplicantReplyRequest(BaseModel):
    claim_id: int
    reply: str
    applicant_name: str

class DiscussionRequest(BaseModel):
    claim_id: int
    comment: str
    user_name: str
    sender_role: str = "" 

# --- NEW MODEL FOR SPC ---
class GenerateSPCRequest(BaseModel):
    Ids: List[int]
    OrgId: int
    BranchId: int
    UserId: int
    CreatedDate: str

class PaymentSummarySyncRequest(BaseModel):
    summary_id: int
    net_cash_withdraw: float

def get_db_connection_sync():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME_FINANCE', 'btggasify_finance_live'),
        port=int(os.getenv('DB_PORT', 3306))
    )

# --- NEW FUNCTION: Generate SPC ---
@router.post("/generate_spc")
def generate_spc(payload: GenerateSPCRequest):
    conn = None
    cursor = None
    try:
        # We need to connect to the User Panel DB for Claims
        # Using the same credentials but switching DB or referencing explicitly
        user_db_name = os.getenv('DB_NAME_USER_NEW', 'btggasify_userpanel_live')
        
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        if not payload.Ids:
            raise HTTPException(status_code=400, detail="No IRNs selected")

        # 1. Generate Claim No (SPC-SEQ)
        # Note: We explicitly reference the user_db_name table
        seq_query = f"SELECT IFNULL(MAX(id), 0) + 1 FROM {user_db_name}.tbl_claim_header"
        cursor.execute(seq_query)
        next_id = cursor.fetchone()[0]
        claim_no = f"SPC-{next_id}"

        # 2. Create Claim Header
        header_query = f"""
            INSERT INTO {user_db_name}.tbl_claim_header 
            (ClaimNo, ClaimDate, OrgId, BranchId, CreatedBy, CreatedDate, Status, IsActive)
            VALUES (%s, NOW(), %s, %s, %s, NOW(), 'Draft', 1)
        """
        cursor.execute(header_query, (claim_no, payload.OrgId, payload.BranchId, payload.UserId))
        new_claim_id = cursor.lastrowid

        # 3. Update IRNs (Invoice Receipt Headers)
        # Using 'format_strings' for IN clause in MySQL connector
        format_strings = ','.join(['%s'] * len(payload.Ids))
        update_query = f"""
            UPDATE {user_db_name}.tbl_invoice_receipt_header 
            SET ClaimId = %s, 
                ClaimStatus = 'Claimed'
            WHERE id IN ({format_strings})
        """
        
        # Combine parameters: claim_id first, then the list of IDs
        params = [new_claim_id] + payload.Ids
        cursor.execute(update_query, tuple(params))

        conn.commit()

        return {
            "status": True, 
            "message": f"Payment Claim {claim_no} generated successfully!", 
            "data": new_claim_id
        }

    except Exception as e:
        print(f"Error generating SPC: {str(e)}")
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/update_payment_summary_sync")
def update_payment_summary_sync(payload: PaymentSummarySyncRequest):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        # Call the stored procedure to update bank totals and net cash withdraw
        # proc_UpdatePaymentSummaryValues(p_SummaryId INT, p_NetCashWithdraw DECIMAL(18,2))
        cursor.callproc('proc_UpdatePaymentSummaryValues', (payload.summary_id, payload.net_cash_withdraw))
        conn.commit()

        return {
            "status": True,
            "message": "Payment Summary synchronized successfully!"
        }

    except Exception as e: 
        print(f"Error synchronizing Payment Summary: {str(e)}")
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- EXISTING FUNCTIONS BELOW (Unchanged) ---

@router.post("/save_hod_discussion")
def save_hod_discussion(req: HodDiscussionRequest):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Fetch existing comment
        cursor.execute("SELECT applicant_hod_comment, hod_discussed_count FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (req.claim_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        existing_comment = row[0] or ""
        current_count = row[1] or 0
        new_count = current_count + 1
        
        if new_count == 4:
            # 4th time logic
            forced_message = "Please cancel the transaction"
            comment_entry = f"[{req.hod_name} at {timestamp}]: {forced_message}"
            new_comment = existing_comment + "\n" + comment_entry if existing_comment else comment_entry
            
            # Reset approvals and set Status to 'Saved'
            update_query = """
                UPDATE tbl_claimAndpayment_header 
                SET claim_hod_isdiscussed = 1, 
                    hod_discussed_count = %s, 
                    applicant_hod_comment = %s, 
                    claim_hod_isapproved = 0,
                    claim_gm_isapproved = 0,
                    claim_director_isapproved = 0,
                    is_delete_required = 1
                WHERE Claim_ID = %s
            """
            cursor.execute(update_query, (new_count, new_comment, req.claim_id))
        else:
            # Normal logic
            comment_entry = f"[{req.hod_name} at {timestamp}]: {req.comment}"
            new_comment = existing_comment + "\n" + comment_entry if existing_comment else comment_entry
            
            update_query = """
                UPDATE tbl_claimAndpayment_header 
                SET claim_hod_isdiscussed = 1, 
                    hod_discussed_count = %s, 
                    applicant_hod_comment = %s
                WHERE Claim_ID = %s
            """
            cursor.execute(update_query, (new_count, new_comment, req.claim_id))

        conn.commit()
        
        return {"status": True, "message": "Discussion sent to applicant", "data": new_comment, "is_delete_required": new_count == 4}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/save_applicant_reply")
def save_applicant_reply(req: ApplicantReplyRequest):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reply_entry = f"[{req.applicant_name} at {timestamp}]: {req.reply}"
        
        # Fetch existing comment and Department
        cursor.execute("SELECT applicant_hod_comment, applicant_gm_comment, DepartmentId FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (req.claim_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Claim not found")
            
        existing_hod_comment = row[0] or ""
        existing_gm_comment = row[1] or ""
        department_id = row[2] or 0
        
        final_comment = ""
        msg = ""

        if department_id != 9:
            # Dept != 9: Discussion between Claimant <-> GM
            new_comment = existing_gm_comment + "\n" + reply_entry if existing_gm_comment else reply_entry
            
            # Sent back to GM (Applicant replies)
            # update applicant_gm_comment, IsSubmitted=1 (sent), claim_gm_isdiscussed=0 (pending GM view)
            update_query = """
                UPDATE tbl_claimAndpayment_header 
                SET applicant_gm_comment = %s, 
                    IsSubmitted = 1,
                    claim_gm_isdiscussed = 0
                WHERE Claim_ID = %s
            """
            cursor.execute(update_query, (new_comment, req.claim_id))
            final_comment = new_comment
            msg = "Reply sent to GM"
        else:
            # Dept = 9: Existing logic (Claimant <-> HOD)
            new_comment = existing_hod_comment + "\n" + reply_entry if existing_hod_comment else reply_entry
            
            update_query = """
                UPDATE tbl_claimAndpayment_header 
                SET applicant_hod_comment = %s, 
                    IsSubmitted = 1,
                    claim_hod_isdiscussed = 0
                WHERE Claim_ID = %s
            """
            cursor.execute(update_query, (new_comment, req.claim_id))
            final_comment = new_comment
            msg = "Reply sent to HOD"
        
        conn.commit()
        
        return {"status": True, "message": msg, "data": final_comment}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.get("/get_history/{claim_id}")
def get_history(claim_id: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        cursor.execute("SELECT applicant_hod_comment, applicant_gm_comment, DepartmentId FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (claim_id,))
        row = cursor.fetchone()
        
        if not row:
            return {"status": False, "message": "Claim not found"}
            
        department_id = row[2] or 0
        if department_id != 9:
             # Dept != 9: Show applicant_gm_comment
             comment_data = row[1] or ""
        else:
             # Dept = 9: Show applicant_hod_comment
             comment_data = row[0] or ""
            
        return {"status": True, "data": comment_data}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/save_hod_gm_discussion")
def save_hod_gm_discussion(req: DiscussionRequest):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("SELECT hod_gm_comment, gm_discussed_count, applicant_gm_comment, DepartmentId FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (req.claim_id,))
        row = cursor.fetchone()
        
        # Close cursor to ensure clean slate
        cursor.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        existing_hod_gm_comment = row[0] or ""
        current_gm_title = row[1] or 0
        existing_applicant_gm_comment = row[2] or ""
        department_id = row[3] or 0
        
        is_third_count = False
        if req.sender_role == "GM" and (current_gm_title + 1) == 4:
             is_third_count = True
        
        if is_third_count:
             comment_entry = f"[{req.user_name} at {timestamp}]: Please cancel the transaction"
        else:
             comment_entry = f"[{req.user_name} at {timestamp}]: {req.comment}"
        
        new_comment = ""
        
        # Re-open cursor for Update
        cursor = conn.cursor()
        
        update_parts = []
        params = []
        
        if department_id != 9:
             # Dept != 9: GM talks to Applicant (skip HOD)
             # Use applicant_gm_comment
             new_comment = existing_applicant_gm_comment + "\n" + comment_entry if existing_applicant_gm_comment else comment_entry
             update_parts = ["applicant_gm_comment = %s"]
             params.append(new_comment)
             
             if req.sender_role == "GM":
                 update_parts.append("claim_gm_isdiscussed = 1")
                 update_parts.append("gm_discussed_count = %s")
                 params.append(current_gm_title + 1)
                 
                 # Send to Applicant
                 # update_parts.append("IsSubmitted = 0")
                 
                 if is_third_count:
                    update_parts.append("is_delete_required = 1")
                    # Do not reset HOD approval as HOD is skipped/auto-approved
                    update_parts.append("claim_director_isapproved = 0")
        else:
             # Dept = 9: HOD <-> GM
             new_comment = existing_hod_gm_comment + "\n" + comment_entry if existing_hod_gm_comment else comment_entry
             update_parts = ["hod_gm_comment = %s"]
             params.append(new_comment)
             
             if req.sender_role == "GM":
                if is_third_count:
                    # 3rd time logic
                    update_parts.append("claim_gm_isdiscussed = 1")
                    update_parts.append("gm_discussed_count = %s")
                    params.append(current_gm_title + 1)
                    
                    # Reset everything
                    update_parts.append("claim_hod_isapproved = 0")
                    update_parts.append("claim_gm_isapproved = 0")
                    update_parts.append("claim_director_isapproved = 0")
                    # update_parts.append("IsSubmitted = 0")
                    update_parts.append("is_delete_required = 1")
                    
                else:
                    update_parts.append("claim_gm_isdiscussed = 1")
                    update_parts.append("gm_discussed_count = %s")
                    params.append(current_gm_title + 1)
                    update_parts.append("claim_hod_isapproved = 0") # Send back to HOD

             elif req.sender_role == "HOD":
                update_parts.append("claim_gm_isdiscussed = 0")
                update_parts.append("claim_hod_isapproved = 1")

        update_query = f"UPDATE tbl_claimAndpayment_header SET {', '.join(update_parts)} WHERE Claim_ID = %s"
        params.append(req.claim_id)
        
        cursor.execute(update_query, tuple(params))
        conn.commit()
        
        return {"status": True, "message": "Discussion saved", "data": new_comment, "is_delete_required": is_third_count}
    except Exception as e:
        print(f"Error in save_hod_gm_discussion: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conn: conn.close()
        except:
            pass

@router.get("/get_hod_gm_history/{claim_id}")
def get_hod_gm_history(claim_id: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        cursor.execute("SELECT hod_gm_comment, applicant_gm_comment, DepartmentId FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (claim_id,))
        row = cursor.fetchone()
        cursor.fetchall() # clear any remaining
        
        if not row:
            return {"status": False, "message": "Claim not found"}
        
        department_id = row[2] or 0
        if department_id != 9:
             # Dept != 9: Show applicant_gm_comment for GM
             comment_data = row[1] or ""
        else:
             # Dept = 9: Show hod_gm_comment
             comment_data = row[0] or ""
        
        return {"status": True, "data": comment_data}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- GM <-> Director Discussion ---

@router.post("/save_gm_director_discussion")
def save_gm_director_discussion(req: DiscussionRequest):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("SELECT gm_director_comment, director_discussed_count FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (req.claim_id,))
        row = cursor.fetchone()
        
        cursor.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        existing_comment = row[0] or ""
        current_dir_count = row[1] or 0
        
        is_third_count = False
        if req.sender_role == "Director" and (current_dir_count + 1) == 4:
             is_third_count = True
        
        if is_third_count:
             comment_entry = f"[{req.user_name} at {timestamp}]: Please cancel the transaction"
        else:
             comment_entry = f"[{req.user_name} at {timestamp}]: {req.comment}"

        new_comment = existing_comment + "\n" + comment_entry if existing_comment else comment_entry
        
        cursor = conn.cursor()
        
        update_parts = ["gm_director_comment = %s"]
        params = [new_comment]
        
        if req.sender_role == "Director":
            if is_third_count:
                 # 3rd time logic - reset all approvals
                update_parts.append("claim_director_isdiscussed = 1")
                update_parts.append("director_discussed_count = %s")
                params.append(current_dir_count + 1)
                update_parts.append("claim_gm_isapproved = 0")
                update_parts.append("claim_hod_isapproved = 0")
                update_parts.append("claim_director_isapproved = 0")
                # update_parts.append("IsSubmitted = 0")
                update_parts.append("is_delete_required = 1")
            else:
                update_parts.append("claim_director_isdiscussed = 1")
                update_parts.append("director_discussed_count = %s")
                params.append(current_dir_count + 1)
                update_parts.append("claim_gm_isapproved = 0")
                
        elif req.sender_role == "GM":
            update_parts.append("claim_director_isdiscussed = 0")
            update_parts.append("claim_gm_isapproved = 1")
            
        update_query = f"UPDATE tbl_claimAndpayment_header SET {', '.join(update_parts)} WHERE Claim_ID = %s"
        params.append(req.claim_id)
        
        cursor.execute(update_query, tuple(params))
        conn.commit()
        
        return {"status": True, "message": "Discussion saved", "data": new_comment, "is_delete_required": is_third_count}
    except Exception as e:
        print(f"Error in save_gm_director_discussion: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")
    finally:
        try:
            if cursor: cursor.close()
            if conn: conn.close()
        except:
            pass

@router.get("/get_gm_director_history/{claim_id}")
def get_gm_director_history(claim_id: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        cursor.execute("SELECT gm_director_comment FROM tbl_claimAndpayment_header WHERE Claim_ID = %s", (claim_id,))
        row = cursor.fetchone()
        cursor.fetchall() # clear
        
        if not row:
            return {"status": False, "message": "Claim not found"}
        
        return {"status": True, "data": row[0] or ""}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.get("/get_payment_summary_seq_no")
def get_payment_summary_seq_no(orgid: int, branchid: int, userid: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        # 🟢 FETCH LATEST: Match the PPP0000000 format seen in the UI
        # Only consider records for this Org/Branch with a non-empty PPP number
        query = """
            SELECT PaymentNo 
            FROM tbl_PaymentSummary_header 
            WHERE OrgId = %s AND BranchId = %s 
              AND PaymentNo LIKE 'PPP%' 
              AND PaymentNo <> ''
            ORDER BY SummaryId DESC 
            LIMIT 1
        """
        cursor.execute(query, (orgid, branchid))
        row = cursor.fetchone()
        
        # Fallback: If no records for this specific branch, try to find the last global PPP number
        if not row:
            query_global = """
                SELECT PaymentNo 
                FROM tbl_PaymentSummary_header 
                WHERE PaymentNo LIKE 'PPP%' 
                  AND PaymentNo <> ''
                ORDER BY SummaryId DESC 
                LIMIT 1
            """
            cursor.execute(query_global)
            row = cursor.fetchone()

        if row and row[0]:
            last_no = row[0].strip()  # e.g., "PPP00000060"
            import re
            # Extract numbers from any part of the string if suffix fails
            match = re.search(r'(\d+)$', last_no)
            if match:
                last_num = int(match.group(1))
                next_num = last_num + 1
                seq_no = f"PPP{str(next_num).zfill(7)}"
            else:
                # Handle case where number is not at the end
                all_nums = re.findall(r'\d+', last_no)
                if all_nums:
                    last_num = int(all_nums[-1])
                    next_num = last_num + 1
                    seq_no = f"PPP{str(next_num).zfill(7)}"
                else:
                    seq_no = "PPP0000001"
        else:
            # First record for this Org/Branch or globally
            seq_no = "PPP0000001"
        
        return {
            "status": True,
            "data": {
                "PaymentNo": seq_no,
                "ClaimNo": seq_no,
                "debug": {
                    "received_orgid": orgid,
                    "received_branchid": branchid,
                    "found_last_no": row[0] if row else None
                }
            }
        }
    except Exception as e:
        print(f"Error generating PPP Sequence: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- NEW: Resolve Claim Application Number → Claim_ID (for BankBook Details popup) ---
@router.get("/get-id-by-no")
def get_claim_id_by_no(claim_no: str):
    """
    Resolves a Claim ApplicationNo (e.g. 'CLM0003750') to its database Claim_ID.
    Used by BankBook to fetch the correct claim details without relying on
    fragile digit-stripping from the application number string.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT Claim_ID FROM tbl_claimAndpayment_header WHERE ApplicationNo = %s AND IsActive = 1 LIMIT 1",
            (claim_no,)
        )
        row = cursor.fetchone()

        if row:
            return {"status": True, "claim_id": row["Claim_ID"]}

        return {"status": False, "message": f"No active claim found for application number '{claim_no}'"}

    except Exception as e:
        print(f"Error resolving claim number: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- NEW: Get All Claims (Migration from .NET proc_claimAndpayment OPT=1) ---
@router.get("/get_all")
def get_all_claims(
    departmentid: int = 0,
    currencyid: int = 0,
    categoryid: int = 0,
    branchId: int = 0,
    orgid: int = 0,
    user_id: int = 0,
    claimtypeid: int = 0
):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)

        user_db = os.getenv('DB_NAME_USER_NEW', 'btggasify_userpanel_live')
        live_db = os.getenv('DB_NAME_USER', 'btggasify_live')
        purchase_db = os.getenv('DB_NAME_PURCHASE', 'btggasify_purchase_live')
        
        # 1. Check if user is HOD
        is_hod = 0
        hod_query = f"SELECT IFNULL(ishod, 0) FROM {live_db}.users WHERE id = %s"
        cursor.execute(hod_query, (user_id,))
        row = cursor.fetchone()
        if row:
            is_hod = list(row.values())[0]

        # 2. Main Query Logic (Simplified compared to SP string concatenation)
        # Purpose aggregation subquery or join
        purpose_subquery = f"""
            (SELECT Claim_ID, 
                    GROUP_CONCAT(DISTINCT Purpose SEPARATOR ', ') as Purpose,
                    GROUP_CONCAT(DISTINCT IFNULL(docReference, '')) as pono,
                    MAX(IFNULL(poid, 0)) as poid
             FROM tbl_claimAndpayment_Details
             WHERE IsActive = 1 {" AND ClaimTypeId = " + str(claimtypeid) if claimtypeid > 0 else ""}
             GROUP BY Claim_ID) as tfc
        """

        query = f"""
            SELECT 
                tfc.Purpose AS purpose, 
                tfc.pono,
                tfc.poid,
                ch.Claim_ID, 
                ch.ApplicationNo AS claimno,
                DATE_FORMAT(ch.ApplicationDate, '%d-%b-%Y') AS claimdate,
                cat.claimcategory AS claimcategory,
                CASE WHEN ch.ClaimCategoryId=3 THEN IFNULL(u.username,'') ELSE u.username END AS applicantname,
                CASE WHEN ch.ClaimCategoryId=3 THEN IFNULL(md.departmentname,'') ELSE md.departmentname END AS departmentname,
                CASE WHEN ch.IsSubmitted=0 AND (IFNULL(ch.Claim_Discussed_Count,0)<=3 
                    AND IFNULL(ch.PPP_Discussed_Count,0)<=3 AND IFNULL(ch.isdiscussionaccepted,0)=0 
                    AND IFNULL(ch.pv_dis_count,0)<=3)
                    THEN 'Saved' ELSE 'Posted' END AS Status,
                cur.CurrencyCode AS transactioncurrency,
                IFNULL(pm.PaymentMethod,'') AS paymentmethodname,
                ch.claimamountintc, 
                IFNULL(ch.isclaimant_discussed,0) AS isclaimant_discussed,
                CASE WHEN IFNULL(ch.claim_hod_isapproved,0)=0 AND (IFNULL(ch.Claim_Discussed_Count,0)>3 OR IFNULL(ch.PPP_Discussed_Count,0)>3 OR IFNULL(ch.pv_dis_count,0)>3 OR IFNULL(ch.IsSubmitted,0)=0) THEN 1 ELSE 0 END AS candelete,
                CASE WHEN IFNULL(ch.ppp_gm_approvalone,0)=0 THEN 1 ELSE 0 END AS canedit,
                ch.totalamountinidr, ch.voucherid, ch.voucherno,
                DATE_FORMAT(ch.PaymentDate, '%d-%b-%Y') AS paymentDate,
                IFNULL(psh.PaymentNo,'') AS PaymentNo,
                IFNULL(ph.nettotal, 0) AS po_amount,
                DATE_FORMAT(ph.podate, '%d-%b-%Y') AS podate,
                CASE WHEN IFNULL(ch.isdiscussionaccepted,0)=1 THEN 1 ELSE IFNULL(ch.IsSubmitted,0) END AS isSubmitted,
                ch.SupplierId,
                IFNULL(ch.claim_director_isapproved, 0) AS claim_director_isapproved,
                IFNULL(ch.PPP_PV_Director_approve, 0) AS ppp_pv_director_approved,
                IFNULL(ch.is_delete_required,0) AS is_delete_required,
                IFNULL(ch.finance_cancel, 0) AS finance_cancel,
                IFNULL(ch.finance_cancel_remarks, '') AS finance_cancel_remarks,
                IFNULL(ch.hod_discussed_count,0) AS hod_discussed_count,
                IFNULL(ch.gm_discussed_count,0) AS gm_discussed_count,
                IFNULL(ch.director_discussed_count,0) AS director_discussed_count,
                CASE WHEN IFNULL(ch.Claim_Discussed_Count,0)>3 OR IFNULL(ch.PPP_Discussed_Count,0)>3 OR IFNULL(ch.pv_dis_count,0)> 3 THEN 1 ELSE 0 END AS IsReject,
                CASE WHEN IFNULL(ch.claim_gm_isapproved,0)=0 AND IFNULL(ch.claim_gm_isdiscussed,0)=1 
                    AND IFNULL(ch.IsSubmitted,0)=0 AND IFNULL(ch.Claim_Discussed_Count,0)<=3 
                    AND IFNULL(ch.PPP_Discussed_Count,0)<=3 THEN 1 ELSE 0 END AS candiscuss
            FROM tbl_claimAndpayment_header ch
            JOIN master_claimcategory cat ON cat.id = ch.ClaimCategoryId
            JOIN {purpose_subquery} ON tfc.Claim_ID = ch.Claim_ID
            LEFT JOIN {live_db}.master_department md ON md.DepartmentId = ch.DepartmentId
            LEFT JOIN {live_db}.users u ON u.id = ch.ApplicantId
            JOIN {live_db}.master_currency cur ON cur.currencyid = ch.TransactionCurrencyId
            LEFT JOIN {live_db}.master_paymentmethod pm ON pm.Id = ch.ModeOfPaymentId
            LEFT JOIN tbl_PaymentSummary_header psh ON psh.SummaryId = ch.SummaryId AND psh.Isactive=1
            LEFT JOIN {purchase_db}.tbl_purchaseorder_header ph ON ph.poid = tfc.poid
            WHERE ch.IsActive=1
            AND (ch.ClaimCategoryId = %s OR %s = 0)
            AND (ch.DepartmentId = %s OR %s = 0)
            AND (ch.TransactionCurrencyId = %s OR %s = 0)
            AND (
                (SELECT hodid FROM {live_db}.users WHERE id=%s) IS NULL
                OR ch.CreatedBy = %s
                OR (%s = 1 AND ch.CreatedBy IN (SELECT id FROM {live_db}.users WHERE hodid=%s))
            )
            ORDER BY ch.Claim_ID ASC
        """
        
        params = (
            categoryid, categoryid,
            departmentid, departmentid,
            currencyid, currencyid,
            user_id, user_id,
            is_hod, user_id
        )

        cursor.execute(query, params)
        data = cursor.fetchall()

        return {
            "status": True,
            "message": "Success",
            "data": data
        }

    except Exception as e:
        print(f"Error fetching claims: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- NEW: Delete Claim (Migration from .NET) ---
class DeleteClaimRequest(BaseModel):
    ClaimId: int
    InActiveBy: int

@router.post("/delete")
def delete_claim(req: DeleteClaimRequest):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor()
        
        # 1. Update IsActive = 0
        update_query = """
            UPDATE tbl_claimAndpayment_header 
            SET IsActive = 0, 
                InActiveBy = %s, 
                InActiveDate = NOW(), 
                InActiveIP = %s
            WHERE Claim_ID = %s
        """
        # Using ClaimId as IP placeholder if real IP not available, matching .NET logic
        cursor.execute(update_query, (req.InActiveBy, str(req.ClaimId), req.ClaimId))
        
        # 2. Call cleanup procedure
        cursor.callproc('proc_claimhodapproval', (req.ClaimId,))
        
        conn.commit()
        
        return {
            "status": True,
            "message": "Deleted Successfully"
        }
    except Exception as e:
        print(f"Error deleting claim: {str(e)}")
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- NEW: Get Seq Number (Migration from .NET proc_claimAndpayment OPT=3) ---
@router.get("/get_seq_num")
def get_seq_num(branchId: int, orgid: int, userid: int):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)
        
        live_db = os.getenv('DB_NAME_USER', 'btggasify_live')
        
        # This replicates OPT=3 of the stored procedure
        # It's a bit complex with nested results, so we'll use the existing logic pattern
        
        # 1. Get HOD info
        hod_query = f"""
            SELECT h.username as HOD, h.id as HODID
            FROM {live_db}.users a
            LEFT JOIN {live_db}.users h ON h.id = IFNULL(a.hodid, 158)
            WHERE a.id = %s
            LIMIT 1
        """
        cursor.execute(hod_query, (userid,))
        hod_info = cursor.fetchone() or {"HOD": "", "HODID": 0}

        # 2. Get Applicant info
        app_query = f"""
            SELECT a.id as applicantid, b.DepartmentId as departmentid, IFNULL(a.IsHOD, 0) as hodlogin, 
                   a.username as applicantname, b.DepartmentName as departmentname
            FROM {live_db}.users a 
            INNER JOIN {live_db}.master_department b ON a.Department = b.DepartmentId 
            WHERE a.id = %s 
            LIMIT 1
        """
        cursor.execute(app_query, (userid,))
        app_info = cursor.fetchone() or {}

        # 3. Get Document Number
        doc_query = f"""
            SELECT CONCAT(a.prefixtext, LPAD(a.Doc_Number + 1, 7, '0')) AS ClaimNo
            FROM master_documentnumber a 
            WHERE a.Doc_Type = 1 AND a.Unit = %s
            LIMIT 1
        """
        cursor.execute(doc_query, (branchId,))
        doc_info = cursor.fetchone() or {"ClaimNo": ""}

        # 4. Merge results
        result = {
            "ClaimNo": doc_info["ClaimNo"],
            "HOD": hod_info["HOD"],
            "HODID": hod_info["HODID"],
            "applicantid": app_info.get("applicantid"),
            "departmentid": app_info.get("departmentid"),
            "hodlogin": app_info.get("hodlogin"),
            "applicantname": app_info.get("applicantname"),
            "departmentname": app_info.get("departmentname"),
            # Add other defaults if needed
            "CurrencyId": 1,
            "CurrencyName": "IDR",
            "ExchangeRate": 1.0,
            "CostCenter": "Main",
            "CostCenter_id": 1
        }

        return {
            "status": True,
            "message": "Success",
            "data": result
        }
    except Exception as e:
        print(f"Error fetching sequence: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- NEW: Get PPP PV Director Approval Status by SummaryId ---
@router.get("/get_pv_director_approval_status")
def get_pv_director_approval_status():
    """
    Returns PPP_PV_Director_approve status grouped by SummaryId.
    Used by the PPP page to determine if the Update Voucher button should be disabled.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                SummaryId,
                MIN(IFNULL(PPP_PV_Director_approve, 0)) AS PPP_PV_Director_approve,
                MIN(IFNULL(PPP_PV_Commissioner_approveone, 0)) AS PPP_PV_Commissioner_approveone
            FROM tbl_claimAndpayment_header
            WHERE IsActive = 1 
              AND IFNULL(SummaryId, 0) > 0
            GROUP BY SummaryId
            HAVING MIN(IFNULL(PPP_PV_Director_approve, 0)) = 1
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        # Build a map: SummaryId -> approval status
        approval_map = {}
        for row in rows:
            approval_map[str(row["SummaryId"])] = {
                "PPP_PV_Director_approve": row["PPP_PV_Director_approve"],
                "PPP_PV_Commissioner_approveone": row["PPP_PV_Commissioner_approveone"]
            }

        return {
            "status": True,
            "message": "Success",
            "data": approval_map
        }
    except Exception as e:
        print(f"Error fetching PV Director approval status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()