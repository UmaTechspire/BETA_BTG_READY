from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..services.opening_balance_service import get_or_create_monthly_balance, recalculate_month_closing

router = APIRouter(prefix="/opening-balance", tags=["OpeningBalance"])

@router.get("")
async def get_opening_balance(
    module_name: str,
    org_id: int,
    branch_id: int,
    from_date: date,
    reference_id: Optional[int] = None,
    currency_id: Optional[int] = 1,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the monthly balance information (opening and closing balances) for the requested month.
    Automatically triggers roll-forward logic if the month row does not exist.
    """
    try:
        # Note: reference_id is kept in signature for compatibility but currently NULL for petty cash
        data = await get_or_create_monthly_balance(
            db=db,
            module_name=module_name,
            org_id=org_id,
            branch_id=branch_id,
            currency_id=currency_id,
            target_date=from_date
        )
        return {"status": True, "data": data}
    except Exception as e:
        import traceback
        return {"status": False, "message": str(e), "traceback": traceback.format_exc()}

@router.post("/recalculate")
async def recalculate_balances(
    module_name: str,
    org_id: int,
    branch_id: int,
    month_date: date,
    currency_id: Optional[int] = 1,
    db: AsyncSession = Depends(get_db)
):
    """
    Recalculates the closing balance manually for a month.
    """
    try:
        # 1. Fetch current month record to get opening values
        month_start = date(month_date.year, month_date.month, 1)
        data = await get_or_create_monthly_balance(
            db=db,
            module_name=module_name,
            org_id=org_id,
            branch_id=branch_id,
            currency_id=currency_id,
            target_date=month_start
        )
        return {"status": True, "message": "Recalculated successfully", "data": data}
    except Exception as e:
        import traceback
        return {"status": False, "message": str(e), "traceback": traceback.format_exc()}
