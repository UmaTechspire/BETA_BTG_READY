from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel
from ..database import get_db, engine, DB_NAME_USER, DB_NAME_USER_NEW, DB_NAME_FINANCE, DB_NAME_MASTER
from ..models import ledger as models

router = APIRouter(
    prefix="/ledger",
    tags=["Ledger Book"]
)

# -----------------------------------------------------------------------------
# SCHEMAS
# -----------------------------------------------------------------------------

class LedgerReportRow(BaseModel):
    transaction_date: Optional[str] = None
    category: Optional[str] = None
    reference_no: Optional[str] = None
    party: Optional[str] = None
    description: Optional[str] = None
    debit: float = 0.0
    credit: float = 0.0
    narration: Optional[str] = None

class LedgerBase(BaseModel):
    gl_id: Optional[int] = None
    reference_no: Optional[str] = None
    category: Optional[str] = None
    party_id: Optional[int] = None
    currency_id: Optional[int] = None
    debit: Optional[float] = 0.0
    credit: Optional[float] = 0.0
    narration: Optional[str] = None
    org_id: Optional[int] = 1
    branch_id: Optional[int] = 1
    created_by: Optional[str] = None
    modified_by: Optional[str] = None

class LedgerCreate(LedgerBase):
    pass

class LedgerUpdate(LedgerBase):
    party: Optional[str] = None
    exchange_rate: Optional[float] = 1.0

class LedgerResponse(LedgerBase):
    party: Optional[str] = None
    exchange_rate: Optional[float] = 1.0
    ledger_id: int
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# LOOKUP ENDPOINTS
# -----------------------------------------------------------------------------

@router.get("/get-gl-codes")
async def get_gl_codes(db: AsyncSession = Depends(get_db)):
    try:
        # Assuming tbl_GLcodemaster is in the default finance database
        query = text("SELECT * FROM tbl_GLcodemaster")
        result = await db.execute(query)
        gl_codes = result.mappings().all()
        return {
            "status": "success",
            "data": gl_codes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-currencies")
async def get_currencies(db: AsyncSession = Depends(get_db)):
    try:
        # master_currency is typically in the user DB (btggasify_live) based on finance.py
        
        query = text(f"SELECT * FROM {DB_NAME_USER}.master_currency")
        result = await db.execute(query)
        currencies = result.mappings().all()
        return {
            "status": "success",
            "data": currencies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-sl-codes")
async def get_sl_codes():
    try:
        async with engine.connect() as conn:
            query = text(f"SELECT sl_code_id, sl_code, sl_name, gl_code_id FROM {DB_NAME_FINANCE}.tbl_sl_codes")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {
                "status": "success",
                "data": [dict(row._mapping) for row in rows]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# LEDGER REPORT — Unified query across source tables
# -----------------------------------------------------------------------------

@router.get("/report")
async def get_ledger_report(
    from_date: str = Query(..., description="Start date YYYY-MM-DD"),
    to_date: str = Query(..., description="End date YYYY-MM-DD"),
    category: Optional[str] = Query(None, description="Filter by category: Sales Invoice, Customer Payment, Credit Note, Debit Note"),
    party: Optional[str] = Query(None, description="Filter by party name (partial match)")
):
    """
    Returns unified Dr/Cr rows by querying source tables directly.
    Each transaction produces 2+ rows (debit line + credit line).
    """
    try:
        async with engine.connect() as conn:
            all_rows = []

            # ---------------------------------------------------------------
            # 1. SALES INVOICES — Dr Customer (AR), Cr Sales
            #    Source: tbl_salesinvoices_header + master_customer
            # ---------------------------------------------------------------
            if not category or category == "Sales Invoice":
                q_sales = text(f"""
                    SELECT 
                        DATE_FORMAT(h.Salesinvoicesdate, '%Y-%m-%d') AS txn_date,
                        h.salesinvoicenbr AS ref_no,
                        COALESCE(c.CustomerName, 'Unknown') AS party_name,
                        h.TotalAmount AS amount,
                        COALESCE(h.CalculatedPrice, h.TotalAmount) AS amount_idr
                    FROM {DB_NAME_USER}.tbl_salesinvoices_header h
                    LEFT JOIN {DB_NAME_USER}.master_customer c ON h.customerid = c.Id
                    WHERE h.isactive = 1 
                      AND h.IsSubmitted = 1
                      AND h.Salesinvoicesdate BETWEEN :from_date AND :to_date
                    ORDER BY h.Salesinvoicesdate ASC
                """)
                result = await conn.execute(q_sales, {"from_date": from_date, "to_date": to_date})
                for row in result.fetchall():
                    r = dict(row._mapping)
                    amount = float(r["amount"] or 0)
                    if amount == 0:
                        continue

                    party_name = r["party_name"]
                    # Apply party filter
                    if party and party.lower() not in party_name.lower():
                        continue

                    ref = r["ref_no"] or ""
                    txn_date = r["txn_date"]

                    # Dr Customer (Accounts Receivable)
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Sales Invoice",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Dr Customer (AR)",
                        "debit": amount,
                        "credit": 0.0,
                        "narration": ref
                    })

                    # Calculate GST (Assuming 11% inclusive based on common IDR logic, user didn't specify exactly)
                    # We will split amount into sales_amount + gst_amount where total = amount.
                    gst_amount = amount * 0.11 / 1.11
                    sales_amount = amount - gst_amount

                    # Cr Output GST
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Sales Invoice",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Output GST",
                        "debit": 0.0,
                        "credit": gst_amount,
                        "narration": ref
                    })

                    # Cr Sales
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Sales Invoice",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Sales",
                        "debit": 0.0,
                        "credit": sales_amount,
                        "narration": ref
                    })

            # ---------------------------------------------------------------
            # 2. RECEIPTS & PAYMENTS (from tbl_ar_receipt)
            #    Includes: Customer Payments (Pos), Purchase Payments (Neg), Claim Payments (Neg)
            # ---------------------------------------------------------------
            if not category or category in ["Customer Payment", "Purchase Payment", "Claim Payment"]:
                q_payment = text(f"""
                    SELECT 
                        DATE_FORMAT(r.receipt_date, '%Y-%m-%d') AS txn_date,
                        COALESCE(r.reference_no, CONCAT('REC-', r.receipt_id)) AS ref_no,
                        COALESCE(c.CustomerName, 'Unknown') AS party_name,
                        -- Use raw amount from ar_receipt directly to see negatives
                        (IFNULL(r.cash_amount, 0) + IFNULL(r.bank_amount, 0)) AS amount,
                        CASE 
                            WHEN IFNULL(r.bank_amount, 0) != 0 THEN 'Bank'
                            ELSE 'Cash'
                        END AS pay_mode
                    FROM {DB_NAME_FINANCE}.tbl_ar_receipt r
                    LEFT JOIN {DB_NAME_USER}.master_customer c ON r.customer_id = c.Id
                    WHERE r.receipt_date BETWEEN :from_date AND :to_date
                      AND r.is_active = 1
                    ORDER BY r.receipt_date ASC
                """)
                result = await conn.execute(q_payment, {"from_date": from_date, "to_date": to_date})
                for row in result.fetchall():
                    r = dict(row._mapping)
                    raw_amount = float(r["amount"] or 0)
                    if raw_amount == 0:
                        continue
                        
                    is_payment_out = (raw_amount < 0)
                    abs_amount = abs(raw_amount)

                    party_name = r["party_name"]
                    if party and party.lower() not in party_name.lower():
                        continue

                    ref = r["ref_no"] or ""
                    txn_date = r["txn_date"]
                    pay_mode = r["pay_mode"]

                    if not is_payment_out:
                        # --- CUSTOMER PAYMENT (Incoming) ---
                        if category and category != "Customer Payment":
                            continue
                            
                        # Dr Bank / Cash
                        all_rows.append({
                            "transaction_date": txn_date,
                            "category": "Customer Payment",
                            "reference_no": ref,
                            "party": party_name,
                            "description": f"Dr {pay_mode}",
                            "debit": abs_amount,
                            "credit": 0.0,
                            "narration": f"Purchase Payment, {ref}" # User specifically requested this narration
                        })
                        # Cr Customer
                        all_rows.append({
                            "transaction_date": txn_date,
                            "category": "Customer Payment",
                            "reference_no": ref,
                            "party": party_name,
                            "description": "Cr Customer",
                            "debit": 0.0,
                            "credit": abs_amount,
                            "narration": f"Purchase Payment, {ref}"
                        })
                    else:
                        # --- OUTGOING PAYMENT (Purchase or Claim) ---
                        is_claim = ref.startswith("SPC-")
                        cat_label = "Claim Payment" if is_claim else "Purchase Payment"
                        
                        if category and category != cat_label:
                            continue
                            
                        # Dr Supplier
                        all_rows.append({
                            "transaction_date": txn_date,
                            "category": cat_label,
                            "reference_no": ref,
                            "party": party_name,
                            "description": "Dr Supplier",
                            "debit": abs_amount,
                            "credit": 0.0,
                            "narration": ref
                        })
                        # Cr Bank / Cash
                        all_rows.append({
                            "transaction_date": txn_date,
                            "category": cat_label,
                            "reference_no": ref,
                            "party": party_name,
                            "description": f"Cr {pay_mode}",
                            "debit": 0.0,
                            "credit": abs_amount,
                            "narration": ref
                        })

            # ---------------------------------------------------------------
            # 3. CREDIT NOTES — Dr Sales Return, Cr Customer
            #    Source: Credit_Notes
            # ---------------------------------------------------------------
            if not category or category == "Credit Note":
                # --- Customer Credit Notes ---
                q_cn = text(f"""
                    SELECT 
                        DATE_FORMAT(cn.TransactionDate, '%Y-%m-%d') AS txn_date,
                        cn.CreditNoteNumber AS ref_no,
                        COALESCE(c.CustomerName, 'Unknown') AS party_name,
                        cn.Amount AS amount
                    FROM {DB_NAME_FINANCE}.Credit_Notes cn
                    LEFT JOIN {DB_NAME_USER}.master_customer c ON cn.CustomerId = c.Id
                    WHERE cn.IsSubmitted = 1
                      AND cn.CustomerId > 0
                      AND cn.TransactionDate BETWEEN :from_date AND :to_date
                    ORDER BY cn.TransactionDate ASC
                """)
                result = await conn.execute(q_cn, {"from_date": from_date, "to_date": to_date})
                for row in result.fetchall():
                    r = dict(row._mapping)
                    amount = float(r["amount"] or 0)
                    if amount == 0:
                        continue

                    party_name = r["party_name"]
                    if party and party.lower() not in party_name.lower():
                        continue

                    ref = r["ref_no"] or ""
                    txn_date = r["txn_date"]

                    # Dr Sales Return
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Credit Note",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Dr Sales Return",
                        "debit": amount,
                        "credit": 0.0,
                        "narration": ref
                    })
                    # Cr Customer
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Credit Note",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Customer",
                        "debit": 0.0,
                        "credit": amount,
                        "narration": ref
                    })

                # --- Supplier Credit Notes ---
                q_supplier_cn = text(f"""
                    SELECT 
                        DATE_FORMAT(cn.TransactionDate, '%Y-%m-%d') AS txn_date,
                        cn.CreditNoteNumber AS ref_no,
                        COALESCE(s.SupplierName, 'Unknown') AS party_name,
                        cn.Amount AS amount
                    FROM {DB_NAME_FINANCE}.Credit_Notes cn
                    LEFT JOIN {DB_NAME_MASTER}.master_supplier s ON cn.SupplierId = s.SupplierId
                    WHERE cn.IsSubmitted = 1
                      AND cn.SupplierId > 0
                      AND cn.TransactionDate BETWEEN :from_date AND :to_date
                    ORDER BY cn.TransactionDate ASC
                """)
                result = await conn.execute(q_supplier_cn, {"from_date": from_date, "to_date": to_date})
                for row in result.fetchall():
                    r = dict(row._mapping)
                    amount = float(r["amount"] or 0)
                    if amount == 0:
                        continue

                    party_name = r["party_name"]
                    if party and party.lower() not in party_name.lower():
                        continue

                    ref = r["ref_no"] or ""
                    txn_date = r["txn_date"]

                    # Cr Supplier (AP)
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Credit Note",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Supplier (AP)",
                        "debit": 0.0,
                        "credit": amount,
                        "narration": ref
                    })

            # ---------------------------------------------------------------
            # 4. DEBIT NOTES — Dr Customer, Cr Adjustment
            #    Source: Debit_Notes
            # ---------------------------------------------------------------
            if not category or category == "Debit Note":
                # --- Customer Debit Notes ---
                q_dn = text(f"""
                    SELECT 
                        DATE_FORMAT(dn.TransactionDate, '%Y-%m-%d') AS txn_date,
                        dn.DebitNoteNumber AS ref_no,
                        COALESCE(c.CustomerName, 'Unknown') AS party_name,
                        dn.Amount AS amount
                    FROM {DB_NAME_FINANCE}.Debit_Notes dn
                    LEFT JOIN {DB_NAME_USER}.master_customer c ON dn.CustomerId = c.Id
                    WHERE dn.IsSubmitted = 1
                      AND dn.CustomerId > 0
                      AND dn.TransactionDate BETWEEN :from_date AND :to_date
                    ORDER BY dn.TransactionDate ASC
                """)
                result = await conn.execute(q_dn, {"from_date": from_date, "to_date": to_date})
                for row in result.fetchall():
                    r = dict(row._mapping)
                    amount = float(r["amount"] or 0)
                    if amount == 0:
                        continue

                    party_name = r["party_name"]
                    if party and party.lower() not in party_name.lower():
                        continue

                    ref = r["ref_no"] or ""
                    txn_date = r["txn_date"]

                    # Dr Customer
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Debit Note",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Dr Customer",
                        "debit": amount,
                        "credit": 0.0,
                        "narration": ref
                    })
                    # Cr Adjustment
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Debit Note",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Adjustment",
                        "debit": 0.0,
                        "credit": amount,
                        "narration": ref
                    })

                # --- Supplier Debit Notes ---
                q_supplier_dn = text(f"""
                    SELECT 
                        DATE_FORMAT(dn.TransactionDate, '%Y-%m-%d') AS txn_date,
                        dn.DebitNoteNumber AS ref_no,
                        COALESCE(s.SupplierName, 'Unknown') AS party_name,
                        dn.Amount AS amount
                    FROM {DB_NAME_FINANCE}.Debit_Notes dn
                    LEFT JOIN {DB_NAME_MASTER}.master_supplier s ON dn.SupplierId = s.SupplierId
                    WHERE dn.IsSubmitted = 1
                      AND dn.SupplierId > 0
                      AND dn.TransactionDate BETWEEN :from_date AND :to_date
                    ORDER BY dn.TransactionDate ASC
                """)
                result = await conn.execute(q_supplier_dn, {"from_date": from_date, "to_date": to_date})
                for row in result.fetchall():
                    r = dict(row._mapping)
                    amount = float(r["amount"] or 0)
                    if amount == 0:
                        continue

                    party_name = r["party_name"]
                    if party and party.lower() not in party_name.lower():
                        continue

                    ref = r["ref_no"] or ""
                    txn_date = r["txn_date"]

                    # Dr Supplier (AP)
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Debit Note",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Dr Supplier (AP)",
                        "debit": amount,
                        "credit": 0.0,
                        "narration": ref
                    })

            # ---------------------------------------------------------------
            # 5. JOURNAL ENTRIES — from tbl_ledgerbook (manual entries)
            # ---------------------------------------------------------------
            if not category or category == "Journal Entry":
                try:
                    q_je = text(f"""
                        SELECT 
                            DATE_FORMAT(lb.created_at, '%Y-%m-%d') AS txn_date,
                            lb.reference_no AS ref_no,
                            COALESCE(lb.party, '') AS party_name,
                            lb.debit,
                            lb.credit,
                            lb.narration,
                            lb.category AS description
                        FROM {DB_NAME_FINANCE}.tbl_ledgerbook lb
                        WHERE lb.created_at BETWEEN :from_date AND :to_date
                        ORDER BY lb.created_at ASC
                    """)
                    result = await conn.execute(q_je, {"from_date": from_date, "to_date": to_date})
                    for row in result.fetchall():
                        r = dict(row._mapping)
                        party_name = r["party_name"] or ""
                        if party and party.lower() not in party_name.lower():
                            continue

                        all_rows.append({
                            "transaction_date": r["txn_date"],
                            "category": "Journal Entry",
                            "reference_no": r["ref_no"] or "",
                            "party": party_name,
                            "description": r["description"] or "Journal Entry",
                            "debit": float(r["debit"] or 0),
                            "credit": float(r["credit"] or 0),
                            "narration": r["narration"] or ""
                        })
                except Exception:
                    # tbl_ledgerbook may not exist yet — skip silently
                    pass

            # Sort all rows by date
            all_rows.sort(key=lambda x: x["transaction_date"] or "")

            return {
                "status": "success",
                "data": all_rows,
                "total_debit": sum(r["debit"] for r in all_rows),
                "total_credit": sum(r["credit"] for r in all_rows),
                "count": len(all_rows)
            }

    except Exception as e:
        print(f"Ledger report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# CRUD OPERATIONS
# -----------------------------------------------------------------------------

@router.post("/", response_model=LedgerResponse, status_code=status.HTTP_201_CREATED)
async def create_ledger_entry(
    ledger_data: LedgerCreate, 
    db: AsyncSession = Depends(get_db)
):
    try:
        data_dict = ledger_data.dict()
        
        # 1. Determine Party
        computed_party = None
        if ledger_data.party_id == 1:
            computed_party = "Supplier"
        elif ledger_data.party_id == 2:
            computed_party = "Customer"
        data_dict['party'] = computed_party

        # 2. Determine Exchange Rate
        computed_exchange_rate = 1.0
        if ledger_data.currency_id:
            # Assuming 'Rate' or 'ExchangeRate' column in master_currency. 
            # Standardizing on ExchangeRate usually, but if not sure select all or specific.
            # Based on previous pattern, query master_currency.
            query = text(f"SELECT CurrencyId, ExchangeRate FROM {DB_NAME_USER}.master_currency WHERE CurrencyId = :cid")
            result = await db.execute(query, {"cid": ledger_data.currency_id})
            row = result.mappings().one_or_none()
            if row and row.get('ExchangeRate') is not None:
                computed_exchange_rate = float(row['ExchangeRate'])
        
        data_dict['exchange_rate'] = computed_exchange_rate

        new_ledger = models.LedgerBook(**data_dict)
        db.add(new_ledger)
        await db.commit()
        await db.refresh(new_ledger)
        return new_ledger
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[LedgerResponse])
async def get_all_ledgers(
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(models.LedgerBook).offset(skip).limit(limit)
        result = await db.execute(query)
        ledgers = result.scalars().all()
        return ledgers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{ledger_id}", response_model=LedgerResponse)
async def get_ledger(
    ledger_id: int, 
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(models.LedgerBook).where(models.LedgerBook.ledger_id == ledger_id)
        result = await db.execute(query)
        ledger = result.scalar_one_or_none()
        
        if not ledger:
            raise HTTPException(status_code=404, detail="Ledger entry not found")
        
        return ledger
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{ledger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ledger(
    ledger_id: int, 
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(models.LedgerBook).where(models.LedgerBook.ledger_id == ledger_id)
        result = await db.execute(query)
        ledger = result.scalar_one_or_none()
        
        if not ledger:
            raise HTTPException(status_code=404, detail="Ledger entry not found")
            
        await db.delete(ledger)
        await db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))