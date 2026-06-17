from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from typing import Optional
from ..database import get_db

router = APIRouter(prefix="/api/sales", tags=["Sales Commission"])


@router.get("/get-sales-commission")
async def get_sales_commission(
    customer_id: Optional[int] = Query(None),
    contact: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = text("""
            CALL btggasify_masterpanel_live.get_sales_commission_report(
                :p_customerId,
                :p_contact,
                :p_fromDate,
                :p_toDate,
                :p_search
            )
        """)

        params = {
            "p_customerId": customer_id,
            "p_contact": contact,
            "p_fromDate": from_date,
            "p_toDate": to_date,
            "p_search": search
        }

        result = await db.execute(query, params)
        rows = result.fetchall()

        data = []
        for row in rows:
            r = row._mapping
            data.append({
                "customerName": r.get("CustomerName") or r.get("customerName"),
                "contactName": r.get("ContactName") or r.get("contactName"),
                "invoiceDate": r.get("InvoiceDate") or r.get("invoiceDate"),
                 "invoiceNo": r.get("InvoiceNo") or r.get("salesinvoicenbr"),
                "qty": r.get("Qty") or r.get("qty"),
                "gasName": r.get("GasName") or r.get("gasName"),
                "rate": r.get("Rate") or r.get("rate"),
                "commission": r.get("Commission") or r.get("commission")
            })

        return {
            "status": True,
            "count": len(data),
            "data": data
        }

    except Exception as e:
        print("ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/customers")
async def get_customers(db: AsyncSession = Depends(get_db)):
    try:
        query = text("CALL btggasify_masterpanel_live.get_customers_list()")

        result = await db.execute(query)
        rows = result.fetchall()

        data = [dict(row._mapping) for row in rows]

        return {
            "status": True,
            "data": data
        }

    except Exception as e:
        print("Error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts")
async def get_contacts(
    customer_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = text("CALL btggasify_masterpanel_live.get_contacts_by_customer(:customer_id)")

        result = await db.execute(query, {
            "customer_id": customer_id
        })

        rows = result.fetchall()
        data = [dict(row._mapping) for row in rows]

        return {
            "status": True,
            "data": data
        }

    except Exception as e:
        print("Error:", e)
        raise HTTPException(status_code=500, detail=str(e))