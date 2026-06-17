from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import text
from ..database import engine 
import os
from dotenv import load_dotenv

# --- FORCE LOAD ENV VARIABLES ---
load_dotenv()

# Explicitly load names to ensure we don't use stale defaults from imports
DB_NAME_USER = os.getenv('DB_NAME_USER', 'btggasify_live')
DB_NAME_USER_NEW = os.getenv('DB_NAME_USER_NEW', 'btggasify_userpanel_live')
DB_NAME_FINANCE = os.getenv('DB_NAME_FINANCE', 'btggasify_finance_live')
DB_NAME_MASTER = os.getenv('DB_NAME_MASTER', 'btggasify_masterpanel_live')
DB_NAME_OLD = os.getenv('DB_NAME_OLD', 'btggasify_live')

router = APIRouter()

# ==========================================
# 1. RESPONSE & FILTER MODELS
# ==========================================

class InvoiceFilter(BaseModel):
    customerid: int = 0
    FromDate: str
    ToDate: str
    BranchId: int = 1
    IsAR: int = 0 
    ItemId: Optional[int] = 0
    SalesPersonId: Optional[int] = 0

class SalesReportItem(BaseModel):
    DetailId: int
    Salesinvoicesdate: Optional[str] = ""
    CustomerName: Optional[str] = ""
    InvoiceCurrency: Optional[str] = ""
    InvoiceNo: Optional[str] = ""
    DONumber: Optional[str] = "" 
    ItemName: Optional[str] = ""
    Qty: float
    UnitPrice: float
    OriginalTotal: float 
    ConvertedTotal: float 

class DOFilter(BaseModel):
    customerid: int
    gascodeid: Optional[int] = 0

class InvoiceListItem(BaseModel):
    InvoiceId: int
    InvoiceNbr: str
    Salesinvoicesdate: str
    CustomerName: str
    PONumber: Optional[str] = ""
    CurrencyCode: Optional[str] = ""
    TotalAmount: float
    CalculatedPrice: float
    Status: str
    DOnumber: Optional[str] = ""
    uomid: Optional[int] = 0  # Fixed: removed duplicate PONumber field

class InvoiceItemDetail(BaseModel):
    Id: int
    gascodeid: int
    GasName: Optional[str] = ""
    PickedQty: float
    UnitPrice: float
    TotalPrice: float
    Currencyid: int
    ExchangeRate: float
    Price: float = 0.0
    DOnumber: Optional[str] = ""
    PONumber: Optional[str] = ""
    uomid: Optional[int] = 0
    Note: Optional[str] = ""
    sellingPrice: Optional[float] = 0.0
    sellingTotal: Optional[float] = 0.0

class InvoiceFullDetail(BaseModel):
    InvoiceId: int
    InvoiceNbr: str
    Salesinvoicesdate: str
    CustomerName: str
    customerid: int
    TotalAmount: float
    CalculatedPrice: float
    Status: str
    PONumber: Optional[str] = ""
    Items: List[InvoiceItemDetail] = []

class ConvertDORequest(BaseModel):
    customerid: int
    do_ids: List[int]
    created_by: int = 1

# ==========================================
# 2. REQUEST MODELS
# ==========================================

class ManualInvoiceDetail(BaseModel):
    gasCodeId: int 
    pickedQty: float
    UnitPrice: float
    CurrencyId: int
    UomId: Optional[int] = 0
    poNumber: Optional[str] = ""
    doNumber: Optional[str] = ""
    driverName: Optional[str] = ""
    truckName: Optional[str] = ""
    deliveryAddress: Optional[str] = ""
    ExchangeRate: Optional[float] = 1.0
    Note: Optional[str] = ""
    sellingPrice: Optional[float] = 0.0
    sellingTotal: Optional[float] = 0.0
    commissions: Optional[List[dict]] = []
    
    class Config:
        extra = "ignore"

class ManualInvoiceHeader(BaseModel):
    id: Optional[int] = 0
    customerId: int
    salesInvoiceDate: str
    salesInvoiceNbr: str 
    userId: int = 1
    orgId: int = 1
    branchId: int = 1
    isSubmitted: int = 0
    ismanual: int = 1
    
    class Config:
        extra = "ignore"

class CreateInvoiceRequest(BaseModel):
    header: ManualInvoiceHeader
    details: List[ManualInvoiceDetail]
    
    class Config:
        extra = "ignore"

class UpdateInvoiceRequest(BaseModel):
    command: str
    header: ManualInvoiceHeader
    details: List[ManualInvoiceDetail]
    doDetail: List[dict] = [] 

# ==========================================
# 3. API ENDPOINTS
# ==========================================

# --- Create Manual Invoice ---
@router.post("/CreateInvoice")
async def create_invoice(payload: CreateInvoiceRequest):
    async with engine.begin() as conn: 
        try:
            # 🟢 [FIX] Disable FK Checks for Cross-DB Reference
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))

            # [FIX 1] Check for Duplicate Invoice Number
            if payload.header.salesInvoiceNbr:
                dup_check = text("CALL proc_DSI_CheckDuplicate(:nbr, 0)")
                dup_res = await conn.execute(dup_check, {"nbr": payload.header.salesInvoiceNbr})
                if dup_res.scalar() > 0:
                     raise HTTPException(status_code=400, detail=f"Invoice Number '{payload.header.salesInvoiceNbr}' already exists.")

            # 1. Create Header
            header_query = text(f"""
                INSERT INTO {DB_NAME_USER}.tbl_salesinvoices_header 
                (salesinvoicenbr, customerid, Salesinvoicesdate, TotalAmount, IsSubmitted, CalculatedPrice, createdby, OrgId, BranchId, IsManual, CreatedDate, isactive)
                VALUES (:nbr, :cust, :date, 0, :submitted, 0, :user, :org, :branch, :manual, NOW(), 1)
            """)
            
            result = await conn.execute(header_query, {
                "nbr": payload.header.salesInvoiceNbr, 
                "cust": payload.header.customerId,
                "date": payload.header.salesInvoiceDate,
                "submitted": payload.header.isSubmitted,
                "user": payload.header.userId,
                "org": payload.header.orgId,
                "branch": payload.header.branchId,
                "manual": payload.header.ismanual
            })
            new_header_id = result.lastrowid

            total_header_amount = 0.0
            total_calculated_price_idr = 0.0

            # 2. Process Details
            for item in payload.details:
                # A. Get Rate
                rate_query = text("CALL proc_DSI_GetExchangeRate(:cid)")
                cid = item.CurrencyId if item.CurrencyId else 1
                rate_result = await conn.execute(rate_query, {"cid": cid})
                exchange_rate = rate_result.scalar() or 1.0

                # [FIX 3] Rounding Calculations to 2 decimal places
                line_total = round(item.pickedQty * item.UnitPrice, 2)
                line_calculated_price = round(line_total * float(exchange_rate), 2)

                total_header_amount += line_total
                total_calculated_price_idr += line_calculated_price

                # C. Insert Detail
                detail_query = text(f"""
                    INSERT INTO {DB_NAME_USER}.tbl_salesinvoices_details
                    (salesinvoicesheaderid, gascodeid, PickedQty, UnitPrice, TotalPrice, Price, Currencyid, ExchangeRate, uomid, DOnumber, PONumber, DriverName, TruckName, DeliveryAddress, Note, SellingPrice, SellingTotal)
                    VALUES (:hid, :gas, :qty, :price, :total, :calc_price, :cur, :rate, :uom, :do, :po, :driver, :truck, :addr, :note, :sp, :st)
                """)
                await conn.execute(detail_query, {
                    "hid": new_header_id,
                    "gas": item.gasCodeId,
                    "qty": item.pickedQty,
                    "price": item.UnitPrice,
                    "total": line_total,
                    "calc_price": line_calculated_price,
                    "cur": cid,
                    "rate": exchange_rate,
                    "uom": item.UomId,
                    "do": item.doNumber,
                    "po": item.poNumber,
                    "driver": item.driverName,
                    "truck": item.truckName,
                    "addr": item.deliveryAddress,
                    "note": item.Note,
                    "sp": item.sellingPrice,
                    "st": item.sellingTotal
                })

            # 3. Process Master Commission Persistence
            for item in payload.details:
                if item.commissions:
                    # A. Find or Create Master Header
                    find_header = text(f"""
                        SELECT Id FROM {DB_NAME_MASTER}.master_salesCommission_header
                        WHERE CustomerId = :cid AND GasId = :gid
                        ORDER BY EffectiveFrom DESC LIMIT 1
                    """)
                    hdr_res = await conn.execute(find_header, {"cid": payload.header.customerId, "gid": item.gasCodeId})
                    existing_hdr = hdr_res.fetchone()
                    
                    if existing_hdr:
                        master_id = existing_hdr[0]
                        update_hdr = text(f"""
                            UPDATE {DB_NAME_MASTER}.master_salesCommission_header
                            SET SellingPrice = :sp, LastModifiedBy = :user, LastModifiedDate = NOW()
                            WHERE Id = :mid
                        """)
                        await conn.execute(update_hdr, {"sp": item.sellingPrice, "user": payload.header.userId, "mid": master_id})
                        log_action = "UPDATE"
                    else:
                        insert_hdr = text(f"""
                            INSERT INTO {DB_NAME_MASTER}.master_salesCommission_header
                            (CustomerId, GasId, SellingPrice, EffectiveFrom, CreatedBy, CreatedDate)
                            VALUES (:cid, :gid, :sp, :eff, :user, NOW())
                        """)
                        res_hdr = await conn.execute(insert_hdr, {
                            "cid": payload.header.customerId,
                            "gid": item.gasCodeId,
                            "sp": item.sellingPrice,
                            "eff": payload.header.salesInvoiceDate,
                            "user": payload.header.userId
                        })
                        master_id = res_hdr.lastrowid
                        log_action = "CREATE"
                    
                    # B. Log Header
                    await conn.execute(text(f"""
                        INSERT INTO {DB_NAME_MASTER}.log_salesCommission_header
                        (Id, CustomerId, GasId, SellingPrice, EffectiveFrom, LogAction, LogDate, CreatedBy)
                        VALUES (:mid, :cid, :gid, :sp, :eff, :action, NOW(), :user)
                    """), {
                        "mid": master_id, "cid": payload.header.customerId, "gid": item.gasCodeId,
                        "sp": item.sellingPrice, "eff": payload.header.salesInvoiceDate,
                        "action": log_action, "user": payload.header.userId
                    })

                    # C. Sync Master Details
                    await conn.execute(text(f"DELETE FROM {DB_NAME_MASTER}.master_salesCommission_details WHERE SalesCommissionId = :mid"), {"mid": master_id})
                    
                    for comm in item.commissions:
                        await conn.execute(text(f"""
                            INSERT INTO {DB_NAME_MASTER}.master_salesCommission_details
                            (SalesCommissionId, Contact, Rate, Qty, CreatedBy, CreatedDate)
                            VALUES (:mid, :contact, :rate, :qty, :user, NOW())
                        """), {
                            "mid": master_id, "contact": comm.get("contactName", ""),
                            "rate": comm.get("rate", 0), "qty": comm.get("qty", 1),
                            "user": payload.header.userId
                        })
                        
                        # D. Log Details
                        await conn.execute(text(f"""
                            INSERT INTO {DB_NAME_MASTER}.log_salesCommission_details
                            (SalesCommissionId, Contact, Rate, Qty, LogAction, LogDate, CreatedBy)
                            VALUES (:mid, :contact, :rate, :qty, :action, NOW(), :user)
                        """), {
                            "mid": master_id, "contact": comm.get("contactName", ""),
                            "rate": comm.get("rate", 0), "qty": comm.get("qty", 1),
                            "action": log_action, "user": payload.header.userId
                        })

                    # 🟢 E. PERSIST IN InvoiceCommission (New Requirement)
                    for comm in item.commissions:
                        await conn.execute(text(f"""
                            INSERT INTO {DB_NAME_USER}.InvoiceCommission
                            (InvoiceId, CustomerId, ContactName, GasId, Rate, Total_Commission, Qty, CreatedDate)
                            VALUES (:hid, :cust, :cname, :gid, :rate, :total_comm, :qty, NOW())
                        """), {
                            "hid": new_header_id,
                            "cust": payload.header.customerId,
                            "cname": comm.get("contactName", ""),
                            "gid": item.gasCodeId,
                            "rate": comm.get("rate", 0),
                            "total_comm": comm.get("amount", 0),
                            "qty": item.pickedQty
                        })

            # 4. Update Header Totals
            update_header = text(f"""
                UPDATE {DB_NAME_USER}.tbl_salesinvoices_header
                SET TotalAmount = :total,
                    CalculatedPrice = :calc_price
                WHERE id = :hid
            """)
            await conn.execute(update_header, {
                "total": total_header_amount,
                "calc_price": total_calculated_price_idr,
                "hid": new_header_id
            })

            await conn.commit() 
            return {"status": "success", "message": "Invoice Created", "data": new_header_id, "InvoiceId": new_header_id}

        except HTTPException as he:
            raise he
        except Exception as e:
            print(f"Error creating invoice: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# --- Update Invoice ---
@router.post("/UpdateInvoice")
async def update_invoice(payload: UpdateInvoiceRequest):
    async with engine.begin() as conn:
        try:
            invoice_id = payload.header.id
            if not invoice_id:
                raise HTTPException(status_code=400, detail="Invoice ID required for update")

            # 🟢 [FIX] Disable FK Checks for Cross-DB Reference
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))

            # [FIX 1] Check for Duplicate Invoice Number (Excluding Current ID)
            if payload.header.salesInvoiceNbr:
                dup_check = text("CALL proc_DSI_CheckDuplicate(:nbr, :hid)")
                dup_res = await conn.execute(dup_check, {"nbr": payload.header.salesInvoiceNbr, "hid": invoice_id})
                if dup_res.scalar() > 0:
                     raise HTTPException(status_code=400, detail=f"Invoice Number '{payload.header.salesInvoiceNbr}' already exists.")

            # 1. Delete Existing Details
            await conn.execute(text("CALL proc_DSI_DeleteDetails(:hid)"), {"hid": invoice_id})

            # 🟢 [REMOVED] Global delete here to prevent data loss if processing fails later
            # await conn.execute(text(f"DELETE FROM {DB_NAME_USER}.InvoiceCommission WHERE InvoiceId = :hid"), {"hid": invoice_id})

            total_header_amount = 0.0
            total_calculated_price_idr = 0.0

            # 2. Insert New Details & Recalculate Totals
            for item in payload.details:
                # Get Rate
                rate_query = text("CALL proc_DSI_GetExchangeRate(:cid)")
                cid = item.CurrencyId if item.CurrencyId else 1
                rate_result = await conn.execute(rate_query, {"cid": cid})
                exchange_rate = rate_result.scalar() or 1.0

                # [FIX 3] Rounding Calculations
                line_total = round(float(item.pickedQty) * float(item.UnitPrice), 2)
                line_calculated_price = round(line_total * float(exchange_rate), 2)

                total_header_amount += line_total
                total_calculated_price_idr += line_calculated_price

                # Insert
                detail_query = text(f"""
                    INSERT INTO {DB_NAME_USER}.tbl_salesinvoices_details
                    (salesinvoicesheaderid, gascodeid, PickedQty, UnitPrice, TotalPrice, Price, Currencyid, ExchangeRate, uomid, DOnumber, PONumber, DriverName, TruckName, DeliveryAddress, Note, SellingPrice, SellingTotal)
                    VALUES (:hid, :gas, :qty, :price, :total, :calc_price, :cur, :rate, :uom, :do, :po, :driver, :truck, :addr, :note, :sp, :st)
                """)
                await conn.execute(detail_query, {
                    "hid": invoice_id,
                    "gas": item.gasCodeId,
                    "qty": item.pickedQty,
                    "price": item.UnitPrice,
                    "total": line_total,
                    "calc_price": line_calculated_price,
                    "cur": cid,
                    "rate": exchange_rate,
                    "uom": item.UomId,
                    "do": item.doNumber,
                    "po": item.poNumber,
                    "driver": item.driverName,
                    "truck": item.truckName,
                    "addr": item.deliveryAddress,
                    "note": item.Note,
                    "sp": item.sellingPrice,
                    "st": item.sellingTotal
                })

            # 3. Process Master Commission Persistence
            for item in payload.details:
                if item.commissions:
                    # A. Find or Create Master Header
                    find_header = text(f"""
                        SELECT Id FROM {DB_NAME_MASTER}.master_salesCommission_header
                        WHERE CustomerId = :cid AND GasId = :gid
                        ORDER BY EffectiveFrom DESC LIMIT 1
                    """)
                    hdr_res = await conn.execute(find_header, {"cid": payload.header.customerId, "gid": item.gasCodeId})
                    existing_hdr = hdr_res.fetchone()
                    
                    if existing_hdr:
                        master_id = existing_hdr[0]
                        update_hdr = text(f"""
                            UPDATE {DB_NAME_MASTER}.master_salesCommission_header
                            SET SellingPrice = :sp, LastModifiedBy = :user, LastModifiedDate = NOW()
                            WHERE Id = :mid
                        """)
                        await conn.execute(update_hdr, {"sp": item.sellingPrice, "user": payload.header.userId, "mid": master_id})
                        log_action = "UPDATE"
                    else:
                        insert_hdr = text(f"""
                            INSERT INTO {DB_NAME_MASTER}.master_salesCommission_header
                            (CustomerId, GasId, SellingPrice, EffectiveFrom, CreatedBy, CreatedDate)
                            VALUES (:cid, :gid, :sp, :eff, :user, NOW())
                        """)
                        res_hdr = await conn.execute(insert_hdr, {
                            "cid": payload.header.customerId,
                            "gid": item.gasCodeId,
                            "sp": item.sellingPrice,
                            "eff": payload.header.salesInvoiceDate,
                            "user": payload.header.userId
                        })
                        master_id = res_hdr.lastrowid
                        log_action = "CREATE"
                    
                    # B. Log Header
                    await conn.execute(text(f"""
                        INSERT INTO {DB_NAME_MASTER}.log_salesCommission_header
                        (Id, CustomerId, GasId, SellingPrice, EffectiveFrom, LogAction, LogDate, CreatedBy)
                        VALUES (:mid, :cid, :gid, :sp, :eff, :action, NOW(), :user)
                    """), {
                        "mid": master_id, "cid": payload.header.customerId, "gid": item.gasCodeId,
                        "sp": item.sellingPrice, "eff": payload.header.salesInvoiceDate,
                        "action": log_action, "user": payload.header.userId
                    })

                    # C. Sync Master Details
                    await conn.execute(text(f"DELETE FROM {DB_NAME_MASTER}.master_salesCommission_details WHERE SalesCommissionId = :mid"), {"mid": master_id})
                    
                    for comm in item.commissions:
                        await conn.execute(text(f"""
                            INSERT INTO {DB_NAME_MASTER}.master_salesCommission_details
                            (SalesCommissionId, Contact, Rate, Qty, CreatedBy, CreatedDate)
                            VALUES (:mid, :contact, :rate, :qty, :user, NOW())
                        """), {
                            "mid": master_id, "contact": comm.get("contactName", ""),
                            "rate": comm.get("rate", 0), "qty": comm.get("qty", 1),
                            "user": payload.header.userId
                        })
                        
                        # D. Log Details
                        await conn.execute(text(f"""
                            INSERT INTO {DB_NAME_MASTER}.log_salesCommission_details
                            (SalesCommissionId, Contact, Rate, Qty, LogAction, LogDate, CreatedBy)
                            VALUES (:mid, :contact, :rate, :qty, :action, NOW(), :user)
                        """), {
                            "mid": master_id, "contact": comm.get("contactName", ""),
                            "rate": comm.get("rate", 0), "qty": comm.get("qty", 1),
                            "action": log_action, "user": payload.header.userId
                        })

                    # 🟢 E. PERSIST IN InvoiceCommission (New Requirement)
                    # First, delete existing commissions for THIS specific item to allow for updates
                    await conn.execute(text(f"""
                        DELETE FROM {DB_NAME_USER}.InvoiceCommission 
                        WHERE InvoiceId = :hid AND GasId = :gid
                    """), {"hid": int(invoice_id), "gid": int(item.gasCodeId)})

                    for comm in item.commissions:
                        print(f"DEBUG: Inserting commission for Invoice {invoice_id}, Gas {item.gasCodeId}: {comm.get('contactName')}")
                        await conn.execute(text(f"""
                            INSERT INTO {DB_NAME_USER}.InvoiceCommission
                            (InvoiceId, CustomerId, ContactName, GasId, Rate, Total_Commission, Qty, CreatedDate)
                            VALUES (:hid, :cust, :cname, :gid, :rate, :total_comm, :qty, NOW())
                        """), {
                            "hid": int(invoice_id),
                            "cust": payload.header.customerId,
                            "cname": comm.get("contactName", ""),
                            "gid": int(item.gasCodeId),
                            "rate": comm.get("rate", 0),
                            "total_comm": comm.get("amount", 0),
                            "qty": item.pickedQty
                        })


            # 4. Update Header Totals
            update_header = text(f"""
                UPDATE {DB_NAME_USER}.tbl_salesinvoices_header
                SET TotalAmount = :total,
                    CalculatedPrice = :calc_price,
                    salesinvoicenbr = :nbr,
                    customerid = :cust,
                    Salesinvoicesdate = :date,
                    IsSubmitted = :submitted,
                    updatedby = :user,
                    LastModifiedDate = NOW()
                WHERE id = :hid
            """)
            
            await conn.execute(update_header, {
                "total": total_header_amount,
                "calc_price": total_calculated_price_idr,
                "nbr": payload.header.salesInvoiceNbr,
                "cust": payload.header.customerId,
                "date": payload.header.salesInvoiceDate,
                "user": payload.header.userId,
                "submitted": payload.header.isSubmitted,
                "hid": invoice_id
            })

            await conn.commit() 
            return {"status": True, "message": "Invoice updated successfully", "data": invoice_id}

        except HTTPException as he:
            raise he
        except Exception as e:
            print(f"Error updating invoice: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# --- Get All Invoices ---
@router.post("/GetALLInvoices", response_model=List[InvoiceListItem])
async def get_all_invoices(filter_data: InvoiceFilter):
    try:
        sql = text("CALL proc_DSI_GetAllInvoices(:from_date, :to_date, :customer_id, :is_ar)")

        async with engine.connect() as conn:
            result = await conn.execute(sql, {
                "from_date": filter_data.FromDate,
                "to_date": filter_data.ToDate,
                "customer_id": filter_data.customerid,
                "is_ar": filter_data.IsAR
            })
            
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]

    except Exception as e:
        print(f"Error fetching invoices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/GetInvoiceDetails", response_model=InvoiceFullDetail)
async def get_invoice_details(invoiceid: str):
    try:
        async with engine.connect() as conn:
            # 1. Fetch ALL matching Headers (to handle consolidated DOs sharing one number)
            header_query = text("CALL proc_DSI_GetHeader(:input_val)")
            result = await conn.execute(header_query, {"input_val": invoiceid})
            header_rows = result.mappings().all()
            
            if not header_rows:
                raise HTTPException(status_code=404, detail=f"Invoice '{invoiceid}' not found")

            # Initialize aggregated header with the first row's primary data
            first_row = dict(header_rows[0])
            aggregated_header = {
                "InvoiceId": first_row["InvoiceId"],
                "InvoiceNbr": first_row["InvoiceNbr"],
                "Salesinvoicesdate": first_row["Salesinvoicesdate"],
                "CustomerName": first_row["CustomerName"],
                "customerid": first_row["customerid"],
                "TotalAmount": sum(float(h["TotalAmount"] or 0) for h in header_rows),
                "CalculatedPrice": sum(float(h["CalculatedPrice"] or h["TotalAmount"] or 0) for h in header_rows),
                "Status": first_row["Status"],
                "PONumber": "", 
                "Items": []
            }

            all_items = []
            
            # 2. Fetch Details for ALL linked Headers
            for h in header_rows:
                hid = h["InvoiceId"]
                detail_query = text("CALL proc_DSI_GetDetails(:hid)")
                details_result = await conn.execute(detail_query, {"hid": hid})
                details_rows = details_result.fetchall()

                # Fetch commissions for this specific hid
                all_comm_query = text(f"""
                    SELECT ic.GasId, ic.ContactName as contactName, ic.Rate as rate, ic.Qty as qty, ic.Total_Commission as amount
                    FROM {DB_NAME_USER}.InvoiceCommission ic
                    WHERE ic.InvoiceId = :hid
                """)
                all_comm_res = await conn.execute(all_comm_query, {"hid": hid})
                all_comm_rows = all_comm_res.mappings().all()
                
                # Create a lookup map for commissions by GasId
                comm_map = {}
                for c in all_comm_rows:
                    c_dict = dict(c)
                    try:
                        gid_val = c_dict.get("GasId") or c_dict.get("gasid") or c_dict.get("gasId")
                        if gid_val is not None:
                            gid = int(gid_val)
                            if gid not in comm_map:
                                comm_map[gid] = []
                            comm_map[gid].append(c_dict)
                    except: continue

                for row in details_rows:
                    row_dict = dict(row._mapping)
                    gid_raw = row_dict.get("gascodeid") or row_dict.get("GasCodeId") or row_dict.get("GasId") or row_dict.get("id")
                    gid = int(gid_raw) if gid_raw else 0
                    
                    # Assign commissions from our map
                    item_comms = comm_map.get(gid, [])
                    row_dict["commissions"] = item_comms
                    
                    # Calculate sums for synchronization if not already present
                    rate_sum = sum(float(c.get("rate") or 0) for c in item_comms)
                    amt_sum = sum(float(c.get("amount") or 0) for c in item_comms)
                    
                    row_dict["SellingPrice"] = float(row_dict.get("SellingPrice") or row_dict.get("sellingPrice") or rate_sum)
                    row_dict["SellingTotal"] = float(row_dict.get("SellingTotal") or row_dict.get("sellingTotal") or amt_sum)
                    
                    # Backward compatibility for frontend
                    row_dict["sellingPrice"] = row_dict["SellingPrice"]
                    row_dict["sellingTotal"] = row_dict["SellingTotal"]
                    
                    # Capture PO Number for the header if we find one in any detail row
                    if row_dict.get("PONumber") and not aggregated_header["PONumber"]:
                        aggregated_header["PONumber"] = row_dict["PONumber"]
                    
                    all_items.append(row_dict)

            aggregated_header["Items"] = all_items
            # 🟢 [LAZY SYNC] Ensure AR record has invoice_id for future renames
            try:
                ar_check_sql = text(f"""
                    SELECT ar_id FROM {DB_NAME_FINANCE}.tbl_accounts_receivable 
                    WHERE (invoice_no = :nbr COLLATE utf8mb4_general_ci) AND (invoice_id IS NULL OR invoice_id = 0)
                    AND is_active = 1 LIMIT 1
                """)
                ar_res = await conn.execute(ar_check_sql, {"nbr": aggregated_header["InvoiceNbr"]})
                ar_row = ar_res.mappings().first()
                if ar_row:
                    print(f"Lazy syncing ID {invoiceid} to AR record {ar_row['ar_id']}")
                    update_ar_id_sql = text(f"UPDATE {DB_NAME_FINANCE}.tbl_accounts_receivable SET invoice_id = :hid WHERE ar_id = :aid")
                    await conn.execute(update_ar_id_sql, {"hid": invoiceid, "aid": ar_row["ar_id"]})
                    # Commit if we are on a connection that supports it
                    if hasattr(conn, "commit"):
                        await conn.commit()
            except Exception as lazy_e:
                print(f"Lazy Sync failed (non-critical): {lazy_e}")

            return aggregated_header

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error fetching invoice {invoiceid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Get Available DOs ---
@router.post("/GetAvailableDOs")
async def get_available_dos(filter_data: DOFilter):
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DSI_GetAvailableDOs(:cust_id)")
            
            result = await conn.execute(query, {
                "cust_id": filter_data.customerid
            })
            
            rows = result.fetchall()
            return {"status": True, "data": [dict(row._mapping) for row in rows]}

    except Exception as e:
        print(f"Error fetching DOs: {e}")
        return {"status": False, "message": str(e), "data": []}

# --- Create Invoice From DO ---
@router.post("/CreateInvoiceFromDO")
async def create_invoice_from_do(payload: ConvertDORequest):
    async with engine.begin() as conn:
        try:
            if not payload.do_ids:
                 raise HTTPException(status_code=400, detail="No DOs selected")

            # 🟢 [FIX] Disable FK Checks for Cross-DB Reference
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))

            # 1. [FIX 2] CHECK IF ANY DO IS ALREADY CONVERTED
            # Logic: Look for any active invoice details that reference these DO Numbers
            for do_id in payload.do_ids:
                # Get the DO Number String first
                do_num_q = text("CALL proc_DSI_GetDONumberString(:doid)")
                do_res = await conn.execute(do_num_q, {"doid": do_id})
                do_num_str = do_res.scalar()

                if do_num_str:
                    # Check if this string exists in any ACTIVE invoice's details
                    check_do_q = text("CALL proc_DSI_CheckDOConverted(:do_num, :do_id)")
                    check_res = await conn.execute(check_do_q, {"do_num": do_num_str, "do_id": do_id})
                    existing_inv = check_res.scalar()
                    
                    if existing_inv:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"DO '{do_num_str}' is already linked to Invoice '{existing_inv}'. Cannot convert again."
                        )

            # 2. Create Invoice Header
            header_query = text(f"""
                INSERT INTO {DB_NAME_USER}.tbl_salesinvoices_header 
                (customerid, Salesinvoicesdate, TotalAmount, IsSubmitted, CalculatedPrice, createdby, invoice_type, isactive, CreatedDate)
                VALUES (:cust, CURDATE(), 0, 0, 0, :user, 'DSI', 1, NOW())
            """)
            result = await conn.execute(header_query, {
                "cust": payload.customerid,
                "user": payload.created_by
            })
            new_invoice_id = result.lastrowid

            total_amount = 0.0
            total_calculated_price = 0.0

            # 3. Process selected DOs
            for do_id in payload.do_ids:
                do_header_query = text("CALL proc_DSI_GetDONumberString(:doid)")
                do_header_res = await conn.execute(do_header_query, {"doid": do_id})
                do_number_str = do_header_res.scalar() or ""

                do_details_query = text("CALL proc_DSI_GetDODetailsForConvert(:doid)")
                do_res = await conn.execute(do_details_query, {"doid": do_id})
                do_rows = do_res.fetchall()
                
                for row in do_rows:
                    rate_val = float(row.ExchangeRate or 1.0)
                    
                    # [FIX 3] Rounding
                    line_total = round(row.PickedQty * row.UnitPrice, 2)
                    line_calc_price = round(line_total * rate_val, 2)
                    
                    total_amount += line_total
                    total_calculated_price += line_calc_price
                    
                    # C. Insert Detail
                    det_query = text(f"""
                        INSERT INTO {DB_NAME_USER}.tbl_salesinvoices_details
                        (salesinvoicesheaderid, gascodeid, PickedQty, UnitPrice, TotalPrice, Price, Currencyid, ExchangeRate, uomid, DOnumber, Note, SellingPrice, SellingTotal)
                        VALUES (:hid, :gas, :qty, :price, :total, :calc_price, :cur, :rate, :uom, :do_str, '', :sp, :st)
                    """)
                    await conn.execute(det_query, {
                        "hid": new_invoice_id,
                        "gas": row.gascodeid,
                        "qty": row.PickedQty,
                        "price": row.UnitPrice,
                        "total": line_total,
                        "calc_price": line_calc_price,
                        "cur": row.Currencyid,
                        "rate": rate_val,
                        "uom": row.uomid,
                        "do_str": do_number_str,
                        "sp": row.SellingPrice,
                        "st": row.SellingTotal
                    })

                    # 🟢 D. Copy Commissions from DO to InvoiceCommission
                    copy_comm_query = text(f"""
                        INSERT INTO {DB_NAME_USER}.InvoiceCommission
                        (InvoiceId, CustomerId, ContactName, GasId, Rate, Total_Commission, Qty, CreatedDate)
                        SELECT :new_hid, CustomerId, ContactName, GasId, Rate, Total_Commission, Qty, NOW()
                        FROM {DB_NAME_USER}.InvoiceCommission
                        WHERE InvoiceId = :old_hid AND GasId = :gid
                    """)
                    await conn.execute(copy_comm_query, {
                        "new_hid": new_invoice_id,
                        "old_hid": do_id,
                        "gid": row.gascodeid
                    })

            # 4. Update Header Totals
            update_header = text(f"""
                UPDATE {DB_NAME_USER}.tbl_salesinvoices_header
                SET TotalAmount = :total, CalculatedPrice = :calc_total
                WHERE id = :hid
            """)
            await conn.execute(update_header, {
                "total": total_amount, 
                "calc_total": total_calculated_price,
                "hid": new_invoice_id
            })

            await conn.commit() 
            return {"status": True, "message": "Invoice Created Successfully", "InvoiceId": new_invoice_id}

        except HTTPException as he:
            raise he
        except Exception as e:
            print(f"Error converting DO: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# --- Get Gas Items ---
@router.get("/GetGasItems")
async def get_gas_items():
    try:
        async with engine.connect() as conn:
            query = text("CALL proc_DSI_GetGasItems()")
            result = await conn.execute(query)
            rows = result.fetchall()
            return {"status": True, "data": [dict(row._mapping) for row in rows]}

    except Exception as e:
        print(f"Error fetching gas items: {e}")
        return {"status": False, "message": str(e), "data": []}

# --- Get Sales Commission ---
@router.get("/GetSalesCommission")
async def get_sales_commission(customerId: int, gasId: int, invoiceDate: str):
    try:
        async with engine.connect() as conn:
            # 1. Fetch the master header for the specific customer and gas code, effective as of the invoice date
            header_query = text(f"""
                SELECT Id, SellingPrice, EffectiveFrom
                FROM {DB_NAME_MASTER}.master_salesCommission_header
                WHERE CustomerId = :cid AND GasId = :gid AND EffectiveFrom <= :invdate
                ORDER BY EffectiveFrom DESC
                LIMIT 1
            """)
            
            result = await conn.execute(header_query, {
                "cid": customerId,
                "gid": gasId,
                "invdate": invoiceDate
            })
            
            header = result.first()
            if not header:
                return {
                    "found": False,
                    "sellingPrice": 0,
                    "commissions": []
                }
                
            header_id = header[0]
            selling_price = header[1]
            effective_from = header[2]
            
            # 2. Fetch the associated commission details
            details_query = text(f"""
                SELECT Id, Contact, Rate, Qty
                FROM {DB_NAME_MASTER}.master_salesCommission_details
                WHERE SalesCommissionId = :hcid
            """)
            
            details_result = await conn.execute(details_query, {"hcid": header_id})
            details_rows = details_result.fetchall()
            
            commissions = []
            for row in details_rows:
                commissions.append({
                    "contactId": row[0],
                    "contactName": row[1] or "",
                    "rate": float(row[2]) if row[2] else 0.0,
                    "qty": float(row[3]) if row[3] else 1.0
                })
                
            return {
                "found": True,
                "sellingPrice": float(selling_price) if selling_price else 0.0,
                "effectiveFrom": str(effective_from),
                "commissions": commissions
            }
            
    except Exception as e:
        print(f"Error fetching sales commission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Get Sales Details (Reports) ---
@router.post("/GetSalesDetails", response_model=List[SalesReportItem])
async def get_sales_details(filter_data: InvoiceFilter):
    try:
        sql = text("CALL proc_DSI_GetSalesDetails(:from_date, :to_date, :cust_id, :item_id, :sp_id)")

        async with engine.connect() as conn:
            result = await conn.execute(sql, {
                "from_date": filter_data.FromDate,
                "to_date": filter_data.ToDate,
                "cust_id": filter_data.customerid,
                "item_id": filter_data.ItemId,
                "sp_id": filter_data.SalesPersonId 
            })
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]

    except Exception as e:
        print(f"Error fetching sales details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/GetItemFilter")
async def get_item_filter():
    try:
        sql = text("CALL proc_DSI_GetItemFilter()")
        async with engine.connect() as conn:
            result = await conn.execute(sql)
            return [dict(row._mapping) for row in result.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))