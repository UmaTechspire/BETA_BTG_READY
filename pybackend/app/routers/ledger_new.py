from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel
from ..database import get_db, engine, DB_NAME_USER, DB_NAME_USER_NEW, DB_NAME_FINANCE
from ..models import ledger as models
import os

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

# -----------------------------------------------------------------------------
# LOOKUP ENDPOINTS (existing)
# -----------------------------------------------------------------------------

@router.get("/get-gl-codes")
async def get_gl_codes():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_Ledger_GetGLCodes()")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {
                "status": "success",
                "data": [dict(row._mapping) for row in rows]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-sl-codes")
async def get_sl_codes():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_Ledger_GetSLCodes()")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {
                "status": "success",
                "data": [dict(row._mapping) for row in rows]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-currencies")
async def get_currencies():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_Ledger_GetCurrencies()")
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
                q_sales = text("CALL proc_Ledger_GetSalesInvoices(:from_date, :to_date)")
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
                    # Cr Sales
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Sales Invoice",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Sales",
                        "debit": 0.0,
                        "credit": amount,
                        "narration": ref
                    })

            # ---------------------------------------------------------------
            # 2. CUSTOMER PAYMENTS — Dr Bank/Cash, Cr Customer
            #    Source: tbl_ar_receipt + tbl_receipt_ag_ar + tbl_accounts_receivable
            # ---------------------------------------------------------------
            if not category or category == "Customer Payment":
                q_payment = text("CALL proc_Ledger_GetCustomerPayments(:from_date, :to_date)")
                result = await conn.execute(q_payment, {"from_date": from_date, "to_date": to_date})
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
                    pay_mode = r["pay_mode"]

                    # Dr Bank / Cash
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Customer Payment",
                        "reference_no": ref,
                        "party": party_name,
                        "description": f"Dr {pay_mode}",
                        "debit": amount,
                        "credit": 0.0,
                        "narration": f"Customer Payment, {ref}"
                    })
                    # Cr Customer
                    all_rows.append({
                        "transaction_date": txn_date,
                        "category": "Customer Payment",
                        "reference_no": ref,
                        "party": party_name,
                        "description": "Cr Customer",
                        "debit": 0.0,
                        "credit": amount,
                        "narration": f"Customer Payment, {ref}"
                    })

            # ---------------------------------------------------------------
            # 3. CREDIT NOTES — Dr Sales Return, Cr Customer
            #    Source: Credit_Notes
            # ---------------------------------------------------------------
            if not category or category == "Credit Note":
                q_cn = text("CALL proc_Ledger_GetCreditNotes(:from_date, :to_date)")
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

            # ---------------------------------------------------------------
            # 4. DEBIT NOTES — Dr Customer, Cr Adjustment
            #    Source: Debit_Notes
            # ---------------------------------------------------------------
            if not category or category == "Debit Note":
                q_dn = text("CALL proc_Ledger_GetDebitNotes(:from_date, :to_date)")
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

            # ---------------------------------------------------------------
            # 5. JOURNAL ENTRIES — from tbl_ledgerbook (manual entries)
            # ---------------------------------------------------------------
            if not category or category == "Journal Entry":
                try:
                    q_je = text("CALL proc_Ledger_GetJournalEntries(:from_date, :to_date)")
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