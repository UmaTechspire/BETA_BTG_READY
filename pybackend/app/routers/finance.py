from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from .. import schemas, crud, database
from sqlalchemy import text
import mysql.connector
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

# --- UPDATED DEFAULTS TO LIVE DATABASES ---
DB_NAME_FINANCE = os.getenv('DB_NAME_FINANCE', 'btggasify_finance_live')
DB_NAME_USER = os.getenv('DB_NAME_USER', 'btggasify_live')
DB_NAME_USER_NEW = os.getenv('DB_NAME_USER_NEW', 'btggasify_userpanel_live')
DB_NAME_MASTER = os.getenv('DB_NAME_MASTER', 'btggasify_masterpanel_live')
DB_NAME_PURCHASE = os.getenv('DB_NAME_PURCHASE', 'btggasify_purchase_live')
DB_NAME_OLD = os.getenv('DB_NAME_OLD', 'btggasify_live')

router = APIRouter(
    prefix="/AR",
    tags=["Accounts Receivable"]
)

# --- CATEGORY MAPPING FOR COMPARATIVE REPORTS ---
PL_CATEGORIES = [
    {"label": "REVENUE", "id": "REV_HDR", "isHeader": True, "level": 0},
    {"label": "LPG Cylinder Sales", "id": "REV_LPG", "codes": ["4000-001", "4100-001"], "level": 1},
    {"label": "Industrial Gas Sales", "id": "REV_IND", "codes": ["4100-002", "4100-003", "4100-004", "4100-005"], "level": 1},
    {"label": "Gas Refilling Charges", "id": "REV_REF", "codes": ["4110-001"], "level": 1},
    {"label": "Cylinder Rental Income", "id": "REV_RENT", "codes": ["4120-001"], "level": 1},
    {"label": "Transportation Charges", "id": "REV_TRANS", "codes": ["4130-001"], "level": 1},
    {"label": "TOTAL REVENUE", "id": "REV_TOTAL", "isTotal": True, "level": 0},
    
    {"label": "COST OF GOODS SOLD", "id": "COGS_HDR", "isHeader": True, "level": 0},
    {"label": "Gas Purchase Cost", "id": "COGS_PURCH", "codes": ["5900-001", "5900-002", "5900-003"], "level": 1},
    {"label": "Gas Transportation Cost", "id": "COGS_TRANS", "codes": ["5910-001"], "level": 1},
    {"label": "Cylinder Filling Cost", "id": "COGS_FILL", "codes": ["5826-012"], "level": 1},
    {"label": "Cylinder Maintenance", "id": "COGS_MAINT", "codes": ["6120-015"], "level": 1},
    {"label": "TOTAL COGS", "id": "COGS_TOTAL", "isTotal": True, "level": 0},
    
    {"label": "GROSS PROFIT", "id": "GROSS_PROFIT", "isTotal": True, "level": 0},
    
    {"label": "OPERATING EXPENSES", "id": "EXP_HDR", "isHeader": True, "level": 0},
    {"label": "Salaries & Wages", "id": "EXP_SAL", "codes": ["6120-001"], "level": 1},
    {"label": "Employee Benefits (BPJS)", "id": "EXP_BEN", "codes": ["6120-019"], "level": 1},
    {"label": "Office Rent", "id": "EXP_RENT", "codes": ["6120-023"], "level": 1},
    {"label": "Utilities", "id": "EXP_UTIL", "codes": ["6120-007", "6120-008"], "level": 1},
    {"label": "Fuel for Delivery Vehicles", "id": "EXP_FUEL", "codes": ["6110-001"], "level": 1},
    {"label": "Vehicle Maintenance", "id": "EXP_VMAINT", "codes": ["6110-003"], "level": 1},
    {"label": "Marketing Expenses", "id": "EXP_MKT", "codes": ["6120-002", "6120-003"], "level": 1},
    {"label": "Other Expenses", "id": "EXP_OTHER", "codes": ["6110", "6120", "6200"], "level": 1}, # Catch-all
    {"label": "TOTAL OPERATING EXPENSES", "id": "EXP_TOTAL", "isTotal": True, "level": 0},
    
    {"label": "OPERATING PROFIT", "id": "OPER_PROFIT", "isTotal": True, "level": 0},
    
    {"label": "OTHER INCOME / EXPENSES", "id": "OTHER_HDR", "isHeader": True, "level": 0},
    {"label": "Bank Interest Income", "id": "OTH_INT", "codes": ["7000-001"], "level": 1},
    {"label": "Forex Gain / Loss", "id": "OTH_FX", "codes": ["7000-002", "6200-002"], "level": 1},
    {"label": "NET PROFIT", "id": "NET_PROFIT", "isTotal": True, "level": 0}
]

BS_CATEGORIES = [
    {"label": "ASSETS", "id": "ASSETS_HDR", "isHeader": True, "level": 0},
    {"label": "Cash on Hand", "id": "AST_CASH", "codes": ["1110"], "level": 1},
    {"label": "Cash in Bank", "id": "AST_BANK", "codes": ["1120"], "level": 1},
    {"label": "Accounts Receivable", "id": "AST_AR", "codes": ["1130"], "level": 1},
    {"label": "Inventories", "id": "AST_INV", "codes": ["1150", "1160", "1170", "1180"], "level": 1},
    {"label": "Fixed Assets", "id": "AST_FIXED", "codes": ["1500"], "level": 1},
    {"label": "TOTAL ASSETS", "id": "AST_TOTAL", "isTotal": True, "level": 0},
    
    {"label": "LIABILITIES", "id": "LIAB_HDR", "isHeader": True, "level": 0},
    {"label": "Accounts Payable", "id": "LIAB_AP", "codes": ["2110"], "level": 1},
    {"label": "Bank Loans", "id": "LIAB_LOAN", "codes": ["2160"], "level": 1},
    {"label": "Accrued Expenses", "id": "LIAB_ACCR", "codes": ["2130"], "level": 1},
    {"label": "TOTAL LIABILITIES", "id": "LIAB_TOTAL", "isTotal": True, "level": 0},
    
    {"label": "EQUITY", "id": "EQUITY_HDR", "isHeader": True, "level": 0},
    {"label": "Capital", "id": "EQT_CAP", "codes": ["3110"], "level": 1},
    {"label": "Retained Earnings", "id": "EQT_RE", "codes": ["3120"], "level": 1},
    {"label": "TOTAL EQUITY", "id": "EQT_TOTAL", "isTotal": True, "level": 0},
]

# --------------------------------------------------
# 1. NEW SCHEMA FOR AR BOOK REQUEST
# --------------------------------------------------
class ARBookRequest(BaseModel):
    org_id: int
    branch_id: int
    customer_id: int 
    from_date: Optional[date] = None
    to_date: Optional[date] = None

class APLedgerRequest(BaseModel):
    supplier_id: int = 0
    currency_id: int = 0
    from_date: Optional[str] = None
    to_date: Optional[str] = None

# --------------------------------------------------
# 2. DB HELPER (SYNC) FOR REPORTING
# --------------------------------------------------
def get_db_connection_sync():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=DB_NAME_FINANCE,
        ssl_disabled=True 
    )

# --------------------------------------------------
# 3. CALLING STORED PROCEDURE
# --------------------------------------------------
# --------------------------------------------------
# SHARED AR BOOK QUERY via SP
# --------------------------------------------------
def call_ar_book_sp(org_id, branch_id, customer_id, from_date, to_date):
    """Calls proc_AR_GetARBook and returns the result rows."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)

        cursor.callproc('proc_AR_GetARBook', [
            org_id, branch_id, 
            customer_id if customer_id else 0,
            from_date if from_date else None,
            to_date if to_date else None
        ])
        
        result_rows = []
        for result in cursor.stored_results():
            result_rows = result.fetchall()

        for row in result_rows:
            if row.get('ledger_date'):
                row['ledger_date'] = str(row['ledger_date'])

        return result_rows
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@router.post("/get_ar_book")
def get_ar_book(request: ARBookRequest):
    try:
        result_rows = call_ar_book_sp(
            request.org_id, request.branch_id, 
            request.customer_id, request.from_date, request.to_date
        )
        return {"status": True, "message": "Success", "data": result_rows}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-ap-ledger")
def get_ap_ledger(
    supplier_id: int = 0,
    currency_id: int = 0,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)

        cursor.callproc('proc_AP_AccountsPayableLedger', [
            supplier_id,
            currency_id,
            from_date if from_date else None,
            to_date if to_date else None
        ])
        
        result_rows = []
        for result in cursor.stored_results():
            result_rows = result.fetchall()

        # Format dates for JSON
        for row in result_rows:
            for key in ['po_date', 'grn_date', 'ref_date', 'irn_date', 'claim_date', 'debit_note_date', 'credit_note_date']:
                if row.get(key):
                    row[key] = str(row[key])

        return {"status": True, "message": "Success", "data": result_rows}
    except Exception as e:
        print(f"Error calling proc_AP_AccountsPayableLedger: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --------------------------------------------------
# 4. GET AR BOOK COMPATIBILITY ENDPOINT
# --------------------------------------------------
@router.get("/getARBook")
def get_ar_book_get(
    orgid: int = 1,
    branchid: int = 1,
    customer_id: int = 0,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None
):
    try:
        result_rows = call_ar_book_sp(orgid, branchid, customer_id, from_date, to_date)
        return {"status": True, "message": "Success", "data": result_rows}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
# 5. GET CUSTOMER ADDRESS FOR SOA
# --------------------------------------------------
@router.get("/getCustomerAddress")
def get_customer_address(customer_id: int):
    conn = None
    cursor = None
    conn = None
    cursor = None
    try:
        conn = get_db_connection_sync()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('proc_AR_GetCustomerAddress', [customer_id])
        row = None
        for result in cursor.stored_results():
            row = result.fetchone()
        return {"status": True, "data": row or {}}
    except Exception as e:
        print(f"Error fetching customer address: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --------------------------------------------------
# CREATE AR RECEIPT
# --------------------------------------------------
@router.post("/create")
async def create_ar_receipt(
    command: schemas.CreateARCommand,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        new_receipts = await crud.create_ar_receipt(db, command)
        return {
            "status": "success",
            "message": "Receipt(s) created successfully",
            "data": new_receipts
        }
    except Exception as e:
        print(f"Error creating AR receipt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# GET ALL PENDING RECEIPTS
# --------------------------------------------------
@router.get("/get-pending-list")
async def get_pending_list(
    user_id: Optional[int] = None, 
    department: Optional[str] = None, 
    db: AsyncSession = Depends(database.get_db)
):
    try:
        # Base WHERE clause
        # Entries that are EITHER:
        # 1. Pending Verification (Marketing Stage)
        # 2. Verified but NOT yet Submitted/Posted (Finance Stage)
        where_clause = """
            WHERE r.is_active = 1 
              AND (IFNULL(r.bank_amount, 0) != 0 OR IFNULL(r.cash_amount, 0) != 0)
              AND (
                  r.pending_verification = 1 
                  OR (r.pending_verification = 0 AND r.is_submitted = 0 AND r.is_posted = 1)
              )
        """
        query_params = {}

        # LOGIC: If Department is '9' (Sales), filter by sales_person_id
        if department == '9' and user_id is not None:
            where_clause += " AND r.sales_person_id = :user_id"
            query_params["user_id"] = user_id

        query = text("CALL proc_AR_GetPendingList(:department, :user_id)")
        result = await db.execute(query, {
            "department": department or '',
            "user_id": user_id or 0
        })
        results = result.mappings().all()
        
        return {
            "status": "success",
            "count": len(results),
            "data": results
        }
    except Exception as e:
        print(f"Error fetching pending list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# VERIFY RECEIPT
# --------------------------------------------------
@router.put("/verify/{receipt_id}")
async def verify_receipt(
    receipt_id: int,
    data: schemas.VerifyCustomerUpdate,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        updated = await crud.update_customer_and_verify(
            db, receipt_id, data
        )

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Receipt not found OR already verified."
            )

        return {
            "status": "success",
            "message": "Verification posted successfully.",
            "data": updated
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
# POST RECEIPT (Final Finance Stage)
# --------------------------------------------------
@router.put("/post/{receipt_id}")
async def post_receipt(
    receipt_id: int,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        from sqlalchemy import update, select
        from ..models.finance import ARReceipt

        stmt = (
            update(ARReceipt)
            .where(ARReceipt.receipt_id == receipt_id)
            .values(is_submitted=True, pending_verification=False)
        )
        result = await db.execute(stmt)

        # 🟢 SYNCHRONIZE POSTING FOR LINKED RECEIPT
        select_stmt = select(ARReceipt.linked_receipt_id).where(ARReceipt.receipt_id == receipt_id)
        linked_res = await db.execute(select_stmt)
        linked_id = linked_res.scalar_one_or_none()
        
        if linked_id:
            linked_stmt = (
                update(ARReceipt)
                .where(ARReceipt.receipt_id == linked_id)
                .values(is_submitted=True, pending_verification=False)
            )
            await db.execute(linked_stmt)

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Receipt not found")

        return {"status": "success", "message": "Receipt posted to books successfully."}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
# SAVE DRAFT
# --------------------------------------------------
@router.put("/save-draft/{receipt_id}")
async def save_draft(
    receipt_id: int,
    data: schemas.SaveDraftRequest,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        saved_record = await crud.save_verification_draft(db, receipt_id, data)
        
        if not saved_record:
            raise HTTPException(status_code=404, detail="Receipt not found")

        return {
            "status": "success",
            "message": "Draft saved successfully",
            "data": saved_record
        }
    except Exception as e:
        print(f"Error saving draft: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
# GET OUTSTANDING INVOICES
# --------------------------------------------------
@router.get("/get-outstanding-invoices/{customer_id}")
async def get_outstanding_invoices(
    customer_id: int, 
    receipt_id: Optional[int] = None, 
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    only_allocated: bool = False,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        rid_val = receipt_id if receipt_id else 0
        fdate_val = from_date if from_date else None
        tdate_val = to_date if to_date else None
        
        # 🟢 REVERTED: Call SP with original 4 parameters to avoid breaking other callers (like SOA)
        query = text("CALL proc_AR_GetOutstandingInvoices(:cust_id, :rid, :fdate, :tdate)")
        result = await db.execute(query, {
            "cust_id": customer_id, 
            "rid": rid_val,
            "fdate": fdate_val,
            "tdate": tdate_val
        })
        invoices = result.mappings().all()
        
        processed_invoices = []
        for inv in invoices:
             item = dict(inv)
             allocated = float(item.get("allocated_here", 0))
             
             # 🟢 New: Filter in Python if only_allocated is requested
             if only_allocated and allocated <= 0:
                 continue

             item["is_pre_selected"] = True if allocated > 0 else False
             processed_invoices.append(item)
             
        return {"status": "success", "data": processed_invoices}

    except Exception as e:
        print(f"Error fetching outstanding invoices: {e}")
        return {"status": "error", "detail": str(e)}

# --------------------------------------------------
# UPDATE REFERENCE ENDPOINTS
# --------------------------------------------------
@router.put("/update-reference")
async def update_reference_endpoint(
    payload: schemas.UpdateReferenceRequest,
    db: AsyncSession = Depends(database.get_db)
):
    success = await crud.update_invoice_reference(db, payload.id, payload.new_reference)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update reference. ID might not exist.")
        
    return {"status": "success", "message": "Reference updated successfully"}


@router.put("/bulk-update-reference")
async def bulk_update_reference(
    payload: schemas.BulkUpdateReferenceRequest,
    db: AsyncSession = Depends(database.get_db)
):
    updated_count = await crud.bulk_update_ar_reference(db, payload.ids, payload.new_reference)
    
    if updated_count == -1:
        raise HTTPException(status_code=500, detail="Database error occurred.")
    
    if updated_count == 0:
        raise HTTPException(status_code=404, detail=f"No records found for IDs: {payload.ids}")
        
    return {
        "status": "success", 
        "message": f"Successfully updated {updated_count} records."
    }

# --------------------------------------------------
# POST INVOICE TO AR
# --------------------------------------------------
@router.post("/post-invoice")
async def post_invoice_endpoint(
    payload: schemas.PostInvoiceToARRequest,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        success = await crud.post_invoice_to_ar(db, payload)
        if success:
            return {"status": "success", "message": "Invoice posted to AR successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to post invoice: Database operation returned false.")
    except Exception as e:
        print(f"ERROR in post_invoice_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}")


# --------------------------------------------------
# CREATE BOOK ENTRIES FROM CLAIM PAYMENTS
# --------------------------------------------------
class ClaimPaymentEntry(BaseModel):
    claim_id: int
    claim_no: str = ""
    amount: float
    payment_mode_id: int          # 1 = Cash, else Bank Transfer
    bank_id: Optional[int] = None
    payment_date: Optional[str] = None
    supplier_id: Optional[int] = 0
    supplier_name: Optional[str] = ""
    applicant_name: Optional[str] = ""
    currency_code: Optional[str] = "IDR"

class CreateFromClaimRequest(BaseModel):
    entries: List[ClaimPaymentEntry]
    user_id: int = 1
    org_id: int = 1
    branch_id: int = 1

@router.post("/create-from-claim")
async def create_book_entries_from_claim(
    payload: CreateFromClaimRequest,
    db: AsyncSession = Depends(database.get_db)
):
    """
    Called after PPP voucher generation.
    Creates CashBook or BankBook payment entries from approved claims.
    - ModeOfPaymentId == 1  → CashBook (cash_amount, deposit_bank_id='0')
    - ModeOfPaymentId != 1  → BankBook (bank_amount, deposit_bank_id=bank_id)
    Entries are auto-posted (no verification needed for outgoing payments).
    """
    try:
        from ..models.finance import ARReceipt
        from sqlalchemy import select

        created_ids = []

        # --- Look up currency IDs for all unique currency codes ---
        unique_codes = set(e.currency_code for e in payload.entries if e.currency_code)
        currency_map = {}  # code -> CurrencyId
        if unique_codes:
            placeholders = ", ".join(f":cc{i}" for i in range(len(unique_codes)))
            cur_params = {f"cc{i}": code for i, code in enumerate(unique_codes)}
            cur_result = await db.execute(text("CALL proc_AR_GetCurrencyIds()"))
            for row in cur_result.mappings().all():
                currency_map[row["CurrencyCode"]] = row["CurrencyId"]

        for entry in payload.entries:
            # 1 = Cash mode. If Cash, it must always route to Cash Book, even if a Bank was selected in the UI.
            is_cash = entry.payment_mode_id == 1
            
            cash_amt = -abs(entry.amount) if is_cash else 0
            bank_amt = 0 if is_cash else -abs(entry.amount)
            ref_no = f"{entry.claim_no} - {entry.supplier_name or entry.applicant_name}".strip(" -")

            # Check for exactly identical existing record to avoid duplication
            check_query = select(ARReceipt).where(
                ARReceipt.reference_no == ref_no,
                ARReceipt.cash_amount == cash_amt,
                ARReceipt.bank_amount == bank_amt
            )
            existing_record = (await db.execute(check_query)).scalars().first()
            
            if existing_record:
                # Skip duplicate insertion
                continue

            # Resolve currency ID from the code sent by frontend
            resolved_currency_id = currency_map.get(entry.currency_code) if entry.currency_code else None

            db_receipt = ARReceipt(
                orgid=payload.org_id,
                branchid=payload.branch_id,
                created_by=str(payload.user_id),
                created_ip="127.0.0.1",

                receipt_date=entry.payment_date,
                customer_id=entry.supplier_id or 0,
                currencyid=resolved_currency_id,

                cash_amount=cash_amt,
                bank_amount=bank_amt,
                bank_charges=0,
                deposit_bank_id=str(entry.bank_id or 0),
                reference_no=ref_no,

                is_posted=True,
                pending_verification=False,
                is_submitted=True,
                send_notification=False,
                flag=False,
                is_cleared=False,
                is_active=True,
            )
            db.add(db_receipt)
            created_ids.append(entry.claim_id)

        await db.commit()

        return {
            "status": "success",
            "message": f"Created {len(created_ids)} book entries from claims",
            "claim_ids": created_ids
        }

    except Exception as e:
        await db.rollback()
        print(f"❌ Create from claim error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
# PROFIT AND LOSS REPORT (OPTION C - DETAILED AGGREGATION)
# --------------------------------------------------
@router.get("/profit-and-loss")
async def get_profit_and_loss(
    from_date: str = None,
    to_date: str = None,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        from app.database import DB_NAME_USER_NEW, DB_NAME_PURCHASE, DB_NAME_MASTER
        if not from_date:
            from_date = f"{date.today().year}-01-01"
        if not to_date:
            to_date = date.today().strftime("%Y-%m-%d")

        report_data = []

        # 1. Consolidated Revenue (SP)
        rev_res = await db.execute(text("CALL proc_PL_GetRevenue(:from_date, :to_date)"), {"from_date": from_date, "to_date": to_date})
        total_revenue = float(rev_res.scalar() or 0)
        
        report_data.append({"id": "HDR_REV", "accountCode": "4000", "accountName": "REVENUE", "amount": 0, "isHeader": True, "indentLevel": 0})
        if total_revenue > 0:
            report_data.append({
                "id": "REV_MAIN",
                "accountCode": "4000-000",
                "accountName": "Sales",
                "amount": total_revenue,
                "isHeader": False,
                "indentLevel": 1
            })

        # 2. Consolidated Purchase History / COGS (SP)
        pur_res = await db.execute(text("CALL proc_PL_GetCOGS(:from_date, :to_date)"), {"from_date": from_date, "to_date": to_date})
        total_cogs = float(pur_res.scalar() or 0)

        report_data.append({"id": "HDR_PUR", "accountCode": "5000", "accountName": "PURCHASES / COGS", "amount": 0, "isHeader": True, "indentLevel": 0})
        if total_cogs > 0:
            report_data.append({
                "id": "PUR_MAIN",
                "accountCode": "5000-000",
                "accountName": "Purchases / COGS",
                "amount": total_cogs,
                "isHeader": False,
                "indentLevel": 1
            })

        # 3. Detailed Expenses (By Claim Category) (SP)
        exp_res = await db.execute(text("CALL proc_PL_GetExpenses(:from_date, :to_date)"), {"from_date": from_date, "to_date": to_date})
        expense_rows = exp_res.mappings().all()

        total_expense = 0
        report_data.append({"id": "HDR_EXP", "accountCode": "6000", "accountName": "OPERATING EXPENSES", "amount": 0, "isHeader": True, "indentLevel": 0})
        for idx, row in enumerate(expense_rows):
            amt = float(row['total'])
            total_expense += amt
            report_data.append({
                "id": f"EXP_{idx}",
                "accountCode": f"6000-{idx+1:03}",
                "accountName": row['claimcategory'],
                "amount": amt,
                "isHeader": False,
                "indentLevel": 1
            })

        # Summary Row
        report_data.append({
            "id": "NP_TOT",
            "accountCode": "",
            "accountName": "NET PROFIT / LOSS",
            "amount": total_revenue - total_cogs - total_expense,
            "isHeader": False,
            "isTotal": True,
            "indentLevel": 0
        })

        return {"status": True, "message": "Success", "data": report_data}
    except Exception as e:
        print(f"Detailed P&L Error: {e}")
        return {"status": "error", "message": str(e)}

# --------------------------------------------------
# BALANCE SHEET REPORT (OPTION C - DETAILED AGGREGATION)
# --------------------------------------------------
@router.get("/balance-sheet")
async def get_balance_sheet(
    as_of_date: str = None,
    db: AsyncSession = Depends(database.get_db)
):
    try:
        from app.database import DB_NAME_USER_NEW, DB_NAME_PURCHASE, DB_NAME_MASTER
        if not as_of_date:
            as_of_date = date.today().strftime("%Y-%m-%d")

        report_data = []

        # --- ASSETS SECTION ---
        report_data.append({"id": "HDR_ASSETS", "accountCode": "1000", "accountName": "ASSETS", "amount": 0, "isHeader": True, "indentLevel": 0})
        
        # 1. Cash & Bank Breakdown (SP)
        bank_res = await db.execute(text("CALL proc_BS_GetBankBalances(:as_of_date)"), {"as_of_date": as_of_date})
        bank_rows = bank_res.mappings().all()
        # Need a second call for cash since SP returns separate result
        cash_res = await db.execute(text("CALL proc_BS_GetCashBalance(:as_of_date)"), {"as_of_date": as_of_date})
        
        total_cash_bank = 0
        # Add Banks
        for idx, row in enumerate(bank_rows):
            amt = float(row['total'])
            total_cash_bank += amt
            
            b_name = row['bank_name']
            if not b_name or str(b_name).strip().lower() in ['none', 'null', '']:
                display_name = "Bank"
            else:
                display_name = f"Bank - {b_name}"
                
            report_data.append({
                "id": f"BANK_{idx}",
                "accountCode": f"1010-{idx:02}",
                "accountName": display_name,
                "amount": amt,
                "indentLevel": 1
            })
        # Add Cash
        cash_amt = float(cash_res.scalar() or 0)
        total_cash_bank += cash_amt
        if cash_amt != 0:
            report_data.append({
                "id": "CASH_MAIN",
                "accountCode": "1001",
                "accountName": "Cash on Hand",
                "amount": cash_amt,
                "indentLevel": 1
            })

        # 2. Consolidated Accounts Receivable (SP)
        ar_res = await db.execute(text("CALL proc_BS_GetARBalance(:as_of_date)"), {"as_of_date": as_of_date})
        total_ar = float(ar_res.scalar() or 0)
        
        if total_ar > 0:
            report_data.append({
                "id": "AR_MAIN",
                "accountCode": "1130-000",
                "accountName": "Accounts Receivable",
                "amount": total_ar,
                "indentLevel": 1
            })

        # --- LIABILITIES SECTION ---
        report_data.append({"id": "HDR_LIAB", "accountCode": "2000", "accountName": "LIABILITIES", "amount": 0, "isHeader": True, "indentLevel": 0})
        
        # 3. Consolidated Accounts Payable (SP)
        ap_res = await db.execute(text("CALL proc_BS_GetAPBalance(:as_of_date)"), {"as_of_date": as_of_date})
        total_ap = float(ap_res.scalar() or 0)
        
        if total_ap > 0:
            report_data.append({
                "id": "AP_MAIN",
                "accountCode": "2100-000",
                "accountName": "Accounts Payable",
                "amount": total_ap,
                "indentLevel": 1
            })

        # 4. Accrued Expenses (Unpaid Claims) (SP)
        claim_res = await db.execute(text("CALL proc_BS_GetAccruedExpenses(:as_of_date)"), {"as_of_date": as_of_date})
        accrued_exp = float(claim_res.scalar() or 0)
        if accrued_exp != 0:
            report_data.append({
                "id": "ACCRUED_EXP",
                "accountCode": "2110",
                "accountName": "Accrued Expenses (Pending Claims)",
                "amount": accrued_exp,
                "indentLevel": 1
            })

        # --- EQUITY & VALIDATION ---
        report_data.append({
            "id": "BS_VAL",
            "accountCode": "CHECK",
            "accountName": "EQUITY (Net Assets)",
            "amount": (total_cash_bank + total_ar) - (total_ap + accrued_exp),
            "isHeader": False,
            "isTotal": True,
            "indentLevel": 0,
            "isValidation": True,
            "isValid": True
        })

        return {"status": "success", "data": report_data}
    except Exception as e:
        print(f"Detailed Balance Sheet Error: {e}")
        return {"status": "error", "message": str(e)}

# --------------------------------------------------
# NEW COMPARATIVE REPORTS
# --------------------------------------------------

@router.get("/reports/comparative-p-and-l")
async def get_comparative_p_and_l(year: int, db: AsyncSession = Depends(database.get_db)):
    try:
        # 1. Fetch data via Stored Procedure (SP)
        res = await db.execute(text("CALL proc_PL_Comparative(:year)"), {"year": year})
        db_data = res.mappings().all()

        
        # 2. Pivot the data into a usable format
        pivoted = {}
        for row in db_data:
            code = row['gl_code']
            m = row['month_num']
            val = float(row['balance'])
            if code not in pivoted: pivoted[code] = {i: 0.0 for i in range(1, 13)}
            pivoted[code][m] = val
            
        # 3. Categorize and build report data
        report_data = []
        used_gl_codes = set()
        
        # Pass 1: Specific categories
        for cat in PL_CATEGORIES:
            row = {"id": cat["id"], "accountName": cat["label"], "isHeader": cat.get("isHeader", False), "isTotal": cat.get("isTotal", False), "level": cat["level"]}
            for i in range(1, 13):
                row[f"month_{i}"] = 0.0
                if "codes" in cat and cat["id"] != "EXP_OTHER":
                    for gl_code in pivoted:
                        if any(gl_code.startswith(prefix) for prefix in cat["codes"]):
                            row[f"month_{i}"] += pivoted[gl_code][i]
                            if i == 1: used_gl_codes.add(gl_code)
            report_data.append(row)

        # Pass 2: Catch-all Other Expenses
        other_exp_row = next((r for r in report_data if r["id"] == "EXP_OTHER"), None)
        if other_exp_row:
            cat_config = next(c for c in PL_CATEGORIES if c["id"] == "EXP_OTHER")
            for i in range(1, 13):
                for gl_code in pivoted:
                    if gl_code not in used_gl_codes:
                        if any(gl_code.startswith(prefix) for prefix in cat_config["codes"]):
                            other_exp_row[f"month_{i}"] += pivoted[gl_code][i]
            
        # 4. Calculate Totals
        def get_row(rid): return next((r for r in report_data if r["id"] == rid), None)
        
        # Total Revenue
        total_rev = get_row("REV_TOTAL")
        for m in range(1, 13):
            total_rev[f"month_{m}"] = sum(r[f"month_{m}"] for r in report_data if r["id"].startswith("REV_") and r["level"] == 1)

        # Total COGS
        total_cogs = get_row("COGS_TOTAL")
        for m in range(1, 13):
            total_cogs[f"month_{m}"] = sum(r[f"month_{m}"] for r in report_data if r["id"].startswith("COGS_") and r["level"] == 1)

        # Gross Profit (Revenue - COGS) - Note: Revenue is usually credit (negative in this SUM logic), so subtract
        # Actually in P&L, we usually take Revenue as Positive for display.
        # My balance is (debit - credit). Revenue (credit) will be negative.
        # So display_val = -balance
        
        for r in report_data:
            if r["id"].startswith("REV_"):
                for m in range(1, 13): r[f"month_{m}"] = -r[f"month_{m}"]
        
        # Now Revenue is positive. COGS (debit) is positive.
        gross_profit = get_row("GROSS_PROFIT")
        for m in range(1, 13):
            gross_profit[f"month_{m}"] = total_rev[f"month_{m}"] - total_cogs[f"month_{m}"]

        # Operating Expenses
        total_exp = get_row("EXP_TOTAL")
        for m in range(1, 13):
            total_exp[f"month_{m}"] = sum(r[f"month_{m}"] for r in report_data if r["id"].startswith("EXP_") and r["level"] == 1)

        # Operating Profit
        oper_profit = get_row("OPER_PROFIT")
        for m in range(1, 13):
            oper_profit[f"month_{m}"] = gross_profit[f"month_{m}"] - total_exp[f"month_{m}"]

        # Net Profit
        net_profit = get_row("NET_PROFIT")
        for m in range(1, 13):
            other_inc = -sum(r[f"month_{m}"] for r in report_data if r["id"].startswith("OTH_") and r["level"] == 1)
            net_profit[f"month_{m}"] = oper_profit[f"month_{m}"] + other_inc

        return {"status": "success", "data": report_data}
    except Exception as e:
        print(f"Error Comparative P&L: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/reports/comparative-balance-sheet")
async def get_comparative_balance_sheet(years: str, db: AsyncSession = Depends(database.get_db)):
    try:
        year_list = sorted([int(y) for y in years.split(",")], reverse=True)
        report_data = []
        for cat in BS_CATEGORIES:
            row = {"id": cat["id"], "accountName": cat["label"], "isHeader": cat.get("isHeader", False), "isTotal": cat.get("isTotal", False), "level": cat["level"]}
            for y in year_list: row[f"year_{y}"] = 0.0
            report_data.append(row)

        for y in year_list:
            # Fetch data via Stored Procedure (SP)
            res = await db.execute(text("CALL proc_BS_Comparative(:year)"), {"year": y})
            year_balances = {row['gl_code']: float(row['balance']) for row in res.mappings().all()}

            for row in report_data:
                field = f"year_{y}"
                cat = next(c for c in BS_CATEGORIES if c["id"] == row["id"])
                if "codes" in cat:
                    for gl_code, balance in year_balances.items():
                        if any(gl_code.startswith(prefix) for prefix in cat["codes"]):
                            if cat["id"].startswith("AST"):
                                row[field] += balance
                            else:
                                row[field] -= balance

        # Calculate Totals & Reconciliation
        def get_row_bs(rid): return next((r for r in report_data if r["id"] == rid), None)
        total_assets = get_row_bs("AST_TOTAL")
        total_liab = get_row_bs("LIAB_TOTAL")
        total_equity = get_row_bs("EQT_TOTAL")
        cap_row = get_row_bs("EQT_CAP")
        re_row = get_row_bs("EQT_RE")

        for y in year_list:
            field = f"year_{y}"
            total_assets[field] = sum(r[field] for r in report_data if r["id"].startswith("AST_") and r["level"] == 1)
            total_liab[field] = sum(r[field] for r in report_data if r["id"].startswith("LIAB_") and r["level"] == 1)
            
            # Reconciliation
            net_assets = total_assets[field] - total_liab[field]
            current_re = re_row[field]
            if cap_row[field] == 0:
                cap_row[field] = net_assets - current_re
            total_equity[field] = cap_row[field] + current_re

        return {"status": "success", "data": report_data}
    except Exception as e:
        print(f"Error Comparative Balance Sheet: {e}")
        return {"status": "error", "message": str(e)}