from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..database import get_db, engine
from ..models.dn_cn import CreditNotes, DebitNotes, CreditInvoice, DebitInvoice
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()
DB_NAME_USER = os.getenv('DB_NAME_USER', 'btggasify_live')
DB_NAME_FINANCE = os.getenv('DB_NAME_FINANCE', 'btggasify_finance_live')

router = APIRouter(
    prefix="/dn_cn",
    tags=["Debit/Credit Notes"]
)

# --- Pydantic Schemas ---

class CreditNoteCreate(BaseModel):
    CreditNoteNo: str
    Date: date
    CreditAmount: float
    Description: Optional[str] = None
    CustomerId: int
    InvoiceNo: Optional[Any] = None 
    CurrencyId: int
    IsSubmitted: bool = False
    GasCodeId: int = 0
    Qty: float = 1.0
    UomId: int = 0

class CreditNoteUpdate(BaseModel):
    CreditNoteId: int
    CreditNoteNo: str
    Date: date
    CreditAmount: float
    Description: Optional[str] = None
    CustomerId: int
    InvoiceNo: Optional[Any] = None
    CurrencyId: int
    IsSubmitted: bool
    GasCodeId: int = 0
    Qty: float = 1.0
    UomId: int = 0

class DebitNoteCreate(BaseModel):
    DebitNoteNo: str
    Date: date
    DebitAmount: float
    Description: Optional[str] = None
    CustomerId: int
    InvoiceNo: Optional[Any] = None
    CurrencyId: int
    IsSubmitted: bool = False
    GasCodeId: int = 0
    Qty: float = 1.0
    UomId: int = 0

class DebitNoteUpdate(BaseModel):
    DebitNoteId: int
    DebitNoteNo: str
    Date: date
    DebitAmount: float
    Description: Optional[str] = None
    CustomerId: int
    InvoiceNo: Optional[Any] = None
    CurrencyId: int
    IsSubmitted: bool
    GasCodeId: int = 0
    Qty: float = 1.0
    UomId: int = 0

# --- API Endpoints ---

from sqlalchemy import select

# 1. Create Credit Note
@router.post("/create-credit-note")
async def create_credit_note(note: CreditNoteCreate, db: Session = Depends(get_db)):
    # 1. Insert into Credit_Notes
    new_cn = CreditNotes(
        CreditNoteNumber=note.CreditNoteNo, # Front sends 'CreditNoteNo', map to DB 'CreditNoteNumber'
        TransactionDate=note.Date,          # Front sends 'Date', map to DB 'TransactionDate'
        Amount=note.CreditAmount,           # Front sends 'CreditAmount', map to DB 'Amount'
        Description=note.Description,
        CustomerId=note.CustomerId,
        InvoiceId=note.InvoiceNo,           # Front sending ID in InvoiceNo field. Map to InvoiceId.
        CurrencyId=note.CurrencyId,
        IsSubmitted=note.IsSubmitted,
        GasCodeId=note.GasCodeId,
        Qty=note.Qty,
        UomId=note.UomId
    )
    db.add(new_cn)
    await db.commit()
    await db.refresh(new_cn)

    # 2. Insert into credit_invoice if InvoiceNo (ID) is present
    # Note: CreditInvoice.InvoiceNo is String(50). If we have ID, do we put ID?
    # Or should we just skip this table if it's redundant?
    # Keeping it for now, converting ID to string.
    if note.InvoiceNo:
        new_inv = CreditInvoice(
            CreditNoteId=new_cn.CreditNoteId,
            InvoiceNo=str(note.InvoiceNo) 
        )
        db.add(new_inv)
        await db.commit()

    return {"status": "success", "message": "Credit Note created successfully", "data": new_cn}

# 2. Update Credit Note
@router.put("/update-credit-note")
async def update_credit_note(note: CreditNoteUpdate, db: Session = Depends(get_db)):
    # 1. Update Credit_Notes
    query = select(CreditNotes).where(CreditNotes.CreditNoteId == note.CreditNoteId)
    result = await db.execute(query)
    existing_cn = result.scalars().first()
    
    if not existing_cn:
        raise HTTPException(status_code=404, detail="Credit Note not found")

    existing_cn.CreditNoteNumber = note.CreditNoteNo
    existing_cn.TransactionDate = note.Date
    existing_cn.Amount = note.CreditAmount
    existing_cn.Description = note.Description
    existing_cn.CustomerId = note.CustomerId
    existing_cn.InvoiceId = note.InvoiceNo
    existing_cn.CurrencyId = note.CurrencyId
    existing_cn.IsSubmitted = note.IsSubmitted
    existing_cn.GasCodeId = note.GasCodeId
    existing_cn.Qty = note.Qty
    existing_cn.UomId = note.UomId
    
    await db.commit()

    # 2. Update credit_invoice
    if note.InvoiceNo:
        inv_query = select(CreditInvoice).where(CreditInvoice.CreditNoteId == note.CreditNoteId)
        inv_result = await db.execute(inv_query)
        existing_inv = inv_result.scalars().first()
        
        if existing_inv:
            existing_inv.InvoiceNo = str(note.InvoiceNo)
        else:
            new_inv = CreditInvoice(
                CreditNoteId=note.CreditNoteId,
                InvoiceNo=str(note.InvoiceNo)
            )
            db.add(new_inv)
        await db.commit()

    return {"status": "success", "message": "Credit Note updated successfully", "data": existing_cn}


# 3. Create Debit Note
@router.post("/create-debit-note")
async def create_debit_note(note: DebitNoteCreate, db: Session = Depends(get_db)):
    # 1. Insert into Debit_Notes
    new_dn = DebitNotes(
        DebitNoteNumber=note.DebitNoteNo,
        TransactionDate=note.Date,
        Amount=note.DebitAmount,
        Description=note.Description,
        CustomerId=note.CustomerId,
        InvoiceId=note.InvoiceNo,
        CurrencyId=note.CurrencyId,
        IsSubmitted=note.IsSubmitted,
        GasCodeId=note.GasCodeId,
        Qty=note.Qty,
        UomId=note.UomId
    )
    db.add(new_dn)
    await db.commit()
    await db.refresh(new_dn)

    # 2. Insert into debit_invoice
    if note.InvoiceNo:
        new_inv = DebitInvoice(
            DebitNoteId=new_dn.DebitNoteId,
            InvoiceNo=str(note.InvoiceNo)
        )
        db.add(new_inv)
        await db.commit()

    # 3. Sync to AR Ledger (if submitted)
    if note.IsSubmitted:
        await db.execute(text(f"CALL {DB_NAME_FINANCE}.proc_AR_InsertFromDebitNote(:id, :org, :branch, :user)"), 
                         {"id": new_dn.DebitNoteId, "org": 1, "branch": 1, "user": "System"})
        await db.commit()

    return {"status": "success", "message": "Debit Note created successfully", "data": new_dn}


# 4. Update Debit Note
@router.put("/update-debit-note")
async def update_debit_note(note: DebitNoteUpdate, db: Session = Depends(get_db)):
    # 1. Update Debit_Notes
    query = select(DebitNotes).where(DebitNotes.DebitNoteId == note.DebitNoteId)
    result = await db.execute(query)
    existing_dn = result.scalars().first()

    if not existing_dn:
        raise HTTPException(status_code=404, detail="Debit Note not found")

    existing_dn.DebitNoteNumber = note.DebitNoteNo
    existing_dn.TransactionDate = note.Date
    existing_dn.Amount = note.DebitAmount
    existing_dn.Description = note.Description
    existing_dn.CustomerId = note.CustomerId
    existing_dn.InvoiceId = note.InvoiceNo
    existing_dn.CurrencyId = note.CurrencyId
    existing_dn.IsSubmitted = note.IsSubmitted
    existing_dn.GasCodeId = note.GasCodeId
    existing_dn.Qty = note.Qty
    existing_dn.UomId = note.UomId
    
    await db.commit()

    # 2. Update debit_invoice
    if note.InvoiceNo:
        inv_query = select(DebitInvoice).where(DebitInvoice.DebitNoteId == note.DebitNoteId)
        inv_result = await db.execute(inv_query)
        existing_inv = inv_result.scalars().first()

        if existing_inv:
            existing_inv.InvoiceNo = str(note.InvoiceNo)
        else:
            new_inv = DebitInvoice(
                DebitNoteId=note.DebitNoteId,
                InvoiceNo=str(note.InvoiceNo)
            )
            db.add(new_inv)
        await db.commit()

    # 3. Sync to AR Ledger (if submitted)
    if note.IsSubmitted:
        await db.execute(text(f"CALL {DB_NAME_FINANCE}.proc_AR_InsertFromDebitNote(:id, :org, :branch, :user)"), 
                         {"id": note.DebitNoteId, "org": 1, "branch": 1, "user": "System"})
        await db.commit()

    return {"status": "success", "message": "Debit Note updated successfully", "data": existing_dn}

# 5. Get Customers (NEW)
@router.get("/get-customers")
async def get_customers():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DNCN_GetCustomers()")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {"status": "success", "data": [dict(row._mapping) for row in rows]}
            
    except Exception as e:
        print(f"Error fetching customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 6. Get All Credit Notes
@router.get("/get-all-credit-notes")
async def get_all_credit_notes():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DNCN_GetAllCN()")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {"status": "success", "data": [dict(row._mapping) for row in rows]}
    except Exception as e:
        print(f"Error fetching credit notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 7. Get All Debit Notes
@router.get("/get-all-debit-notes")
async def get_all_debit_notes():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DNCN_GetAllDN()")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {"status": "success", "data": [dict(row._mapping) for row in rows]}
    except Exception as e:
        print(f"Error fetching debit notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 8. Get Credit Note by ID
@router.get("/get-credit-note/{id}")
async def get_credit_note_by_id(id: int):
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DNCN_GetCNById(:id)")
            result = await conn.execute(query, {"id": id})
            row = result.fetchone()
            if row:
                return {"status": "success", "data": dict(row._mapping)}
            else:
                 return {"status": "error", "message": "Credit Note not found"}
    except Exception as e:
        print(f"Error fetching credit note: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 9. Get Debit Note by ID
@router.get("/get-debit-note/{id}")
async def get_debit_note_by_id(id: int):
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DNCN_GetDNById(:id)")
            result = await conn.execute(query, {"id": id})
            row = result.fetchone()
            if row:
                return {"status": "success", "data": dict(row._mapping)}
            else:
                 return {"status": "error", "message": "Debit Note not found"}
    except Exception as e:
        print(f"Error fetching debit note: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 10. Delete Credit Note
@router.delete("/delete-credit-note/{id}")
async def delete_credit_note(id: int, db: Session = Depends(get_db)):
    try:
        # Delete from credit_invoice first (child)
        await db.execute(text(f"DELETE FROM {DB_NAME_FINANCE}.credit_invoice WHERE CreditNoteId = :id"), {"id": id})
        # Delete from Credit_Notes (parent)
        await db.execute(text(f"DELETE FROM {DB_NAME_FINANCE}.Credit_Notes WHERE CreditNoteId = :id"), {"id": id})
        await db.commit()
        return {"status": "success", "message": "Credit Note deleted successfully"}
    except Exception as e:
        await db.rollback()
        print(f"Error deleting credit note: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 11. Delete Debit Note
@router.delete("/delete-debit-note/{id}")
async def delete_debit_note(id: int, db: Session = Depends(get_db)):
    try:
        # Delete from debit_invoice first (child)
        await db.execute(text(f"DELETE FROM {DB_NAME_FINANCE}.debit_invoice WHERE DebitNoteId = :id"), {"id": id})
        # Delete from Debit_Notes (parent)
        await db.execute(text(f"DELETE FROM {DB_NAME_FINANCE}.Debit_Notes WHERE DebitNoteId = :id"), {"id": id})
        # Cleanup AR Ledger
        await db.execute(text(f"DELETE FROM {DB_NAME_FINANCE}.tbl_accounts_receivable WHERE invoice_id = :id AND doc_type = 'DN'"), {"id": id})
        await db.commit()
        return {"status": "success", "message": "Debit Note deleted successfully"}
    except Exception as e:
        await db.rollback()
        print(f"Error deleting debit note: {e}")
        raise HTTPException(status_code=500, detail=str(e))