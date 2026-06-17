from sqlalchemy import text
import re
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Union, Optional
from . import schemas
from .models.finance import ARReceipt
from sqlalchemy import select, desc, update
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# --- UPDATED DEFAULTS TO LIVE DATABASES ---
DB_NAME_FINANCE = os.getenv('DB_NAME_FINANCE', 'btggasify_finance_live')
DB_NAME_USER = os.getenv('DB_NAME_USER', 'btggasify_live')
DB_NAME_USER_NEW = os.getenv('DB_NAME_USER_NEW', 'btggasify_userpanel_live')
DB_NAME_MASTER = os.getenv('DB_NAME_MASTER', 'btggasify_masterpanel_live')

# ----------------------------------------------------------
# 1. CREATE AR RECEIPT
# ----------------------------------------------------------
async def create_ar_receipt(db: AsyncSession, command: schemas.CreateARCommand):
    created_records = []
    
    for item in command.header:
        is_cleared_status = False
        if item.deposit_bank_id and str(item.deposit_bank_id) != "0" and str(item.deposit_bank_id).strip() != "":
            is_cleared_status = True

        # --- WORKFLOW LOGIC ---
        is_posted = item.is_posted
        
        # Only 'Receipt' type goes to Marketing Verification
        is_receipt = (item.transaction_type == 'Receipt')
        
        pending_verification = (is_posted and is_receipt)
        is_submitted = (is_posted and not is_receipt)

        if item.transaction_type == 'Bank transfer':
            # 1. Source Bank (Outflow -> Negative)
            cash_amount = -abs(item.cash_amount) if item.cash_amount else 0
            bank_amount = -abs(item.bank_amount) if item.bank_amount else 0
            
            # 2. Destination Bank (Inflow -> Positive)
            b_cash_amount = abs(item.cash_amount) if item.cash_amount else 0
            b_bank_amount = abs(item.bank_amount) if item.bank_amount else 0
            
            dest_deposit_bank_id = str(item.customer_id) if item.customer_id else "0"
            dest_customer_id = int(item.deposit_bank_id) if item.deposit_bank_id and str(item.deposit_bank_id).isdigit() else 0
            
            is_cleared_status_b = False
            if dest_deposit_bank_id and dest_deposit_bank_id != "0" and dest_deposit_bank_id.strip() != "":
                is_cleared_status_b = True

            record_a = ARReceipt(
                orgid=command.orgId, branchid=command.branchId, created_by=str(command.userId),
                created_ip=command.userIp, receipt_date=item.receipt_date,
                customer_id=item.customer_id, transaction_type=item.transaction_type,
                bank_amount=bank_amount, bank_charges=item.bank_charges,
                deposit_bank_id=str(item.deposit_bank_id), reference_no=item.reference_no,
                sales_person_id=item.sales_person_id, send_notification=item.send_notification,
                cash_amount=cash_amount, bank_payment_via=item.bank_payment_via,
                cheque_number=item.cheque_number, is_posted=is_posted,
                pending_verification=pending_verification, is_submitted=is_submitted,
                flag=is_cleared_status, is_cleared=is_cleared_status, is_active=True
            )
            
            record_b = ARReceipt(
                orgid=command.orgId, branchid=command.branchId, created_by=str(command.userId),
                created_ip=command.userIp, receipt_date=item.receipt_date,
                customer_id=dest_customer_id, transaction_type=item.transaction_type,
                bank_amount=b_bank_amount, bank_charges=item.bank_charges,
                deposit_bank_id=dest_deposit_bank_id, reference_no=item.reference_no,
                sales_person_id=item.sales_person_id, send_notification=item.send_notification,
                cash_amount=b_cash_amount, bank_payment_via=item.bank_payment_via,
                cheque_number=item.cheque_number, is_posted=is_posted,
                pending_verification=pending_verification, is_submitted=is_submitted,
                flag=is_cleared_status_b, is_cleared=is_cleared_status_b, is_active=True
            )
            
            db.add(record_a)
            db.add(record_b)
            await db.flush()
            
            record_a.linked_receipt_id = record_b.receipt_id
            record_b.linked_receipt_id = record_a.receipt_id
            created_records.extend([record_a, record_b])
        elif item.transaction_type == 'Cash Deposit':
            amt = abs(item.bank_amount) if item.bank_amount else (abs(item.cash_amount) if item.cash_amount else 0)
            cash_amount = -amt
            bank_amount = amt
            
            db_receipt = ARReceipt(
                orgid=command.orgId,
                branchid=command.branchId,
                created_by=str(command.userId),
                created_ip=command.userIp,
                receipt_date=item.receipt_date, 
                customer_id=0,
                transaction_type=item.transaction_type,
                bank_amount=bank_amount,
                bank_charges=item.bank_charges,
                deposit_bank_id=str(item.deposit_bank_id),
                reference_no=item.reference_no,
                sales_person_id=item.sales_person_id,
                send_notification=item.send_notification,
                cash_amount=cash_amount,
                bank_payment_via=4,
                cheque_number=item.cheque_number,
                is_posted=is_posted,
                pending_verification=pending_verification, 
                is_submitted=is_submitted,
                flag=is_cleared_status, 
                is_cleared=is_cleared_status,
                is_active=True,
            )
            db.add(db_receipt)
            created_records.append(db_receipt)
        else:
            db_receipt = ARReceipt(
                orgid=command.orgId,
                branchid=command.branchId,
                created_by=str(command.userId),
                created_ip=command.userIp,
                
                # 🟢 FIX: Use the User-Selected Date (Transaction Date), NOT Today's Date
                receipt_date=item.receipt_date, 
                
                customer_id=item.customer_id,
                transaction_type=item.transaction_type,
                bank_amount=item.bank_amount,
                bank_charges=item.bank_charges,
                deposit_bank_id=str(item.deposit_bank_id),
                
                # New Fields
                reference_no=item.reference_no,
                sales_person_id=item.sales_person_id,
                send_notification=item.send_notification,
    
                # 🟢 Persist Cash/Cheque/Via
                cash_amount=item.cash_amount,
                bank_payment_via=item.bank_payment_via,
                cheque_number=item.cheque_number,
                
                # --- STATUS FLAGS ---
                is_posted=is_posted,
                pending_verification=pending_verification, 
                is_submitted=is_submitted,
                
                # ... other fields ...
                flag=is_cleared_status, 
                is_cleared=is_cleared_status,
                is_active=True,
                
            )
            db.add(db_receipt)
            created_records.append(db_receipt)

    await db.commit()
    for record in created_records:
        await db.refresh(record)
    return created_records

# ----------------------------------------------------------
# 2. GET PENDING LIST
# ----------------------------------------------------------
async def get_pending_bank_books(db: AsyncSession):
    stmt = (
        select(ARReceipt)
        .where(ARReceipt.pending_verification == True)
        .order_by(desc(ARReceipt.receipt_id))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------------------------------------
# 3. GET RECEIPT BY ID
# ----------------------------------------------------------
async def get_receipt_by_id(db: AsyncSession, receipt_id: int):
    stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
    result = await db.execute(stmt)
    return result.scalars().first()


# ----------------------------------------------------------
# 4. UPDATE CUSTOMER + VERIFY
# ----------------------------------------------------------
async def update_customer_and_verify(
    db: AsyncSession, 
    receipt_id: int, 
    data: schemas.VerifyCustomerUpdate
):
    # 1. Fetch the Receipt
    stmt = select(ARReceipt).where(
        ARReceipt.receipt_id == receipt_id,
        ARReceipt.pending_verification == True
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        return None 

    # 2. Update Receipt Details
    if data.customer_id and data.customer_id != 0:
        record.customer_id = data.customer_id
    
    record.bank_charges = data.bank_charges
    record.tax_rate = data.tax_deduction 
    record.exchange_rate = data.exchange_rate
    # 3. PROCESS ALLOCATIONS (Idempotent)
    linked_invoices = await _process_receipt_allocations(db, record, data)

    # 4. Update Description / Reference
    await _update_receipt_reference(record, data.reply_message, linked_invoices)

    record.pending_verification = False
    record.modified_on = datetime.now()

    await db.commit()
    await db.refresh(record)

    return record


# ----------------------------------------------------------
# 5. GET VERIFIED UNSUBMITTED
# ----------------------------------------------------------
async def get_verified_unsubmitted_books(db: AsyncSession):
    stmt = (
        select(ARReceipt)
        .where(
            ARReceipt.pending_verification == False,
            ARReceipt.is_submitted == False
        )
        .order_by(desc(ARReceipt.receipt_id))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ----------------------------------------------------------
# 6. SUBMIT RECEIPT
# ----------------------------------------------------------
async def finalize_receipt_and_update_ref(db: AsyncSession, receipt_id: int):
    """Final Step: Set is_submitted=True and append linked invoices to description."""
    try:
        # 1. Fetch the Receipt
        stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return False

        # 2. Get Linked Invoices from the allocation table (Raw SQL for robustness)
        get_inv_sql = text(f"""
            SELECT DISTINCT ar.invoice_no 
            FROM {DB_NAME_FINANCE}.tbl_receipt_ag_ar ra
            JOIN {DB_NAME_FINANCE}.tbl_accounts_receivable ar ON ra.ar_id = ar.ar_id
            WHERE ra.receipt_id = :rid AND ra.is_active = 1
        """)
        inv_res = await db.execute(get_inv_sql, {"rid": receipt_id})
        rows = inv_res.fetchall()
        linked_invoices = [str(row[0]) for row in rows if row[0]]
        
        # Log for debugging (will show in terminal)
        print(f"DEBUG Step 3: rid={receipt_id}, found_invoices={linked_invoices}")

        # 3. Update Reference with the actual linked invoices
        await _update_receipt_reference(record, None, linked_invoices)

        # 4. Finalize status (in object)
        record.is_submitted = True
        record.pending_verification = False
        
        # 5. Backup robust update (in case ORM sync has issues)
        final_ref = record.reference_no
        print(f"DEBUG Step 3: rid={receipt_id}, final_ref='{final_ref}'")
        
        update_sql = text(f"""
            UPDATE {DB_NAME_FINANCE}.tbl_ar_receipt 
            SET reference_no = :ref, is_submitted = 1, is_posted = 1, pending_verification = 0, updated_date = NOW()
            WHERE receipt_id = :rid
        """)
        await db.execute(update_sql, {"ref": final_ref, "rid": receipt_id})

        await db.commit()
        return True
    except Exception as e:
        import traceback
        print(f"Error finalizing receipt {receipt_id}: {e}")
        traceback.print_exc()
        await db.rollback()
        return False


# ----------------------------------------------------------
# 6. Post to AR (UPSERT & AGGREGATE LOGIC)
# ----------------------------------------------------------
async def post_invoice_to_ar(db: AsyncSession, request: schemas.PostInvoiceToARRequest):
    try:
        # 1. Fetch Invoice Number (Trimmed)
        get_nbr_sql = text("CALL proc_DSI_GetDONumberString(:inv_id)")
        # Explicit integer casting to avoid mismatch
        nbr_res = await db.execute(get_nbr_sql, {"inv_id": int(request.invoiceId)})
        invoice_number = nbr_res.scalar()

        if not invoice_number:
            print(f"ERROR: Invoice No not found for ID {request.invoiceId}")
            return False
            
        invoice_number = invoice_number.strip()

        # 2. Fetch Aggregated Totals
        sum_sql = text("CALL proc_CRUD_GetInvoiceGrandTotal(:nbr)")
        sum_res = await db.execute(sum_sql, {"nbr": invoice_number})
        totals = sum_res.mappings().first()
        
        if not totals:
            print(f"ERROR: No items found for Invoice {invoice_number}")
            return False

        grand_total = totals["GrandTotal"] or 0
        grand_total_idr = totals["GrandTotalIDR"] or 0
        primary_id = totals["PrimaryID"] or request.invoiceId

        # 3. Check for existence in AR (using both number and ID to detect renames)
        check_sql = text("CALL proc_CRUD_CheckExistingAR(:nbr, :inv_id, :old_nbr)")
        result = await db.execute(check_sql, {
            "nbr": invoice_number, 
            "inv_id": int(request.invoiceId),
            "old_nbr": request.oldInvoiceNumber
        })
        existing_row = result.mappings().first()

        if existing_row:
            # --- UPDATE SCENARIO ---
            ar_id = existing_row["ar_id"]
            print(f"Aggregating AR record for Invoice No: {invoice_number}. New Total: {grand_total}")
            update_ar_sql = text("CALL proc_CRUD_UpdateARSum(:nbr, :total, :total_idr, :userId, :inv_id, :ar_id)")
            await db.execute(update_ar_sql, {
                "nbr": invoice_number,
                "total": grand_total,
                "total_idr": grand_total_idr,
                "userId": str(request.userId),
                "inv_id": int(request.invoiceId),
                "ar_id": ar_id
            })
        else:
            # --- INSERT SCENARIO ---
            print(f"Inserting new AR record for Invoice No: {invoice_number}")
            insert_sql = text("CALL proc_CRUD_InsertARFromInvoice(:orgId, :branchId, :userId, :inv_id, :primary_id, :total, :total_idr)")
            await db.execute(insert_sql, {
                "orgId": request.orgId, 
                "branchId": request.branchId, 
                "userId": str(request.userId), 
                "inv_id": int(request.invoiceId),
                "primary_id": int(primary_id),
                "total": grand_total,
                "total_idr": grand_total_idr
            })

        # 4. Cleanup & Secondary Operations
        print(f"DEBUG: Deactivating old DOs for InvID {request.invoiceId}")
        deactivate_dos_sql = text("CALL proc_CRUD_DeactivateOldDOsInAR(:inv_id, :inv_no)")
        await db.execute(deactivate_dos_sql, {"inv_id": int(request.invoiceId), "inv_no": invoice_number})

        print(f"DEBUG: Marking header as AR for InvID {request.invoiceId}")
        update_header_flag_sql = text("CALL proc_CRUD_MarkHeaderAsAR(:inv_id)")
        await db.execute(update_header_flag_sql, {"inv_id": int(request.invoiceId)})

        print(f"DEBUG: Committing AR Posting for {invoice_number}")
        await db.commit()
        return True

    except Exception as e:
        # LOG THE ACTUAL ERROR FOR DEBUGGING
        print(f"CRITICAL ERROR in post_invoice_to_ar: {str(e)}")
        await db.rollback()
        return False

# ----------------------------------------------------------
# 7. UPDATE AR RECEIPT
# ----------------------------------------------------------
async def update_ar_receipt(db: AsyncSession, command: schemas.CreateARCommand):
    updated_count = 0
    
    for item in command.header:
        is_cleared_status = False
        if item.deposit_bank_id and str(item.deposit_bank_id) != "0" and str(item.deposit_bank_id).strip() != "":
            is_cleared_status = True

        is_posted = item.is_posted
        pending_verification = True if is_posted else False

        if item.transaction_type == 'Bank transfer':
            cash_amount = -abs(item.cash_amount) if item.cash_amount else 0
            bank_amount = -abs(item.bank_amount) if item.bank_amount else 0
        elif item.transaction_type == 'Cash Deposit':
            amt = abs(item.bank_amount) if item.bank_amount else (abs(item.cash_amount) if item.cash_amount else 0)
            cash_amount = -amt
            bank_amount = amt
        else:
            cash_amount = item.cash_amount
            bank_amount = item.bank_amount

        values_to_update = {
            "customer_id": item.customer_id,
            "bank_amount": bank_amount,
            "cash_amount": cash_amount,
            "contra_amount": item.contra_amount,
            "bank_charges": item.bank_charges,
            "tax_rate": item.tax_rate,
            "deposit_bank_id": str(item.deposit_bank_id),
            "deposit_account_number": item.deposit_account_number,
            "cheque_number": item.cheque_number,
            "giro_number": item.giro_number,
            "bank_payment_via": item.bank_payment_via,
            "reference_no": item.reference_no,
            "sales_person_id": item.sales_person_id,
            "send_notification": item.send_notification,
            "is_posted": is_posted,
            "pending_verification": pending_verification,
            "flag": is_cleared_status,
            "is_cleared": is_cleared_status,
            "proof_missing": item.proof_missing,
            "contra_reference": item.contra_reference,
            "receipt_date": item.receipt_date
        }

        stmt = (
            update(ARReceipt)
            .where(ARReceipt.receipt_id == item.receipt_id)
            .values(**values_to_update)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(stmt)
        updated_count += result.rowcount

        # 🟢 SYNCHRONIZE LINKED RECEIPT IF IT'S A BANK TRANSFER
        if item.transaction_type == 'Bank transfer':
            select_stmt = select(ARReceipt.linked_receipt_id).where(ARReceipt.receipt_id == item.receipt_id)
            linked_res = await db.execute(select_stmt)
            linked_id = linked_res.scalar_one_or_none()
            
            if linked_id:
                b_cash_amount = abs(item.cash_amount) if item.cash_amount else 0
                b_bank_amount = abs(item.bank_amount) if item.bank_amount else 0
                dest_deposit_bank_id = str(item.customer_id) if item.customer_id else "0"
                dest_customer_id = int(item.deposit_bank_id) if item.deposit_bank_id and str(item.deposit_bank_id).isdigit() else 0
                
                is_cleared_status_b = False
                if dest_deposit_bank_id and str(dest_deposit_bank_id) != "0" and str(dest_deposit_bank_id).strip() != "":
                    is_cleared_status_b = True
                    
                linked_values = values_to_update.copy()
                linked_values["bank_amount"] = b_bank_amount
                linked_values["cash_amount"] = b_cash_amount
                linked_values["deposit_bank_id"] = dest_deposit_bank_id
                linked_values["customer_id"] = dest_customer_id
                linked_values["flag"] = is_cleared_status_b
                linked_values["is_cleared"] = is_cleared_status_b

                linked_stmt = (
                    update(ARReceipt)
                    .where(ARReceipt.receipt_id == linked_id)
                    .values(**linked_values)
                    .execution_options(synchronize_session="fetch")
                )
                linked_result = await db.execute(linked_stmt)
                updated_count += linked_result.rowcount

    await db.commit()
    return updated_count > 0

# ----------------------------------------------------------
# 🟢 8. GET AR BOOK (FIXED: UNION OF INVOICES AND RECEIPTS)
# ----------------------------------------------------------
async def get_ar_book(db: AsyncSession, customer_id: int, from_date: str = None, to_date: str = None):
    # 🟢 FIX: Fetch BOTH Invoices (from AR Table) and Receipts (from Receipt Table)
    # This solves "Missing Receipts" and "Currency Bug"
    
    sql = text("CALL proc_CRUD_GetARBook(:cid)")
    
    result = await db.execute(sql, {"cid": customer_id})
    return result.mappings().all()

# ----------------------------------------------------------
# SAVE DRAFT
# ----------------------------------------------------------
async def save_verification_draft(db: AsyncSession, receipt_id: int, data: schemas.SaveDraftRequest):
    stmt = select(ARReceipt).where(ARReceipt.receipt_id == receipt_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        return None 

    if data.customer_id:
        record.customer_id = data.customer_id
    
    record.bank_charges = data.bank_charges
    record.tax_rate = data.tax_deduction
    record.exchange_rate = data.exchange_rate

    # 3. PROCESS ALLOCATIONS (NEW for Save Draft)
    linked_invoices = await _process_receipt_allocations(db, record, data)

    # 4. Update Description / Reference
    await _update_receipt_reference(record, data.reply_message, linked_invoices)
    
    record.modified_on = datetime.now()
    
    await db.commit()
    await db.refresh(record)
    return record


async def _process_receipt_allocations(db: AsyncSession, record: ARReceipt, data: Union[schemas.VerifyCustomerUpdate, schemas.SaveDraftRequest]):
    """Helper to clear old allocations and apply new ones idempotently."""
    receipt_id = record.receipt_id
    
    # A. PRE-CLEANUP: Revert existing allocations for this receipt_id
    old_allocs_query = text("CALL proc_CRUD_GetOldAllocations(:rid)")
    old_res = await db.execute(old_allocs_query, {"rid": receipt_id})
    old_allocs = old_res.fetchall()

    for old in old_allocs:
        if old.record_type == 'DN':
             # Revert PaidAmount in Debit_Notes
             await db.execute(text("CALL proc_DN_RevertPaidAmount(:amt, :id)"), {"amt": old.payment_amount, "id": old.invoice_id})
        else:
             # Revert PaidAmount in Header
             await db.execute(text("CALL proc_CRUD_RevertHeaderPaidAmount(:amt, :id)"), {"amt": old.payment_amount, "id": old.invoice_id})
             
        # Revert already_received in AR
        await db.execute(text("CALL proc_CRUD_RevertARAlreadyReceived(:amt, :arid)"), {"amt": old.payment_amount, "arid": old.ar_id})

    # 2. Deactivate old allocation records
    await db.execute(text("CALL proc_CRUD_DeactivateOldAllocations(:rid)"), {"rid": receipt_id})

    # B. APPLY NEW ALLOCATIONS
    linked_invoices = []
    # Safeguard for user_id
    user_id = getattr(data, 'user_id', None) or (record.created_by or 'System')
    user_ip = record.created_ip or '127.0.0.1'

    for alloc in data.allocations:
        if alloc.amount_allocated > 0:
            if alloc.record_type == 'DN':
                # 1. Update PaidAmount in Debit_Notes
                update_dn = text("CALL proc_DN_ApplyPaidAmount(:amt, :id)")
                await db.execute(update_dn, {"amt": alloc.amount_allocated, "id": alloc.invoice_id})
                inv_nbr = alloc.invoice_no
                if inv_nbr: linked_invoices.append(inv_nbr)
            else:
                # 1. Update PaidAmount in Header
                update_header = text("CALL proc_CRUD_ApplyHeaderPaidAmount(:amt, :id)")
                await db.execute(update_header, {"amt": alloc.amount_allocated, "id": alloc.invoice_id})
                
                # 2. Get Invoice Number
                get_inv_nbr = text("CALL proc_DSI_GetDONumberString(:id)")
                inv_res = await db.execute(get_inv_nbr, {"id": alloc.invoice_id})
                inv_nbr = inv_res.scalar()
                if inv_nbr: linked_invoices.append(inv_nbr)

            # 3. Update AR Table
            get_ar = text("CALL proc_CRUD_GetARIdByInvoiceId(:id, :type)")
            ar_id = (await db.execute(get_ar, {"id": alloc.invoice_id, "type": alloc.record_type})).scalar()
            
            if ar_id:
                # Insert Link
                insert_link = text("CALL proc_CRUD_InsertReceiptARLink(:rid, :arid, :amt, :rdate, :uid, :ip)")
                await db.execute(insert_link, {
                    "rid": receipt_id, "arid": ar_id, "amt": alloc.amount_allocated,
                    "rdate": record.receipt_date or datetime.now().date(), "uid": user_id, "ip": user_ip
                })
                
                # Update AR Balance
                update_ar = text("CALL proc_CRUD_ApplyARAlreadyReceived(:amt, :arid, :uid)")
                await db.execute(update_ar, {"amt": alloc.amount_allocated, "uid": user_id, "arid": ar_id})
                
                if record.ar_id is None: record.ar_id = ar_id

    return linked_invoices


async def _update_receipt_reference(record: ARReceipt, reply_message: Optional[str], linked_invoices: List[str]):
    """Helper to construct the reference string with linked invoices."""
    current_desc = record.reference_no or ""
    
    # Extract existing Reply: if no new reply_message is provided
    final_reply = reply_message
    if final_reply is None:
        match = re.search(r'\(Reply:\s*(.*?)\)', current_desc, flags=re.IGNORECASE)
        if match:
            final_reply = match.group(1)

    # Clean up standard formats
    current_desc = re.sub(r'\s*\|\s*Inv:.*', '', current_desc, flags=re.IGNORECASE)
    current_desc = re.sub(r'\s*\|\s*Reply:.*', '', current_desc, flags=re.IGNORECASE)
    current_desc = re.sub(r'\s*\(Inv:.*?\)', '', current_desc, flags=re.IGNORECASE)
    current_desc = re.sub(r'\s*\(Reply:.*?\)', '', current_desc, flags=re.IGNORECASE)
    current_desc = current_desc.strip()
    
    additional_info = []
    if final_reply: additional_info.append(f"(Reply: {final_reply})")
    if linked_invoices: additional_info.append(f"(Inv: {', '.join(linked_invoices)})")
        
    new_val = f"{current_desc} {' '.join(additional_info)}".strip()
    record.reference_no = new_val

# ----------------------------------------------------------
# UPDATE REFERENCE NUMBER (For AR Book Editing)
# ----------------------------------------------------------
async def update_invoice_reference(db: AsyncSession, invoice_id: int, new_reference: str):
    try:
        query = text("CALL proc_CRUD_UpdateHeaderReference(:id, :ref)")
        
        result = await db.execute(query, {"ref": new_reference, "id": invoice_id})
        await db.commit()
        return result.rowcount > 0
    except Exception as e:
        print(f"Error updating reference: {e}")
        await db.rollback()
        return False

# 🟢 FIXED BULK UPDATE LOGIC TO PREVENT DUPLICATE ERRORS
async def bulk_update_ar_reference(db: AsyncSession, ar_ids: List[int], new_reference: str):
    try:
        if not ar_ids:
            return 0 

        updated_count = 0

        # 🟢 Resolve all invoice IDs first
        query_get_inv = text("SELECT ar_id, invoice_id FROM btggasify_finance_live.tbl_accounts_receivable WHERE ar_id IN :ids")
        res = await db.execute(query_get_inv, {"ids": tuple(ar_ids)})
        id_map = {row[0]: row[1] for row in res.fetchall()}
        
        if not id_map:
            return 0
            
        # Pick the first invoice ID as primary
        primary_inv_id = list(id_map.values())[0]

        for ar_id in ar_ids:
            inv_id = id_map.get(ar_id)
            if not inv_id: continue

            # 1. Update Details (Preserve DO Linkage)
            await db.execute(text("CALL proc_CRUD_BulkUpdatePreserveDO(:id, :ref)"), {"id": ar_id, "ref": new_reference})
            
            # 2. Update Finance AR Table (Existing SP handles merging AR amounts)
            await db.execute(text("CALL proc_CRUD_BulkUpdateFinanceAR(:id, :ref)"), {"id": ar_id, "ref": new_reference})

            # 3. Update/Consolidate Sales Header (New SP handles merging headers)
            await db.execute(text("CALL proc_CRUD_ConsolidateInvoices(:p_id, :s_id, :ref)"), 
                             {"p_id": primary_inv_id, "s_id": inv_id, "ref": new_reference})
            
            updated_count += 1

        await db.commit()
        return updated_count

    except Exception as e:
        print(f"CRITICAL DB ERROR in bulk_update: {str(e)}")
        await db.rollback()
        return -1

# ----------------------------------------------------------
# 9. COMBINE VOUCHERS (Logical Grouping)
# ----------------------------------------------------------
async def combine_receipts(db: AsyncSession, request: schemas.CombineVouchersRequest):
    """
    Logically groups multiple receipts for display in Bank Book Entries.
    Does NOT delete originals or move allocations, ensuring they show separately in the Bank Book report.
    """
    try:
        # 1. Fetch all original receipts
        stmt = select(ARReceipt).where(ARReceipt.receipt_id.in_(request.receipt_ids), ARReceipt.is_active == True)
        result = await db.execute(stmt)
        originals = result.scalars().all()
        
        if not originals or len(originals) < 2:
            print(f"Combine failed: Found {len(originals)} active receipts for IDs {request.receipt_ids}")
            return None
        
        # 2. Generate a Group ID (using current timestamp for uniqueness)
        import time
        group_id = int(time.time() % 1000000000) # Ensure it fits in INT
        
        # 3. Create a Dummy Record to Consume Sequence ID
        dummy_receipt = ARReceipt(
            orgid=request.orgId,
            branchid=request.branchId,
            created_by=str(request.userId),
            created_ip=request.userIp,
            receipt_date=datetime.now().date(),
            customer_id=0,
            transaction_type='Combined',
            bank_amount=0,
            cash_amount=0,
            is_active=False,
            is_posted=False,
            pending_verification=False,
            is_submitted=False
        )
        db.add(dummy_receipt)
        await db.flush()
        
        # Format the auto-generated receipt number with the correct prefix
        t_type = (originals[0].transaction_type or 'Receipt').lower()
        prefix = ""
        if 'other income' in t_type:
            prefix = "RCV - "
        elif 'receipt' in t_type or 'rounding' in t_type:
            prefix = "RV - "
        elif 'transfer' in t_type:
            prefix = "CV - "
        
        auto_voucher_no = f"{prefix}{dummy_receipt.receipt_id}"

        # 4. Update all records with the group_id and auto_voucher_no
        for r in originals:
            r.combine_group_id = group_id
            r.custom_voucher_no = auto_voucher_no
            r.is_combined = True
            if request.new_reference:
                # Append custom reference if provided, keeping it clean
                if r.reference_no:
                    if request.new_reference not in r.reference_no:
                        r.reference_no = f"{r.reference_no} | {request.new_reference}"
                else:
                    r.reference_no = request.new_reference
            
        await db.commit()
        return originals[0] # Return first record as proxy for success
        
    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in combine_receipts (Logical): {str(e)}")
        traceback.print_exc()
        await db.rollback()
        return None

    except Exception as e:
        print(f"CRITICAL DB ERROR in bulk_update: {str(e)}")
        await db.rollback()
        return -1