from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession 
from sqlalchemy import text, select, func, and_, or_, update
from datetime import date
from typing import List, Optional
from pydantic import BaseModel
from .. import schemas
from .. import crud 
from ..database import get_db, DB_NAME_USER, DB_NAME_FINANCE, DB_NAME_MASTER, DB_NAME_OLD, DB_NAME_USER_NEW
from ..models.finance import ARReceipt, ARReceiptMessage

router = APIRouter(
    prefix="/AR", 
    tags=["Bank Book Entry"]
)

# --- Pydantic Schemas ---
class ReceiptItem(BaseModel):
    receipt_id: int = 0
    customer_id: int
    bank_amount: float
    bank_charges: float
    deposit_bank_id: int
    receipt_date: Optional[str] = None
    reference_no: Optional[str] = None
    sales_person_id: Optional[int] = None
    send_notification: bool = False
    status: str 
    
    # 🟢 New fields for Cash/Cheque/Via
    cash_amount: float = 0
    bank_payment_via: int = 0
    cheque_number: Optional[str] = None

class CreateReceiptRequest(BaseModel):
    orgId: int
    branchId: int
    userId: int
    userIp: str = "127.0.0.1"
    header: List[ReceiptItem]

# --- API Endpoints ---

@router.get("/get-daily-entries")
async def get_daily_entries(db: AsyncSession = Depends(get_db)):
    try:
        query = text("CALL proc_Bank_GetDailyEntries()")
        result = await db.execute(query)
        raw_data = result.mappings().all()
        
        # Convert to list of dicts for consistency
        final_list = [dict(row) for row in raw_data]
            
        # Sort by date descending, then ID descending
        final_list.sort(key=lambda x: (str(x.get('date', '')), int(x.get('receipt_id', 0))), reverse=True)
        
        return {"status": "success", "data": final_list}
        
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# --- UPDATED ENDPOINT: BANK BOOK REPORT ---
@router.get("/get-report")
async def get_bank_book_report(
    from_date: str,
    to_date: str,
    bank_id: int = 0,
    db: AsyncSession = Depends(get_db)
):
    try:
        data = []
        running_balance = 0.0

        def clean_date(d_str):
            if not d_str: return None
            # Extract YYYY-MM-DD from '2026-01-31T18:30:00.000Z', '2026-01-31 00:00:00', or '2026-01-31'
            return d_str.split('T')[0].split(' ')[0]

        from_date_clean = clean_date(from_date)
        to_date_clean = clean_date(to_date)

        # 1. FETCH OPENING BALANCE
        if bank_id and str(bank_id) != '0' and from_date_clean:
            opening_sql = text("CALL proc_Bank_GetOpeningBalance(:bank_id, :from_date)")
            opening_result = await db.execute(opening_sql, {
                "bank_id": int(bank_id), 
                "from_date": from_date_clean
            })
            opening_row = opening_result.mappings().first()

            if opening_row:
                op_item = dict(opening_row)
                op_debit = float(op_item["DebitOut"] or 0)
                running_balance = op_debit
                
                op_item["CreditIn"] = 0.0
                op_item["DebitOut"] = op_debit
                # Ensure balance is correct
                op_item["Balance"] = running_balance
                data.append(op_item)

        # 1b. FETCH OVERDRAFT LIMIT
        overdraft_limit = 0.0
        if bank_id and bank_id != 0:
            overdraft_sql = text("CALL proc_Bank_GetOverdraftLimit(:bank_id)")
            overdraft_result = await db.execute(overdraft_sql, {"bank_id": bank_id})
            overdraft_row = overdraft_result.mappings().first()
            if overdraft_row:
                overdraft_limit = float(overdraft_row["OverdraftLimit"])

        if data:
            data[0]["OverdraftLimit"] = overdraft_limit
            data[0]["OverDraft"] = overdraft_limit - running_balance

        # 2. FETCH TRANSACTIONS
        # Start from the 1st of the month for calculation continuity
        try:
            dt_from = date.fromisoformat(from_date_clean)
            from_date_for_sql = str(dt_from.replace(day=1))
        except:
            from_date_for_sql = from_date_clean

        sql = text("CALL proc_Bank_GetReportTransactions(:from_date, :to_date, :bank_id)")

        params = {
            "from_date": from_date_for_sql, 
            "to_date": to_date_clean, 
            "bank_id": int(bank_id) 
        }

        result = await db.execute(sql, params)
        raw_rows = result.mappings().all()
        
        # --- FILTER PAYMENT-TYPE CLAIMS BY DIRECTOR APPROVAL ---
        # Receipt entries (money IN to bank) should always show once posted.
        # Only Payment-type entries linked to a Claim need the Director approval gate.
        receipt_ids = [r.get("receipt_id") for r in raw_rows if r.get("receipt_id")]
        if receipt_ids:
            approval_sql = text(f"""
                SELECT r.receipt_id 
                FROM {DB_NAME_FINANCE}.tbl_ar_receipt r
                LEFT JOIN {DB_NAME_FINANCE}.tbl_claimAndpayment_header h ON r.ar_id = h.Claim_ID AND LOWER(r.transaction_type) NOT IN ('receipt', 'customer receipt')
                WHERE r.receipt_id IN ({','.join(map(str, receipt_ids))})
                  AND (
                      LOWER(r.transaction_type) IN ('receipt', 'customer receipt')  -- Receipts always show (no Director gate)
                      OR r.ar_id = 0 OR r.ar_id IS NULL  -- Non-claim payments always show
                      OR h.PPP_PV_Director_approve = 1    -- Claim payments need Director approval
                  )
            """)
            approval_result = await db.execute(approval_sql)
            approved_ids = {row[0] for row in approval_result.all()}
            
            raw_rows = [r for r in raw_rows if (not r.get("receipt_id")) or (r.get("receipt_id") in approved_ids)]

        # --- MAP ALL TRANSACTIONS (INCLUDING CLAIMS) ---
        all_items = []
        for i, row in enumerate(raw_rows):
            item = dict(row)
            # Add GroupedClaims as a single item list for potential UI usage (e.g. popups)
            item["GroupedClaims"] = [{
                "VoucherNo": item["VoucherNo"],
                "Amount": float(item["NetAmount"] or 0),
                "receipt_id": item["receipt_id"],
                "InvoiceNo": item["AllocatedInvoices"] or item.get("Description", ""),
                "pending_verification": item.get("pending_verification", 1),
                "transactionType": item["TransactionType"]
            }]
            item["_order"] = i
            all_items.append(item)

        # Final sort by date and original order
        all_items.sort(key=lambda x: (str(x.get("Date", "")), x.get("_order", 0)))
        
        # Calculate running balance on the final sorted list
        for item in all_items:
            credit_val = float(item.get("CreditIn", 0))
            debit_val = float(item.get("DebitOut", 0))
            running_balance += (debit_val - credit_val)
            item["Balance"] = running_balance
            item["OverdraftLimit"] = overdraft_limit
            item["OverDraft"] = overdraft_limit - running_balance
            item.pop("_order", None)
            data.append(item)
            
        return {"status": "success", "data": data}

    except Exception as e:
        print(f"Error fetching bank book report: {e}")
        return {"status": "error", "detail": str(e)}

# --- 🟢 UPDATED ENDPOINT: GET SUPPLIER FILTER ---
@router.get("/get-supplier-filter")
async def get_supplier_filter(db: AsyncSession = Depends(get_db)):
    try:
        # 🟢 FIX: Use SupplierId column & DB_NAME_MASTER
        query = text("CALL proc_Bank_GetSupplierFilter()")
        result = await db.execute(query)
        data = result.mappings().all()
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# --- NEW ENDPOINT: VERIFY RECEIPT ---
@router.put("/verify/{receipt_id}")
async def verify_receipt(
    receipt_id: int, 
    payload: schemas.VerifyCustomerUpdate, 
    db: AsyncSession = Depends(get_db)
):
    try:
        record = await crud.update_customer_and_verify(db, receipt_id, payload)
        if not record:
            raise HTTPException(status_code=404, detail="Receipt not found or not in pending state")
        return {"status": "success", "message": "Verification finalized"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.put("/submit/{receipt_id}")
async def submit_receipt(receipt_id: int, db: AsyncSession = Depends(get_db)):
    """
    Sets is_posted=True and pending_verification=True.
    If receipt_id is part of a group, updates the WHOLE group.
    """
    # 1. Find the target record
    stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
    result = await db.execute(stmt)
    entry = result.scalars().first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Receipt not found")

    # 2. Determine target records (single or group)
    if entry.combine_group_id:
        stmt_group = select(ARReceipt).where(ARReceipt.combine_group_id == entry.combine_group_id, ARReceipt.is_active == True)
        res_group = await db.execute(stmt_group)
        targets = res_group.scalars().all()
    else:
        targets = [entry]

    # 3. Apply updates
    for item in targets:
        is_receipt = (item.transaction_type == 'Receipt')
        item.is_posted = True
        item.pending_verification = is_receipt
        item.is_submitted = not is_receipt # Straight to bankbook if not a receipt

    await db.commit()
    return {"status": "success"}

@router.put("/post/{receipt_id}")
async def finalize_receipt(receipt_id: int, db: AsyncSession = Depends(get_db)):
    """
    Final Finance POST. If part of a group, posts all members.
    """
    # 1. Find the target record
    stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
    result = await db.execute(stmt)
    entry = result.scalars().first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Receipt not found")

    # 2. Determine target records
    if entry.combine_group_id:
        stmt_group = select(ARReceipt).where(ARReceipt.combine_group_id == entry.combine_group_id, ARReceipt.is_active == True)
        res_group = await db.execute(stmt_group)
        ids = [r.receipt_id for r in res_group.scalars().all()]
    else:
        ids = [receipt_id]

    # 3. Finalize all
    for rid in ids:
        await crud.finalize_receipt_and_update_ref(db, rid)
            
    return {"status": "success"}

@router.get("/get-by-id")
async def get_by_id(receipt_id: int, db: AsyncSession = Depends(get_db)):
    sql = text(f"""
        SELECT 
            r.*,
            CASE 
                WHEN LOWER(r.transaction_type) = 'bank transfer' THEN COALESCE(b2.BankName, '-')
                ELSE COALESCE(c.CustomerName, s.SupplierName, '-')
            END as customer_name,
            COALESCE(b.BankName, '-') as bank_name,
            COALESCE(mc.CurrencyCode, 'IDR') as CurrencyCode
        FROM {DB_NAME_FINANCE}.tbl_ar_receipt r
        LEFT JOIN {DB_NAME_USER}.master_customer c ON r.customer_id = c.Id
        LEFT JOIN {DB_NAME_MASTER}.master_supplier s ON r.customer_id = s.SupplierId
        LEFT JOIN {DB_NAME_MASTER}.master_bank b ON CAST(NULLIF(r.deposit_bank_id, '') AS UNSIGNED) = b.BankId
        LEFT JOIN {DB_NAME_MASTER}.master_bank b2 ON CAST(NULLIF(r.customer_id, '') AS UNSIGNED) = b2.BankId
        LEFT JOIN {DB_NAME_USER}.master_currency mc ON COALESCE(r.currencyid, b.CurrencyId) = mc.CurrencyId
        WHERE r.receipt_id = :receipt_id
    """)
    result = await db.execute(sql, {"receipt_id": receipt_id})
    row = result.mappings().first()
    
    if not row:
        return {"status": "error", "detail": "Not Found"}
    return {"status": "success", "data": dict(row)}

@router.post("/create")
async def create_receipt(payload: schemas.CreateARCommand, db: AsyncSession = Depends(get_db)):
    try:
        new_records = await crud.create_ar_receipt(db, payload)
        
        if new_records:
            return {"status": "success", "message": f"Created {len(new_records)} entries", "ids": [r.receipt_id for r in new_records]}
        else:
            raise HTTPException(status_code=400, detail="Failed to create receipt")

    except Exception as e:
        print(f"Create Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update/{receipt_id}")
async def update_receipt(receipt_id: int, payload: CreateReceiptRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = payload.header[0]
        
        stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
        result = await db.execute(stmt)
        entry = result.scalars().first()
        
        if not entry:
            raise HTTPException(status_code=404, detail="Receipt not found")

        entry.customer_id = data.customer_id
        entry.deposit_bank_id = str(data.deposit_bank_id)
        
        is_cleared_status = False
        if data.deposit_bank_id and str(data.deposit_bank_id) != "0" and str(data.deposit_bank_id).strip() != "":
            is_cleared_status = True
            
        entry.flag = is_cleared_status
        entry.is_cleared = is_cleared_status

        if data.receipt_date:
            entry.receipt_date = data.receipt_date 

        entry.bank_amount = data.bank_amount
        entry.bank_charges = data.bank_charges
        entry.reference_no = data.reference_no
        entry.sales_person_id = data.sales_person_id
        entry.send_notification = data.send_notification
        entry.cash_amount = data.cash_amount
        entry.bank_payment_via = data.bank_payment_via
        entry.cheque_number = data.cheque_number
        # NOTE: is_posted, pending_verification, and is_submitted are intentionally
        # NOT updated here — those are controlled exclusively by submit/post endpoints.
        entry.updated_by = str(payload.userId)

        await db.commit()
        return {"status": "success"}

    except Exception as e:
        await db.rollback()
        return {"status": "error", "detail": str(e)}

@router.get("/get-sales-persons")
async def get_sales_persons(db: AsyncSession = Depends(get_db)):
    try:
        query = text("CALL proc_Bank_GetSalesPersons()")
        
        result = await db.execute(query)
        sales_persons = result.mappings().all()
        
        return {"status": "success", "data": sales_persons}

    except Exception as e:
        print(f"Error fetching sales persons: {e}")
        return {"status": "error", "detail": str(e)}

@router.get("/get-customer-defaults")
async def get_customer_defaults(db: AsyncSession = Depends(get_db)):
    try:
        query = text("CALL proc_Bank_GetCustomerDefaults()")
        
        result = await db.execute(query)
        rows = result.mappings().all()
        
        defaults = {}
        for row in rows:
            customer_id = int(row['Id'])
            sales_person_id = int(row['SalesPersonId']) if row['SalesPersonId'] else None
            if sales_person_id is not None:
                defaults[customer_id] = sales_person_id
        
        return {"status": "success", "data": defaults}

    except Exception as e:
        print(f"❌ Error fetching customer defaults: {e}")
        return {"status": "error", "detail": str(e)}


# --- NEW ENDPOINT: SYNC CLAIM TO AP ---
@router.post("/sync-claim-to-ap/{claim_id}")
async def sync_claim_to_ap(
    claim_id: int, 
    user_id: int, 
    db: AsyncSession = Depends(get_db)
):
    """
    Calls the stored procedure to sync a validated Claim into the 
    Accounts Payable (AP) table.
    """
    try:
        # 1. Optional: Verify if the claim exists and is posted before syncing
        # This prevents accidental syncing of 'Saved' but 'Not Posted' claims
        check_query = text("CALL proc_Bank_GetClaimSubmissionStatus(:cid)")
        check_result = await db.execute(check_query, {"cid": claim_id})
        claim = check_result.mappings().first()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim record not found")
        
        if claim['IsSubmitted'] == 0:
            return {
                "status": "warning", 
                "message": "Only 'Posted' claims can be synced to Accounts Payable."
            }

        # 2. Call the Stored Procedure
        # Note: We use db.execute with text() for calling procedures in SQLAlchemy Async
        sync_query = text("CALL proc_sync_ClaimToAP(:cid, :uid)")
        await db.execute(sync_query, {"cid": claim_id, "uid": user_id})
        
        # 3. Commit the transaction
        await db.commit()

        return {
            "status": "success", 
            "message": f"Claim {claim_id} successfully synced to Accounts Payable."
        }

    except Exception as e:
        await db.rollback()
        print(f"❌ Sync Error: {e}")
        return {"status": "error", "detail": str(e)}

@router.post("/combine-vouchers")
async def combine_vouchers(request: schemas.CombineVouchersRequest, db: AsyncSession = Depends(get_db)):
    """Combines multiple receipts into one and transfers allocations."""
    result = await crud.combine_receipts(db, request)
    if result:
        return {"status": "success", "message": "Vouchers combined successfully", "new_id": result.receipt_id}
    else:
        raise HTTPException(status_code=400, detail="Failed to combine vouchers. Ensure they exist and are active.")

@router.get("/get-all-active-banks")
async def get_all_active_banks(db: AsyncSession = Depends(get_db)):
    sql = text("SELECT BankId as value, BankName as label FROM btggasify_masterpanel_live.master_bank WHERE IsActive = 1")
    result = await db.execute(sql)
    return {"status": "success", "data": result.mappings().all()}

@router.get("/get-messages/{receipt_id}")
async def get_messages(receipt_id: int, role: str = None, db: AsyncSession = Depends(get_db)):
    try:
        if role:
            # Mark messages from the OTHER role as read
            opposite_role = 'Finance' if role == 'Marketing' else 'Marketing'
            upd_stmt = update(ARReceiptMessage).where(
                ARReceiptMessage.receipt_id == receipt_id,
                ARReceiptMessage.sender_role == opposite_role,
                ARReceiptMessage.is_read == False
            ).values(is_read=True)
            await db.execute(upd_stmt)
            await db.commit()

        stmt = select(ARReceiptMessage).where(ARReceiptMessage.receipt_id == receipt_id).order_by(ARReceiptMessage.created_at.asc())
        result = await db.execute(stmt)
        messages = result.scalars().all()
        return {"status": "success", "data": messages}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/send-message")
async def send_message(payload: schemas.ARMessage, db: AsyncSession = Depends(get_db)):
    try:
        new_msg = ARReceiptMessage(
            receipt_id=payload.receipt_id,
            sender_role=payload.sender_role,
            message_text=payload.message_text
        )
        db.add(new_msg)
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        await db.rollback()
        return {"status": "error", "detail": str(e)}

@router.delete("/delete/{receipt_id}")
async def delete_receipt(receipt_id: int, db: AsyncSession = Depends(get_db)):
    """
    Permanently deletes a bank book entry from the database.
    Only allowed when the entry is in 'MP' (pending verification) state.
    """
    try:
        stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
        result = await db.execute(stmt)
        entry = result.scalars().first()

        if not entry:
            raise HTTPException(status_code=404, detail="Receipt not found")

        # Only allow deletion when entry is posted and pending verification (MP state)
        if not entry.is_posted or not entry.pending_verification:
            raise HTTPException(
                status_code=400,
                detail="Only entries in 'MP' (pending verification) state can be deleted."
            )

        # Hard delete: permanently remove the row from the database
        await db.delete(entry)
        await db.commit()

        return {"status": "success", "message": f"Receipt {receipt_id} deleted successfully."}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        return {"status": "error", "detail": str(e)}