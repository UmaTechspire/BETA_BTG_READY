from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession 
from sqlalchemy import text, select, update
from datetime import date
from typing import List, Optional, Union
from pydantic import BaseModel
from .. import schemas
from .. import crud 
from ..database import get_db, DB_NAME_USER, DB_NAME_FINANCE, DB_NAME_MASTER, DB_NAME_OLD, DB_NAME_USER_NEW
from ..models.finance import ARReceipt

# Distinct prefix for Cash Book to avoid conflict with Bank Book
router = APIRouter(
    prefix="/AR/cash", 
    tags=["Cash Book Entry"]
)

# --- Pydantic Schemas ---
class CashReceiptItem(BaseModel):
    receipt_id: int = 0
    customer_id: int
    cash_amount: float
    receipt_date: Optional[str] = None
    reference_no: Optional[str] = None
    sales_person_id: Optional[int] = None
    send_notification: bool = False
    transaction_type: str = "Receipt"
    bank_amount: float = 0
    deposit_bank_id: Union[int, str] = 0
    linked_claim_id: Optional[int] = None
    currencyid: Optional[int] = None
    status: str 
    is_posted: bool = False

class CreateCashReceiptRequest(BaseModel):
    orgId: int
    branchId: int
    userId: int
    userIp: str = "127.0.0.1"
    header: List[CashReceiptItem]

class CancelClaimPayload(BaseModel):
    remark: str

# ==========================================
# 1. LISTING & REPORTING (CASH SPECIFIC)
# ==========================================

@router.get("/get-daily-entries")
async def get_daily_cash_entries(db: AsyncSession = Depends(get_db)):
    """
    Fetches entries for the Cash Book Entry screen.
    Includes both saved and posted (submitted) entries to ensure they stay in the grid.
    """
    try:
        # Replacement for proc_Cash_GetDailyEntries to remove the is_submitted=0 filter
        sql = text(f"""
            SELECT 
                r.receipt_id,
                r.transaction_type,
                r.currencyid,
                r.ar_id,
                COALESCE(r.receipt_date, r.created_date) as date,
                r.customer_id,
                CASE 
                    WHEN LOWER(r.transaction_type) = 'cash deposit' THEN 'Cash Deposit'
                    WHEN r.cash_amount < 0 AND r.customer_id != 0 THEN COALESCE(s.SupplierName, 'Unknown Supplier')
                    WHEN r.reference_no LIKE 'PC%' AND r.reference_no LIKE '% | %' THEN SUBSTRING_INDEX(r.reference_no, ' | ', -1)
                    WHEN r.reference_no LIKE 'CLM%' AND r.reference_no LIKE '% - %' THEN SUBSTRING_INDEX(r.reference_no, ' - ', -1)
                    ELSE COALESCE(c.CustomerName, 'Unknown Customer')
                END as customerName,
                r.cash_amount,
                r.deposit_bank_id,
                CASE 
                    WHEN r.reference_no LIKE 'PC%' AND r.reference_no LIKE '% | %' THEN SUBSTRING_INDEX(r.reference_no, ' | ', 1)
                    ELSE r.reference_no 
                END as reference_no,
                r.sales_person_id,
                r.send_notification,
                r.is_posted, 
                r.pending_verification, 
                r.is_submitted,
                r.is_combined,
                r.combine_group_id,
                r.custom_voucher_no,
                tfc.Purpose as purpose,
                mcc.claimcategory as claimCategory,
                CASE WHEN r.is_posted = 1 THEN 'P' ELSE 'S' END as status_code,
                CASE 
                    WHEN r.is_posted = 1 AND r.pending_verification = 1 THEN 'Pending'
                    WHEN r.is_posted = 1 AND r.pending_verification = 0 THEN 'Completed'
                    ELSE NULL 
                END as verification_status
            FROM {DB_NAME_FINANCE}.tbl_ar_receipt r
            LEFT JOIN {DB_NAME_USER}.master_customer c ON r.customer_id = c.Id
            LEFT JOIN {DB_NAME_MASTER}.master_supplier s ON r.customer_id = s.SupplierId
            LEFT JOIN (
                SELECT Claim_ID, GROUP_CONCAT(DISTINCT Purpose SEPARATOR ', ') as Purpose
                FROM {DB_NAME_FINANCE}.tbl_claimAndpayment_Details
                WHERE IsActive = 1
                GROUP BY Claim_ID
            ) tfc ON r.ar_id = tfc.Claim_ID
            LEFT JOIN {DB_NAME_FINANCE}.tbl_claimAndpayment_header h ON r.ar_id = h.Claim_ID AND LOWER(r.transaction_type) NOT IN ('receipt', 'customer receipt')
            LEFT JOIN {DB_NAME_FINANCE}.master_claimcategory mcc ON h.ClaimCategoryId = mcc.Id
            WHERE r.cash_amount != 0
              AND r.is_active = 1
            ORDER BY r.receipt_id DESC
            LIMIT 1000
        """)
        result = await db.execute(sql)
        data = result.mappings().all()
        return {"status": "success", "data": data}
        
    except Exception as e:
        print(f"Error in get_daily_cash_entries: {e}")
        return {"status": "error", "detail": str(e)}


@router.get("/get-cash-claims")
async def get_cash_claims(claim_category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Returns CEO-approved claims with Cash mode of payment for linking in manual Cash Book entries.
    Claim categories: 'Cash', 'Cash Advance', 'Supplier Payment'
    Display format: '{ApplicationNo} - {ApplicantName}'
    """
    try:
        from ..database import DB_NAME_FINANCE
        
        category_filter = ""
        params = {}
        
        if claim_category:
            category_filter = "AND mc.claimcategory = :category"
            params["category"] = claim_category

        sql = text(f"""
            SELECT 
                h.Claim_ID        as claim_id,
                h.ApplicationNo   as claim_no,
                COALESCE(h.SupplierId, 0) as supplier_id,
                COALESCE(h.ApplicantId, 0) as applicant_id,
                COALESCE(
                    TRIM(CONCAT(COALESCE(u.FirstName,''), ' ', COALESCE(u.LastName,''))),
                    CAST(h.CreatedBy AS CHAR),
                    h.Remarks,
                    h.ApplicationNo
                )                 as applicant_name,
                h.claimamountintc  as amount,
                h.ApplicationDate as payment_date,
                mc.claimcategory  as claim_category,
                COALESCE(mc2.CurrencyCode, 'IDR') as currency_code,
                mct.ClaimType     as type
            FROM {DB_NAME_FINANCE}.tbl_claimAndpayment_header h
            LEFT JOIN {DB_NAME_FINANCE}.master_claimcategory mc ON h.ClaimCategoryId = mc.Id
            LEFT JOIN {DB_NAME_FINANCE}.tbl_claimAndpayment_Details d ON h.Claim_ID = d.Claim_ID
            LEFT JOIN {DB_NAME_FINANCE}.master_claimtype mct ON d.ClaimTypeId = mct.Id
            LEFT JOIN btggasify_live.master_currency mc2 ON h.TransactionCurrencyId = mc2.CurrencyId
            LEFT JOIN btggasify_live.users u ON h.CreatedBy = u.Id
            INNER JOIN {DB_NAME_FINANCE}.tbl_PaymentSummary_header s ON h.SummaryId = s.SummaryId
            WHERE (h.PPP_PV_Director_approve = 1 OR h.PPP_PV_Commissioner_approveone = 1)
              AND h.IsActive = 1
              AND h.SummaryId > 0
              AND s.PaymentNo >= 'PPP0000041'
              AND NOT EXISTS (
                  SELECT 1 FROM {DB_NAME_FINANCE}.tbl_ar_receipt r 
                  WHERE (
                        (r.ar_id = h.Claim_ID AND LOWER(r.transaction_type) NOT IN ('receipt', 'customer receipt'))
                        OR LOWER(r.reference_no) LIKE CONCAT('%', LOWER(TRIM(h.ApplicationNo)), '%')
                    ) 
                    AND r.is_active = 1
              )
              {category_filter}
            ORDER BY h.Claim_ID DESC
            LIMIT 500
        """)

        result = await db.execute(sql, params)
        rows = result.mappings().all()

        data = [
            {
                "value": row["claim_id"],
                "label": f"{row['claim_no']} - {row['applicant_name']}",
                "claim_no": row["claim_no"],
                "applicant_name": row["applicant_name"],
                "amount": float(row["amount"] or 0),
                "payment_date": str(row["payment_date"]) if row["payment_date"] else None,
                "claim_category": row["claim_category"],
                "currency_code": row["currency_code"],
                "type": row["type"],
                "supplier_id": row["supplier_id"],
                "applicant_id": row["applicant_id"]
            }
            for row in rows
        ]
        return {"status": "success", "data": data}

    except Exception as e:
        print(f"get-cash-claims error: {e}")
        return {"status": "error", "detail": str(e)}

@router.get("/get-report")
async def get_cash_book_report(
    from_date: str,
    to_date: str,
    bank_id: int = 0,
    currency_id: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Cash Book Report. Uses cash_amount for CashIn/CashOut.
    """
    try:
        from datetime import datetime
        
        # Parse UI dates (typically '%d-%b-%Y') to standard MySQL '%Y-%m-%d' for safe string comparison
        try:
            f_date_parsed = datetime.strptime(from_date, '%d-%b-%Y').strftime('%Y-%m-%d')
            t_date_parsed = datetime.strptime(to_date, '%d-%b-%Y').strftime('%Y-%m-%d')
        except ValueError:
            f_date_parsed = from_date
            t_date_parsed = to_date

        sql = "CALL proc_Cash_GetReport(:from_date, :to_date, :bank_id, :currency_id)"
        params = {
            "from_date": f_date_parsed,
            "to_date": t_date_parsed, 
            "bank_id": bank_id if bank_id and bank_id > 0 else 0,
            "currency_id": currency_id if currency_id and currency_id > 0 else 0,
            "f_date_parsed": f_date_parsed,
            "t_date_parsed": t_date_parsed
        }

        result = await db.execute(text(sql), params)
        rows = result.mappings().all()

        # --- FILTER BY DIRECTOR APPROVAL ---
        receipt_ids = [r.get("receipt_id") for r in rows if r.get("receipt_id")]
        if receipt_ids:
            # Join with claims table to check approval status
            approval_sql = text(f"""
                SELECT r.receipt_id 
                FROM {DB_NAME_FINANCE}.tbl_ar_receipt r
                LEFT JOIN {DB_NAME_FINANCE}.tbl_claimAndpayment_header h ON r.ar_id = h.Claim_ID AND LOWER(r.transaction_type) NOT IN ('receipt', 'customer receipt')
                WHERE r.receipt_id IN ({','.join(map(str, receipt_ids))})
                  AND (LOWER(r.transaction_type) IN ('receipt', 'customer receipt') OR r.ar_id = 0 OR r.ar_id IS NULL OR h.PPP_PV_Director_approve = 1)
            """)
            approval_result = await db.execute(approval_sql)
            approved_ids = {row[0] for row in approval_result.all()}
            
            # Keep rows that are NOT claims or are approved claims
            rows = [r for r in rows if (not r.get("receipt_id")) or (r.get("receipt_id") in approved_ids)]
        
        # --- 2. FETCH PPP CASH WITHDRAWS DIRECTLY (WITH APPROVAL VALIDATION) ---
        # NOTE: PPP withdrawals are NOW filtered by approval status to prevent unapproved PPPs from showing
        # Only include PPPs where claims have been approved by the claim module (either via PPP-PV or regular PPP paths)
        # NetCashWithdraw is always in IDR. Skip PPP rows entirely if a non-IDR currency filter is active.
        IDR_CURRENCY_ID = 3
        include_ppp = (currency_id == 0 or currency_id == IDR_CURRENCY_ID)
        
        ppp_rows = []
        if include_ppp:
            ppp_sql = text(f"""
                SELECT 
                    s.PaymentNo as VoucherNo,
                    DATE_FORMAT(s.CreatedDate, '%d-%b-%Y') as Date,
                    s.NetCashWithdraw
                FROM {DB_NAME_FINANCE}.tbl_PaymentSummary_header s
                INNER JOIN {DB_NAME_FINANCE}.tbl_claimAndpayment_header h ON s.SummaryId = h.SummaryId
                WHERE DATE(s.CreatedDate) >= :f_date_parsed AND DATE(s.CreatedDate) <= :t_date_parsed
                  AND s.NetCashWithdraw > 0
                  AND h.IsActive = 1
                  AND COALESCE(h.ppp_IsRejected, 0) = 0
                  AND COALESCE(h.ppp_pv_IsRejected, 0) = 0
                  AND COALESCE(h.finance_cancel, 0) = 0
                GROUP BY s.SummaryId, s.PaymentNo, s.CreatedDate, s.NetCashWithdraw
                HAVING MIN(
                  CASE 
                    -- PPP-PV Approval Path
                    WHEN (COALESCE(h.PPP_PV_Director_approve, 0) = 1 OR COALESCE(h.PPP_PV_Commissioner_approveone, 0) = 1) THEN 1
                    -- Regular PPP Approval Path (GM & Director approved)
                    WHEN (COALESCE(h.ppp_gm_approvalone, 0) = 1 AND COALESCE(h.ppp_director_approvalone, 0) = 1) THEN 1
                    ELSE 0 
                  END
                ) = 1
            """)
            ppp_result = await db.execute(ppp_sql, params)
            ppp_rows = ppp_result.mappings().all()

        combined_data = [dict(r) for r in rows]

        # Process only approved PPP records (already filtered by SQL query above)
        for row in ppp_rows:
            net_withdraw = float(row['NetCashWithdraw'] or 0)
            
            if net_withdraw > 0:
                combined_data.append({
                    "Date": str(row["Date"]),
                    "VoucherNo": row["VoucherNo"],
                    "TransactionType": "Cash withdraw",
                    "Party": "Multiple",
                    "BankName": "-",
                    "Description": f"{row['VoucherNo']} - Net Cash Withdraw",
                    "CashIn": net_withdraw, # Changed to Debit (CashIn)
                    "CashOut": 0.0,
                    "NetAmount": net_withdraw
                })


        # --- 3. SORT BY DATE AND RECALCULATE RUNNING BALANCE ---
        def get_sort_key(item):
            date_str = str(item.get('Date', ''))
            try:
                return datetime.strptime(date_str, '%d-%b-%Y').strftime('%Y-%m-%d')
            except ValueError:
                return date_str
                
        combined_data.sort(key=get_sort_key)

        data = []
        running_balance = 0.0 
        
        # --- 4. INJECT OPENING BALANCE ---
        if f_date_parsed:
            opening_sql = text("CALL proc_Cash_GetOpeningBalance(:currency_id, :from_date)")
            opening_result = await db.execute(opening_sql, {
                "currency_id": int(currency_id) if currency_id else 0,
                "from_date": f_date_parsed
            })
            opening_row = opening_result.mappings().first()

            if opening_row:
                op_item = dict(opening_row)
                op_cash_in = float(op_item.get("CashIn", 0))
                op_cash_out = float(op_item.get("CashOut", 0))
                
                # Calculate brought forward balance
                running_balance = op_cash_in - op_cash_out
                op_item["Balance"] = running_balance
                data.append(op_item)
        
        for item in combined_data:
            cash_in = float(item.get("CashIn", 0))
            cash_out = float(item.get("CashOut", 0))
            running_balance += (cash_in - cash_out)
            
            item["CashIn"] = cash_in
            item["CashOut"] = cash_out
            item["Balance"] = running_balance
            data.append(item)
            
        return {"status": "success", "data": data}

    except Exception as e:
        print(f"Error fetching cash book report: {e}")
        return {"status": "error", "detail": str(e)}

# ==========================================
# 2. TRANSACTIONAL ENDPOINTS (CREATE/UPDATE)
# ==========================================

@router.post("/create")
async def create_cash_receipt(payload: CreateCashReceiptRequest, db: AsyncSession = Depends(get_db)):
    """
    Creates new cash book entries. Writes to cash_amount column 
    instead of bank_amount to differentiate from bankbook entries.
    """
    try:
        created_records = []
        
        for item in payload.header:
            is_posted = item.is_posted
            pending_verification = True if is_posted and item.transaction_type == 'Receipt' else False

            db_receipt = ARReceipt(
                orgid=payload.orgId,
                branchid=payload.branchId,
                created_by=str(payload.userId),
                created_ip=payload.userIp,
                
                receipt_date=item.receipt_date,
                customer_id=item.customer_id,
                
                # KEY DIFFERENCE: Write to cash_amount, leave bank_amount as 0
                cash_amount=item.cash_amount,
                bank_amount=item.bank_amount,
                bank_charges=0,
                deposit_bank_id=str(item.deposit_bank_id),
                
                # Standard fields
                reference_no=item.reference_no,
                transaction_type=item.transaction_type,
                ar_id=item.linked_claim_id,
                currencyid=item.currencyid,
                sales_person_id=item.sales_person_id,
                send_notification=item.send_notification,
                
                # Status flags
                is_posted=is_posted,
                pending_verification=pending_verification if item.transaction_type == 'Receipt' else False,
                is_submitted=True if is_posted and item.transaction_type != 'Receipt' else False,
                
                flag=False,
                is_cleared=False,
                is_active=True,
            )
            db.add(db_receipt)
            created_records.append(db_receipt)

        await db.commit()
        for record in created_records:
            await db.refresh(record)
            
        return {
            "status": "success", 
            "message": f"Created {len(created_records)} cash entries", 
            "ids": [r.receipt_id for r in created_records]
        }
    except Exception as e:
        await db.rollback()
        print(f"Cash Create Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update/{receipt_id}")
async def update_cash_receipt(receipt_id: int, payload: CreateCashReceiptRequest, db: AsyncSession = Depends(get_db)):
    """
    Updates an existing cash book entry. Writes to cash_amount column.
    """
    try:
        data = payload.header[0]
        stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
        result = await db.execute(stmt)
        entry = result.scalars().first()
        
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")

        entry.customer_id = data.customer_id
        entry.deposit_bank_id = str(data.deposit_bank_id) if data.deposit_bank_id else "0"

        if data.receipt_date:
            entry.receipt_date = data.receipt_date 

        # KEY DIFFERENCE: Write to cash_amount
        entry.cash_amount = data.cash_amount
        entry.bank_amount = data.bank_amount
        entry.bank_charges = 0
        
        entry.reference_no = data.reference_no
        entry.transaction_type = data.transaction_type
        if data.linked_claim_id is not None:
            entry.ar_id = data.linked_claim_id
        if data.currencyid is not None:
            entry.currencyid = data.currencyid
        entry.sales_person_id = data.sales_person_id
        entry.send_notification = data.send_notification
        entry.status = data.status
        
        if data.status == "Posted":
            entry.is_posted = True
            is_receipt = (data.transaction_type == 'Receipt')
            entry.pending_verification = is_receipt
            entry.is_submitted = not is_receipt
        else:
            entry.is_posted = False
            entry.is_submitted = False
            
        entry.updated_by = str(payload.userId)
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        await db.rollback()
        return {"status": "error", "detail": str(e)}

@router.put("/submit/{receipt_id}")
async def submit_cash_receipt(receipt_id: int, db: AsyncSession = Depends(get_db)):
    """
    Called when generating Marketing Verification. Sets is_posted=1 and pending_verification=1.
    """
    # 1. Get the current entry to check type
    stmt_sel = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
    res_sel = await db.execute(stmt_sel)
    entry = res_sel.scalars().first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    is_receipt = (entry.transaction_type == 'Receipt')
    
    stmt = (
        update(ARReceipt)
        .where(ARReceipt.receipt_id == receipt_id)
        .values(
            is_posted=True, 
            pending_verification=is_receipt,
            is_submitted=not is_receipt
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "success"}

@router.put("/post/{receipt_id}")
async def finalize_cash_receipt(receipt_id: int, db: AsyncSession = Depends(get_db)):
    """
    Called by Finance to finally POST to the Cash Book report. Sets is_submitted=1.
    If the receipt is part of a combined group, all entries in that group are posted.
    """
    # Fetch the receipt to check for combine_group_id
    stmt_sel = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
    res = await db.execute(stmt_sel)
    receipt = res.scalar_one_or_none()
    
    if not receipt:
        return {"status": "error", "message": "Receipt not found"}

    # 1. Determine target record IDs
    if receipt.combine_group_id:
        stmt_group = select(ARReceipt.receipt_id).where(ARReceipt.combine_group_id == receipt.combine_group_id, ARReceipt.is_active == True)
        res_group = await db.execute(stmt_group)
        ids = [r for r in res_group.scalars().all()]
    else:
        ids = [receipt_id]

    # 2. Finalize each record using the standard business logic
    # This ensures references are updated with linked invoices
    for rid in ids:
        await crud.finalize_receipt_and_update_ref(db, rid)
        
    return {"status": "success"}

@router.put("/cancel-claim/{claim_id}")
async def cancel_claim(claim_id: int, payload: CancelClaimPayload, db: AsyncSession = Depends(get_db)):
    """
    Called by Finance to cancel a Claim from the Cash Book Entry modal.
    """
    try:
        sql = text(f"""
            UPDATE {DB_NAME_FINANCE}.tbl_claimAndpayment_header
            SET finance_cancel = 1, finance_cancel_remarks = :remark
            WHERE Claim_ID = :claim_id
        """)
        await db.execute(sql, {"claim_id": claim_id, "remark": payload.remark})
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        await db.rollback()
        return {"status": "error", "detail": str(e)}

@router.post("/combine-vouchers")
async def combine_cash_vouchers(request: schemas.CombineVouchersRequest, db: AsyncSession = Depends(get_db)):
    """Combines multiple cash entries into one."""
    result = await crud.combine_receipts(db, request)
    if result:
        return {"status": "success", "message": "Vouchers combined successfully", "new_id": result.receipt_id}
    else:
        raise HTTPException(status_code=400, detail="Failed to combine vouchers. Ensure they exist and are active.")