from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models.overdraft import TblOverDraft as OverDraft
from datetime import date, datetime
from decimal import Decimal

router = APIRouter(prefix="/overdraft", tags=["OverDraft"])


def row_to_dict(row, lowercase_keys=False):
    """Helper to convert SQLAlchemy row or model to a dict, handling Decimals/Dates."""
    if row is None:
        return None

    # If it's a model instance
    if hasattr(row, "__table__"):
        d = {}
        for column in row.__table__.columns:
            val = getattr(row, column.name)
            if isinstance(val, Decimal):
                val = float(val)
            elif isinstance(val, (date, datetime)):
                val = val.isoformat()
            key = column.name.lower() if lowercase_keys else column.name
            d[key] = val
        return d

    # If it's a Row mapping
    if hasattr(row, "_mapping"):
        mapping = dict(row._mapping)
        d = {}
        for k, v in mapping.items():
            val = v
            if isinstance(v, Decimal):
                val = float(v)
            elif isinstance(v, (date, datetime)):
                val = v.isoformat()
            key = k.lower() if lowercase_keys else k
            d[key] = val
        return d
    return row


class OverDraftHeader(BaseModel):
    OverDraftId: Optional[int] = Field(None)
    VoucherNo: Optional[str] = Field(None)
    OverDraftDate: Optional[datetime] = Field(None)
    OverDraftType: Optional[str] = Field(None)
    Bank: Optional[str] = Field(None)
    InterestType: Optional[str] = Field(None)
    ODInterest: Optional[float] = Field(None)
    ODAmount: Optional[float] = Field(None)
    ODAmountIDR: Optional[float] = Field(None)
    RepayInMonths: Optional[int] = Field(None)
    FinalSettlementAmount: Optional[float] = Field(0)
    FinalSettlementAmountIDR: Optional[float] = Field(0)
    FinalSettlementDate: Optional[datetime] = Field(None)
    bankid: Optional[int] = Field(None)
    currencyid: Optional[int] = Field(None)
    payment_method: Optional[int] = Field(None)
    IsSubmitted: Optional[bool] = Field(False)
    IsActive: Optional[bool] = Field(True)
    OrgId: Optional[int] = Field(1)
    BranchId: Optional[int] = Field(1)
    userid: Optional[int] = Field(None)
    CreatedIP: Optional[str] = Field(None)
    ModifiedIP: Optional[str] = Field(None)

    class Config:
        populate_by_name = True
        extra = "allow"


class OverDraftCommand(BaseModel):
    command: Optional[str] = None
    Header: Optional[OverDraftHeader] = None
    header: Optional[OverDraftHeader] = None

    class Config:
        extra = "allow"

    def get_header(self):
        return self.Header or self.header


# --- Helper: generate voucher number ---
async def generate_voucher_no(db: AsyncSession) -> str:
    q = await db.execute(select(func.max(OverDraft.OverDraftId)))
    max_id = q.scalar() or 0
    return f"OD{str(max_id + 1).zfill(6)}"


# ================================================
# CREATE
# ================================================
@router.post("/create")
async def create_overdraft(body: OverDraftCommand, db: AsyncSession = Depends(get_db)):
    """Create a new overdraft record."""
    try:
        header = body.get_header()
        if not header:
            raise HTTPException(status_code=400, detail="Header is required")

        cmd = body.command or "Insert"
        is_submitted = (cmd == "Post" or header.IsSubmitted is True)

        # Auto-generate VoucherNo
        voucher_no = await generate_voucher_no(db)

        new = OverDraft(
            VoucherNo=voucher_no,
            OverDraftDate=header.OverDraftDate.date() if isinstance(header.OverDraftDate, datetime) else header.OverDraftDate,
            OverDraftType=header.OverDraftType,
            Bank=header.Bank,
            InterestType=header.InterestType,
            ODInterest=header.ODInterest,
            ODAmount=header.ODAmount,
            ODAmountIDR=header.ODAmountIDR,
            RepayInMonths=header.RepayInMonths,
            FinalSettlementAmount=header.FinalSettlementAmount,
            FinalSettlementAmountIDR=header.FinalSettlementAmountIDR,
            FinalSettlementDate=header.FinalSettlementDate.date() if isinstance(header.FinalSettlementDate, datetime) else header.FinalSettlementDate,
            bankid=header.bankid,
            currencyid=header.currencyid,
            payment_method=header.payment_method,
            IsSubmitted=is_submitted,
            IsActive=header.IsActive if header.IsActive is not None else True,
            OrgId=header.OrgId,
            BranchId=header.BranchId,
        )
        db.add(new)
        await db.flush()
        await db.commit()
        await db.refresh(new)
        return {"status": True, "data": row_to_dict(new), "message": "Overdraft saved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in create_overdraft: {tb}")
        await db.rollback()
        return {"status": False, "message": str(e), "traceback": tb}


# ================================================
# UPDATE
# ================================================
@router.put("/update")
async def update_overdraft(body: OverDraftCommand, db: AsyncSession = Depends(get_db)):
    """Update an existing overdraft record."""
    try:
        header = body.get_header()
        if not header or not header.OverDraftId:
            raise HTTPException(status_code=400, detail="OverDraftId is required for update")

        cmd = body.command or "Update"

        q = await db.execute(select(OverDraft).where(OverDraft.OverDraftId == header.OverDraftId))
        obj = q.scalars().first()
        if not obj:
            raise HTTPException(status_code=404, detail="OverDraft not found")

        # Update fields
        if header.OverDraftDate:
            obj.OverDraftDate = header.OverDraftDate.date() if isinstance(header.OverDraftDate, datetime) else header.OverDraftDate
        if header.OverDraftType:
            obj.OverDraftType = header.OverDraftType
        if header.Bank is not None:
            obj.Bank = header.Bank
        if header.InterestType:
            obj.InterestType = header.InterestType
        if header.ODInterest is not None:
            obj.ODInterest = header.ODInterest
        if header.ODAmount is not None:
            obj.ODAmount = header.ODAmount
        if header.ODAmountIDR is not None:
            obj.ODAmountIDR = header.ODAmountIDR
        if header.RepayInMonths is not None:
            obj.RepayInMonths = header.RepayInMonths
        if header.FinalSettlementAmount is not None:
            obj.FinalSettlementAmount = header.FinalSettlementAmount
        if header.FinalSettlementAmountIDR is not None:
            obj.FinalSettlementAmountIDR = header.FinalSettlementAmountIDR
        if header.FinalSettlementDate:
            obj.FinalSettlementDate = header.FinalSettlementDate.date() if isinstance(header.FinalSettlementDate, datetime) else header.FinalSettlementDate
        if header.bankid is not None:
            obj.bankid = header.bankid
        if header.currencyid is not None:
            obj.currencyid = header.currencyid
        if header.payment_method is not None:
            obj.payment_method = header.payment_method

        if cmd == "Post" or header.IsSubmitted is True:
            obj.IsSubmitted = True

        if header.OrgId:
            obj.OrgId = header.OrgId
        if header.BranchId:
            obj.BranchId = header.BranchId

        await db.commit()
        await db.refresh(obj)
        return {"status": True, "data": row_to_dict(obj), "message": "Overdraft updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in update_overdraft: {tb}")
        await db.rollback()
        return {"status": False, "message": str(e), "traceback": tb}


# ================================================
# LIST
# ================================================
@router.get("/list")
async def get_list(
    branchid: int = 1,
    orgid: int = 1,
    overdraftid: Optional[int] = 0,
    overdrafttype: Optional[str] = None,
    voucherno: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get list of overdraft records with optional filters."""
    try:
        q = await db.execute(
            text("CALL proc_OD_GetList(:overdraftid, :overdrafttype, :voucherno)"),
            {
                "overdraftid": overdraftid if overdraftid else 0,
                "overdrafttype": overdrafttype or '',
                "voucherno": voucherno or ''
            }
        )
        items = q.fetchall()

        return {"status": True, "data": [row_to_dict(it) for it in items]}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in get_list_overdraft: {tb}")
        return {"status": False, "message": str(e), "traceback": tb}


# ================================================
# GET BY ID
# ================================================
@router.get("/get-by-id")
async def get_by_id(
    overdraftid: int,
    branchid: int = 1,
    orgid: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """Get a single overdraft record by ID."""
    try:
        q = await db.execute(select(OverDraft).where(OverDraft.OverDraftId == overdraftid))
        obj = q.scalars().first()
        if not obj:
            raise HTTPException(status_code=404, detail="OverDraft not found")
        return {"status": True, "data": {"Header": row_to_dict(obj)}}
    except HTTPException:
        raise
    except Exception as e:
        return {"status": False, "message": str(e)}


# ================================================
# GET SEQUENCE NUMBER (auto-gen voucher)
# ================================================
@router.get("/get-seq-num")
async def get_seq_num(
    branchId: int = 1,
    orgid: int = 1,
    userid: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Return the next auto-generated voucher number in OD000001 format."""
    try:
        voucher_no = await generate_voucher_no(db)
        return {"status": True, "data": {"VoucherNo": voucher_no}}
    except Exception as e:
        return {"status": False, "message": str(e)}