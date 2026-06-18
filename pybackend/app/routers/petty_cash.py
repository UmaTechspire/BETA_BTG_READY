from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db, DB_NAME_MASTER, DB_NAME_USER, DB_NAME_FINANCE
from ..models.petty_cash import TblPettyCash as PettyCash
from datetime import date, datetime
import os
import shutil
from pathlib import Path

router = APIRouter(prefix="/pettycash", tags=["PettyCash"])

# Directory to store uploaded files
UPLOAD_DIR = Path(__file__).parent.parent / "uploads" / "pettycash"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def row_to_dict(row, lowercase_keys=False):
    """Helper to convert SQLAlchemy row or model to a dict, handling Decimals/Dates."""
    from decimal import Decimal
    from datetime import date, datetime
    
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

class PettyCashHeader(BaseModel):
    PettyCashId: Optional[int] = Field(None, alias="PettyCashId")
    VoucherNo: Optional[str] = Field(None, alias="VoucherNo")
    ExpDate: Optional[date] = Field(None, alias="ExpDate")
    Expense_type_id: Optional[int] = Field(None, alias="expense_type_id")
    category_id: Optional[int] = Field(None, alias="category_id")
    ExpenseDescriptionId: Optional[str] = Field(None, alias="ExpenseDescriptionId")
    ExpenseDescription: Optional[str] = Field(None, alias="ExpenseDescription")
    Amount: Optional[float] = Field(None, alias="Amount")
    OrgId: Optional[int] = Field(1, alias="OrgId")
    BranchId: Optional[int] = Field(1, alias="BranchId")
    Who: Optional[str] = Field(None, alias="Who")
    Whom: Optional[str] = Field(None, alias="Whom")
    currencyid: Optional[int] = Field(None, alias="currencyid")
    IsSubmitted: Optional[int] = Field(0, alias="IsSubmitted")

    class Config:
        populate_by_name = True
        extra = "allow"


class CreatePettyCashCommand(BaseModel):
    header: PettyCashHeader
    command: Optional[str] = None
    payload: Optional[List[Any]] = []


@router.post("/create")
async def create_pettycash(
    request: Request,
    VoucherNo: Optional[str] = Form(None),
    ExpDate: Optional[date] = Form(None),
    category_id: Optional[int] = Form(None),
    expense_type_id: Optional[int] = Form(None),

    Amount: Optional[float] = Form(None),
    OrgId: Optional[int] = Form(1),
    BranchId: Optional[int] = Form(1),
    Who: Optional[str] = Form(None),
    Whom: Optional[str] = Form(None),
    currencyid: Optional[int] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    """Create a new petty cash record with automated field population."""
    header_raw = {}
    is_submitted = False
    
    # 1. Capture JSON if provided via Form field 'command' or 'payload'
    form_data = await request.form()
    command_str = form_data.get("command") or form_data.get("payload")
    cmd = "Insert"
    
    header = PettyCashHeader(
        VoucherNo=VoucherNo,
        ExpDate=ExpDate,
        category_id=category_id,
        Expense_type_id=expense_type_id,

        Amount=Amount,
        OrgId=OrgId,
        BranchId=BranchId,
        Who=Who,
        Whom=Whom,
        currencyid=currencyid,
        IsSubmitted=form_data.get("IsSubmitted")
    )

    if command_str and isinstance(command_str, str) and command_str.strip().startswith("{"):
        try:
            import json
            data = json.loads(command_str)
            if "Header" in data and "header" not in data: data["header"] = data.pop("Header")
            if "Payload" in data and "payload" not in data: data["payload"] = data.pop("Payload")
            
            print(f"DEBUG create_pettycash incoming JSON: {data}")

            parsed = CreatePettyCashCommand.model_validate(data) if hasattr(CreatePettyCashCommand, "model_validate") else CreatePettyCashCommand.parse_obj(data)
            jh = parsed.header
            
            print(f"DEBUG create_pettycash parsed header (jh): {jh}")
            print(f"DEBUG create_pettycash jh.category_id: {jh.category_id}")
            print(f"DEBUG create_pettycash parsed category from JSON: {data.get('header', {}).get('category_id')}")
            header.VoucherNo = jh.VoucherNo or header.VoucherNo
            header.ExpDate = jh.ExpDate or header.ExpDate
            header.category_id = jh.category_id or header.category_id
            header.Expense_type_id = jh.Expense_type_id or header.Expense_type_id
            header.ExpenseDescriptionId = jh.ExpenseDescriptionId or header.ExpenseDescriptionId
            header.ExpenseDescription = jh.ExpenseDescription or header.ExpenseDescription
            header.Amount = jh.Amount or header.Amount
            header.OrgId = jh.OrgId or header.OrgId
            header.BranchId = jh.BranchId or header.BranchId
            header.Who = jh.Who or header.Who
            header.Whom = jh.Whom or header.Whom
            header.currencyid = jh.currencyid or header.currencyid

            header.IsSubmitted = jh.IsSubmitted if jh.IsSubmitted is not None else header.IsSubmitted
            
            cmd = parsed.command or cmd
            header_raw = data.get("header", {})
        except Exception as e:
            print(f"DEBUG create_pettycash JSON parse error: {str(e)}")
            if not VoucherNo and not Amount:
                raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")

    is_submitted = (cmd == "Post" or header.IsSubmitted == 1)

    try:
        # 1. Fetch Exchange Rate from DB
        rate = 1.0
        if header.currencyid:
            rate_query = text("CALL proc_PC_GetExchangeRate(:cid)")
            rate_res = await db.execute(rate_query, {"cid": header.currencyid})
            fetched_rate = rate_res.scalar()
            if fetched_rate:
                rate = float(fetched_rate)

        # 2. Generate ONE PCNumber for the entire batch
        q_max = await db.execute(select(func.max(PettyCash.PettyCashId)))
        max_id = q_max.scalar() or 0
        pc_no = f"PC{str(max_id + 1).zfill(6)}"

        # 3. Process items from payload if present, otherwise use header (legacy fallback)
        items_to_save = []
        payload_items = data.get("payload", []) if 'data' in locals() else []
        
        if payload_items and isinstance(payload_items, list):
            for idx, item in enumerate(payload_items):
                # Handle file for each item? Usually one PC has one attachment or each row has one.
                # The user requested 'attachment' in grid, but legacy code handled one file.
                # For now, we'll associate the main file with the first item or all items if needed.
                # Standard claim & payment usually has one attachment in header.
                
                # Calculate AmountIDR for this item
                item_amt = float(item.get("amount") or 0)
                item_amt_idr = item_amt * rate
                
                new_item = PettyCash(
                    pc_number=pc_no,
                    VoucherNo=header.VoucherNo,
                    ExpDate=header.ExpDate,
                    expense_type_id=item.get("expenseType"),
                    category_id=item.get("category"),
                    ExpenseDescription=item.get("expenseDescription"),
                    AmountIDR=item_amt_idr,
                    Amount=item_amt,
                    ExpenseFileName=file.filename if file and idx == 0 else None,
                    ExpenseFilePath=None, # Will update below if file exists
                    IsSubmitted=is_submitted,
                    OrgId=header.OrgId,
                    BranchId=header.BranchId,
                    Who=header.Who,
                    Whom=item.get("whom"),
                    currencyid=header.currencyid,
                    exchangeRate=rate
                )
                items_to_save.append(new_item)
        else:
            # Fallback to single header record (original behavior)
            amt_idr = float(header.Amount or 0) * rate
            new_item = PettyCash(
                pc_number=pc_no,
                VoucherNo=header.VoucherNo,
                ExpDate=header.ExpDate,
                expense_type_id=header.Expense_type_id,
                category_id=header.category_id,
                ExpenseDescription=header.ExpenseDescription,
                AmountIDR=amt_idr,
                Amount=header.Amount,
                ExpenseFileName=file.filename if file else None,
                IsSubmitted=is_submitted,
                OrgId=header.OrgId,
                BranchId=header.BranchId,
                Who=header.Who,
                Whom=header.Whom,
                currencyid=header.currencyid,
                exchangeRate=rate
            )
            items_to_save.append(new_item)

        # 4. Handle file upload (main file)
        file_path = None
        if file:
            try:
                file_path = UPLOAD_DIR / file.filename
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                file_path = str(file_path)
                # Assign path to items that have the filename
                for item in items_to_save:
                    if item.ExpenseFileName == file.filename:
                        item.ExpenseFilePath = file_path
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")
        
        # 5. Add all items
        for item in items_to_save:
            db.add(item)
            
        await db.commit()
        
        # Trigger recalculation of monthly balances
        if header.ExpDate:
            try:
                from ..services.opening_balance_service import get_or_create_monthly_balance
                await get_or_create_monthly_balance(
                    db=db,
                    module_name="PETTY_CASH",
                    org_id=header.OrgId or 1,
                    branch_id=header.BranchId or 1,
                    currency_id=header.currencyid,
                    target_date=header.ExpDate
                )
            except Exception as e_bal:
                print(f"Error recalculating monthly balance: {e_bal}")

        # Return the first item's data or summary
        return {"status": True, "data": row_to_dict(items_to_save[0])}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in create_pettycash: {tb}")
        await db.rollback()
        return {"status": False, "message": str(e), "traceback": tb}


@router.put("/update")
async def update_pettycash(
    request: Request,
    PettyCashId: int = Form(...),
    VoucherNo: Optional[str] = Form(None),
    ExpDate: Optional[date] = Form(None),
    category_id: Optional[int] = Form(None),
    expense_type_id: Optional[int] = Form(None),

    Amount: Optional[float] = Form(None),
    OrgId: Optional[int] = Form(None),
    BranchId: Optional[int] = Form(None),
    Who: Optional[str] = Form(None),
    Whom: Optional[str] = Form(None),
    currencyid: Optional[int] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    """Update a petty cash record with automated field population."""
    header_raw = {}
    
    form_data = await request.form()
    command_str = form_data.get("command") or form_data.get("payload")
    cmd = "Update"

    header = PettyCashHeader(
        PettyCashId=PettyCashId,
        VoucherNo=VoucherNo,
        ExpDate=ExpDate,
        category_id=category_id,
        Expense_type_id=expense_type_id,

        Amount=Amount,
        OrgId=OrgId,
        BranchId=BranchId,
        Who=Who,
        Whom=Whom,
        currencyid=currencyid
    )

    if command_str and isinstance(command_str, str) and command_str.strip().startswith("{"):
        try:
            import json
            data = json.loads(command_str)
            if "Header" in data and "header" not in data: data["header"] = data.pop("Header")
            
            parsed = CreatePettyCashCommand.model_validate(data) if hasattr(CreatePettyCashCommand, "model_validate") else CreatePettyCashCommand.parse_obj(data)
            jh = parsed.header
            
            header.PettyCashId = jh.PettyCashId if jh.PettyCashId is not None else header.PettyCashId
            header.VoucherNo = jh.VoucherNo if jh.VoucherNo is not None else header.VoucherNo
            header.ExpDate = jh.ExpDate if jh.ExpDate is not None else header.ExpDate
            header.category_id = jh.category_id if jh.category_id is not None else header.category_id
            header.Expense_type_id = jh.Expense_type_id if jh.Expense_type_id is not None else header.Expense_type_id
            header.ExpenseDescriptionId = jh.ExpenseDescriptionId if jh.ExpenseDescriptionId is not None else header.ExpenseDescriptionId
            header.ExpenseDescription = jh.ExpenseDescription if jh.ExpenseDescription is not None else header.ExpenseDescription
            header.Amount = jh.Amount if jh.Amount is not None else header.Amount
            header.OrgId = jh.OrgId if jh.OrgId is not None else header.OrgId
            header.BranchId = jh.BranchId if jh.BranchId is not None else header.BranchId
            header.Who = jh.Who if jh.Who is not None else header.Who
            header.Whom = jh.Whom if jh.Whom is not None else header.Whom
            header.currencyid = jh.currencyid if jh.currencyid is not None else header.currencyid
            header.IsSubmitted = jh.IsSubmitted if jh.IsSubmitted is not None else header.IsSubmitted
            
            cmd = parsed.command or cmd
            header_raw = data.get("header", {})
        except Exception as e:
            print(f"DEBUG update_pettycash JSON parse error: {str(e)}")
            if not PettyCashId:
                raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    
    if not header.PettyCashId:
        raise HTTPException(status_code=400, detail="PettyCashId is required for update")
    
    q = await db.execute(select(PettyCash).where(PettyCash.PettyCashId == header.PettyCashId))
    obj = q.scalars().first()
    if not obj:
        raise HTTPException(status_code=404, detail="PettyCash not found")
    
    # 1. Fetch existing group by PCNumber
    q_pc = await db.execute(select(PettyCash.pc_number).where(PettyCash.PettyCashId == header.PettyCashId))
    current_pc_no = q_pc.scalar()
    
    # 2. Fetch Exchange Rate from DB
    rate = 1.0
    if header.currencyid:
        rate_query = text("CALL proc_PC_GetExchangeRate(:cid)")
        rate_res = await db.execute(rate_query, {"cid": header.currencyid})
        fetched_rate = rate_res.scalar()
        if fetched_rate:
            rate = float(fetched_rate)

    # 3. Handle file upload (if any)
    file_name = None
    file_path = None
    if file:
        try:
            file_name = file.filename
            file_path = UPLOAD_DIR / file_name
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_path = str(file_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")

    # 4. Batch sync items
    payload_items = data.get("payload", []) if 'data' in locals() else []
    is_submitted = (cmd == "Post" or header.IsSubmitted == 1)

    if payload_items and isinstance(payload_items, list):
        # Determine items to keep, update, or delete
        # For simplicity in batch "standardization", we'll delete existing ones for this PC number and re-insert
        # but only if we have a PC number.
        if current_pc_no:
            await db.execute(text("DELETE FROM tbl_petty_cash WHERE pc_number = :pc"), {"pc": current_pc_no})
        else:
            # Fallback for legacy records without pc_number
            await db.execute(text("DELETE FROM tbl_petty_cash WHERE PettyCashId = :pid"), {"pid": header.PettyCashId})
            # Generate a new pc_number to consolidate future updates
            q_max = await db.execute(select(func.max(PettyCash.PettyCashId)))
            max_id = q_max.scalar() or 0
            current_pc_no = f"PC{str(max_id + 1).zfill(6)}"
        
        items_to_save = []
        for idx, item in enumerate(payload_items):
            item_amt = float(item.get("amount") or 0)
            item_amt_idr = item_amt * rate
            
            new_item = PettyCash(
                pc_number=current_pc_no,
                VoucherNo=header.VoucherNo,
                ExpDate=header.ExpDate,
                expense_type_id=item.get("expenseType"),
                category_id=item.get("category"),
                ExpenseDescription=item.get("expenseDescription"),
                AmountIDR=item_amt_idr,
                Amount=item_amt,
                ExpenseFileName=file_name if file and idx == 0 else (item.get("ExpenseFileName") if 'ExpenseFileName' in item else None),
                ExpenseFilePath=file_path if file and idx == 0 else (item.get("ExpenseFilePath") if 'ExpenseFilePath' in item else None),
                IsSubmitted=is_submitted,
                OrgId=header.OrgId or 1,
                BranchId=header.BranchId or 1,
                Who=header.Who,
                Whom=item.get("whom"),
                currencyid=header.currencyid,
                exchangeRate=rate
            )
            items_to_save.append(new_item)
        
        for item in items_to_save:
            db.add(item)
            
        await db.commit()

        # Trigger recalculation of monthly balances
        if header.ExpDate:
            try:
                from ..services.opening_balance_service import get_or_create_monthly_balance
                await get_or_create_monthly_balance(
                    db=db,
                    module_name="PETTY_CASH",
                    org_id=header.OrgId or 1,
                    branch_id=header.BranchId or 1,
                    currency_id=header.currencyid,
                    target_date=header.ExpDate
                )
            except Exception as e_bal:
                print(f"Error recalculating monthly balance: {e_bal}")

        return {"status": True, "message": "Batch update success"}
    else:
        # Single record update (fallback)
        q = await db.execute(select(PettyCash).where(PettyCash.PettyCashId == header.PettyCashId))
        obj = q.scalars().first()
        if not obj:
            raise HTTPException(status_code=404, detail="PettyCash not found")
        
        if file_name:
            obj.ExpenseFileName = file_name
            obj.ExpenseFilePath = file_path
        
        if cmd == "Post" or header.IsSubmitted == 1:
            obj.IsSubmitted = True

        if header.VoucherNo: obj.VoucherNo = header.VoucherNo
        if header.ExpDate: obj.ExpDate = header.ExpDate
        if header.category_id: obj.category_id = header.category_id
        if header.Expense_type_id: obj.expense_type_id = header.Expense_type_id
        if header.ExpenseDescription: obj.ExpenseDescription = header.ExpenseDescription
        if header.Amount:
            obj.Amount = header.Amount
            obj.AmountIDR = float(header.Amount) * rate
        if header.Who: obj.Who = header.Who
        if header.Whom: obj.Whom = header.Whom
        if header.currencyid: obj.currencyid = header.currencyid
        obj.exchangeRate = rate
        
        await db.commit()

        # Trigger recalculation of monthly balances
        if header.ExpDate:
            try:
                from ..services.opening_balance_service import get_or_create_monthly_balance
                await get_or_create_monthly_balance(
                    db=db,
                    module_name="PETTY_CASH",
                    org_id=header.OrgId or 1,
                    branch_id=header.BranchId or 1,
                    currency_id=header.currencyid,
                    target_date=header.ExpDate
                )
            except Exception as e_bal:
                print(f"Error recalculating monthly balance: {e_bal}")

        return {"status": True, "data": row_to_dict(obj)}


@router.get("/get-by-id")
async def get_by_id(pettycashid: int, branchid: int, orgid: int, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(PettyCash).where(PettyCash.PettyCashId == pettycashid))
    obj = q.scalars().first()
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": True, "data": row_to_dict(obj)}


@router.get("/get-group-by-id")
async def get_pettycash_group_by_id(pettycashid: int, branchid: int, orgid: int, db: AsyncSession = Depends(get_db)):
    # 1. Find the pc_number for this ID
    q_pc = await db.execute(select(PettyCash.pc_number).where(PettyCash.PettyCashId == pettycashid))
    pc_no = q_pc.scalar()
    
    if not pc_no:
        # Fallback: if no pc_number (legacy), return it as a single-item list
        q = await db.execute(select(PettyCash).where(PettyCash.PettyCashId == pettycashid))
        obj = q.scalars().first()
        if not obj:
            return {"status": False, "message": "Not found"}
        return {"status": True, "data": [row_to_dict(obj, lowercase_keys=True)]}
    
    # 2. Fetch all items with this pc_number
    q_group = await db.execute(select(PettyCash).where(
        PettyCash.pc_number == pc_no,
        PettyCash.OrgId == orgid,
        PettyCash.BranchId == branchid
    ))
    items = q_group.scalars().all()
    # Sort by PettyCashId to maintain order
    sorted_items = sorted(items, key=lambda x: x.PettyCashId)
    return {"status": True, "data": [row_to_dict(i, lowercase_keys=True) for i in sorted_items]}


@router.get("/list")
async def get_list(
    branchid: Optional[int] = None, 
    orgid: Optional[int] = None, 
    pettycashid: int = 0, 
    exptype: Optional[int] = None, 
    voucherno: Optional[str] = None, 
    category_id: Optional[int] = None,
    currencyid: Optional[int] = None,
    FromDate: Optional[date] = None,
    ToDate: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    # Fetch Expenses
    q = await db.execute(
        text("CALL proc_PC_GetList(:pettycashid, :exptype, :voucherno, :category_id, :from_date, :to_date)"),
        {
            "pettycashid": pettycashid if pettycashid else 0,
            "exptype": exptype or 0,
            "voucherno": voucherno or '',
            "category_id": category_id or 0,
            "from_date": FromDate,
            "to_date": ToDate
        }
    )
    items = q.fetchall()
    results = [row_to_dict(it, lowercase_keys=True) for it in items]
    


    # Implementation-level filtering for currencyid if provided
    if currencyid:
        results = [r for r in results if r.get("currencyid") == currencyid]

    return {"status": True, "data": results}


@router.get("/opening-balance")
async def get_opening_balance(
    from_date: date,
    branchid: int,
    orgid: int,
    currencyid: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        from ..services.opening_balance_service import get_or_create_monthly_balance
        data = await get_or_create_monthly_balance(
            db=db,
            module_name="PETTY_CASH",
            org_id=orgid,
            branch_id=branchid,
            currency_id=currencyid,
            target_date=from_date
        )
        print(f"DEBUG get_opening_balance: target_date={from_date}, returned_data={data}")
        op_debit = data.get("opening_debit", 0.0)
        op_credit = data.get("opening_credit", 0.0)
        balance = op_debit
        return {"status": True, "opening_balance": balance, "opening_debit": op_debit, "opening_credit": op_credit}
    except Exception as e:
        import traceback
        return {"status": False, "message": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-balances")
async def debug_balances(db: AsyncSession = Depends(get_db)):
    """Temporary debug endpoint to view tbl_opening_balance_master rows."""
    try:
        res = await db.execute(text(f"SELECT * FROM {DB_NAME_FINANCE}.tbl_opening_balance_master ORDER BY balance_month"))
        rows = res.fetchall()
        return {"status": True, "data": [row_to_dict(r) for r in rows]}
    except Exception as e:
        return {"status": False, "message": str(e)}


@router.get("/inspect-table")
async def inspect_table(tablename: str, db: AsyncSession = Depends(get_db)):
    """Debug endpoint to see columns of any table."""
    try:
        # Prevent basic SQL injection by allowing only alphanumeric and underscores
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', tablename):
             return {"status": False, "message": "Invalid table name"}
             
        result = await db.execute(text(f"SHOW COLUMNS FROM {tablename}"))
        rows = result.fetchall()
        columns = [dict(row._mapping) for row in rows]
        return {"status": True, "table": tablename, "columns": columns}
    except Exception as e:
        return {"status": False, "error": str(e)}


@router.get("/master-expense-categories")
async def get_master_expense_categories(orgid: int = 1, branchid: int = 1, db: AsyncSession = Depends(get_db)):
    """Return rows from master_expense_category."""
    try:
        query = text("CALL proc_PC_GetExpenseCategories()")
        result = await db.execute(query)
        rows = [row_to_dict(row, lowercase_keys=True) for row in result.fetchall()]
        return {"status": True, "data": rows}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in master-expense-categories: {tb}")
        return {"status": False, "message": str(e)}


@router.get("/master-expense-types")
async def get_master_expense_types(orgid: int = 1, branchid: int = 1, category_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    """Return rows from master_expense_type."""
    try:
        result = await db.execute(
            text("CALL proc_PC_GetExpenseTypes(:cat_id)"),
            {"cat_id": category_id or 0}
        )
        rows = [row_to_dict(row, lowercase_keys=True) for row in result.fetchall()]
        return {"status": True, "data": rows}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in master-expense-types: {tb}")
        return {"status": False, "message": str(e)}


@router.get("/download/{pettycash_id}")
async def download_file(pettycash_id: int, db: AsyncSession = Depends(get_db)):
    """Download the file attached to a petty cash record."""
    q = await db.execute(select(PettyCash).where(PettyCash.PettyCashId == pettycash_id))
    obj = q.scalars().first()
    if not obj:
        raise HTTPException(status_code=404, detail="PettyCash record not found")
    
    if not obj.ExpenseFilePath:
        raise HTTPException(status_code=404, detail="No file attached to this record")
    
    file_path = Path(obj.ExpenseFilePath)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")
    
    return FileResponse(
        path=file_path,
        filename=obj.ExpenseFileName or "download",
        media_type="application/octet-stream"
    )


@router.get("/get-seq-num")
async def get_seq_num(branchId: int, orgid: int, userid: int, db: AsyncSession = Depends(get_db)):
    # simple next sequence: max(PettyCashId) + 1
    q = await db.execute(select(func.max(PettyCash.PettyCashId)))
    max_id = q.scalar() or 0
    next_id = max_id + 1
    return {"status": True, "data": {"VoucherNo": next_id}}


@router.get("/master-currency")
async def get_master_currency(orgid: int = 1, branchid: int = 1, db: AsyncSession = Depends(get_db)):
    """Return rows from master_currency."""
    try:
        query = text("CALL proc_PC_GetCurrencies()")
        result = await db.execute(query)
        # Using lowercase_keys=False to preserve likely ColumnCase (CurrencyId, Currency)
        rows = [row_to_dict(row, lowercase_keys=False) for row in result.fetchall()]
        return {"status": True, "data": rows}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR in master-currency: {tb}")
        return {"status": False, "message": str(e)}


@router.get("/get-image-path")
async def get_image_path(pettycashid: int, branchid: Optional[int] = 1, orgid: Optional[int] = 1, db: AsyncSession = Depends(get_db)):
    """Get the image path and filename for a specific petty cash record."""
    try:
        q = await db.execute(select(PettyCash).where(PettyCash.PettyCashId == pettycashid))
        obj = q.scalars().first()
        
        if not obj:
            raise HTTPException(status_code=404, detail="PettyCash record not found")
        
        # Check if file path exists in record
        if not obj.ExpenseFilePath:
            return {"status": True, "data": None, "message": "No file attached"}
            
        file_path = Path(obj.ExpenseFilePath)
        
        # Construct a relative path or a full URL depending on your frontend needs.
        # Since the frontend seems to use a download endpoint effectively, 
        # we can just return the path information used by the backend.
        
        data = {
            "PettyCashId": obj.PettyCashId,
            "ExpenseFileName": obj.ExpenseFileName,
            "ExpenseFilePath": obj.ExpenseFilePath,
            "ExistsOnServer": file_path.exists()  # Helper boolean
        }
        
        return {"status": True, "data": data}
        
    except Exception as e:
        return {"status": False, "message": str(e)}