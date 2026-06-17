from fastapi import APIRouter, Depends, Query
from typing import Optional

router = APIRouter(
    prefix="/api/FinanceReport",
    tags=["FinanceReport"]
)

# -----------------------------
# Mock mediator replacement
# -----------------------------
async def send_common_report(query: dict):
    """
    Replace this with your actual service / DB logic
    """
    return query  # placeholder (same as mediator result)


# -----------------------------
# GET: SalesReport
# -----------------------------
@router.get("/SalesReport")
async def sales_report(
    orgid: int = Query(...),
    fromDate: Optional[str] = Query(None),
    toDate: Optional[str] = Query(None),
    customerid: int = Query(...),
    gasid: int = Query(...)
):
    query = {
        "opt": 1,
        "orgid": orgid,
        "customerid": customerid,
        "Fromdate": fromDate,
        "Todate": toDate,
        "gasid": gasid
    }

    result = await send_common_report(query)
    return result


# -----------------------------
# GET: ProfitAndLossReport
# -----------------------------
@router.get("/ProfitAndLossReport")
async def profit_and_loss_report(
    orgid: int = Query(...),
    fromDate: Optional[str] = Query(None),
    toDate: Optional[str] = Query(None),
    currencyid: int = Query(...)
):
    query = {
        "opt": 2,
        "orgid": orgid,
        "currencyid": currencyid,
        "Fromdate": fromDate,
        "Todate": toDate
    }

    result = await send_common_report(query)
    return result
