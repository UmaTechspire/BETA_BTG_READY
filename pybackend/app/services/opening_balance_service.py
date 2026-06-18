from datetime import date, datetime
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import DB_NAME_FINANCE

async def get_month_transactions_sum(
    db: AsyncSession,
    module_name: str,
    org_id: int,
    branch_id: int,
    currency_id: Optional[int],
    month_start: date
) -> Dict[str, float]:
    """
    Get sum of receipts (category_id = 1) and expenses (category_id != 1) for a given month.
    """
    cur_id = currency_id or (3 if module_name == "PETTY_CASH" else 1)
    
    # Calculate next month start
    if month_start.month == 12:
        next_month_start = date(month_start.year + 1, 1, 1)
    else:
        next_month_start = date(month_start.year, month_start.month + 1, 1)

    if module_name == "PETTY_CASH":
        tx_query = text(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN category_id = 1 THEN amount ELSE 0 END), 0) as receipts,
                COALESCE(SUM(CASE WHEN category_id != 1 THEN amount ELSE 0 END), 0) as expenses
            FROM {DB_NAME_FINANCE}.tbl_petty_cash
            WHERE IsSubmitted = 1
              AND OrgId = :orgid
              AND BranchId = :branchid
              AND (currencyid = :curid OR :curid = 0 OR :curid IS NULL)
              AND pc_number != 'OPENING'
              AND COALESCE(ExpenseDescription, '') != 'OPENING BALANCE'
              AND expdate >= :start_date
              AND expdate < :end_date
        """)
        res = await db.execute(tx_query, {
            "orgid": org_id,
            "branchid": branch_id,
            "curid": cur_id,
            "start_date": month_start,
            "end_date": next_month_start
        })
        row = res.mappings().first()
        if row:
            return {
                "receipts": float(row["receipts"] or 0),
                "expenses": float(row["expenses"] or 0)
            }
            
    return {"receipts": 0.0, "expenses": 0.0}

async def propagate_forward_balances(
    db: AsyncSession,
    module_name: str,
    org_id: int,
    branch_id: int,
    currency_id: Optional[int],
    from_month: date,
    closing_debit: float,
    closing_credit: float
):
    """
    Propagates the closing balance of from_month to all existing subsequent months.
    """
    cur_id = currency_id or (3 if module_name == "PETTY_CASH" else 1)
    
    # Fetch all subsequent months that exist in the database, ordered by balance_month ASC
    select_query = text(f"""
        SELECT balance_month, debit_opening, credit_opening
        FROM {DB_NAME_FINANCE}.tbl_opening_balance_master
        WHERE org_id = :orgid
          AND branch_id = :branchid
          AND module_name = :module_name
          {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
          AND balance_month > :from_month
        ORDER BY balance_month ASC
    """)
    res = await db.execute(select_query, {
        "orgid": org_id,
        "branchid": branch_id,
        "module_name": module_name,
        "curid": cur_id,
        "from_month": from_month
    })
    rows = res.mappings().all()
    
    current_op_debit = closing_debit
    current_op_credit = closing_credit
    
    for row in rows:
        loop_month = row["balance_month"]
        
        # Update this month's opening balance to match the previous month's closing
        update_op_query = text(f"""
            UPDATE {DB_NAME_FINANCE}.tbl_opening_balance_master
            SET debit_opening = :op_debit,
                credit_opening = :op_credit
            WHERE org_id = :orgid
              AND branch_id = :branchid
              AND module_name = :module_name
              {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
              AND balance_month = :loop_month
        """)
        await db.execute(update_op_query, {
            "op_debit": current_op_debit,
            "op_credit": current_op_credit,
            "orgid": org_id,
            "branchid": branch_id,
            "module_name": module_name,
            "curid": cur_id,
            "loop_month": loop_month
        })
        
        # Calculate new transaction sums for this loop month
        sums = await get_month_transactions_sum(db, module_name, org_id, branch_id, cur_id, loop_month)
        receipts = sums["receipts"]
        expenses = sums["expenses"]
        
        # Calculate new closing balance
        if module_name == "PETTY_CASH":
            loop_closing_debit = (current_op_debit - current_op_credit) + receipts - expenses
            loop_closing_credit = 0.0
        else:
            net_balance = (current_op_debit - current_op_credit) + receipts - expenses
            if net_balance >= 0:
                loop_closing_debit = net_balance
                loop_closing_credit = 0.0
            else:
                loop_closing_debit = 0.0
                loop_closing_credit = abs(net_balance)
                
        # Update this month's closing balance
        update_cl_query = text(f"""
            UPDATE {DB_NAME_FINANCE}.tbl_opening_balance_master
            SET debit_closing = :closing_debit,
                credit_closing = :closing_credit
            WHERE org_id = :orgid
              AND branch_id = :branchid
              AND module_name = :module_name
              {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
              AND balance_month = :loop_month
        """)
        await db.execute(update_cl_query, {
            "closing_debit": loop_closing_debit,
            "closing_credit": loop_closing_credit,
            "orgid": org_id,
            "branchid": branch_id,
            "module_name": module_name,
            "curid": cur_id,
            "loop_month": loop_month
        })
        
        # Set next loop's input values to this month's closing values
        current_op_debit = loop_closing_debit
        current_op_credit = loop_closing_credit

async def recalculate_month_closing(
    db: AsyncSession,
    module_name: str,
    org_id: int,
    branch_id: int,
    currency_id: Optional[int],
    month_start: date,
    opening_debit: float,
    opening_credit: float
) -> Dict[str, float]:
    """
    Calculate receipts, expenses, and closing debit/credit for a month and update tbl_opening_balance_master.
    """
    cur_id = currency_id or (3 if module_name == "PETTY_CASH" else 1)
    
    # 1. Fetch transactions sum
    sums = await get_month_transactions_sum(db, module_name, org_id, branch_id, cur_id, month_start)
    receipts = sums["receipts"]
    expenses = sums["expenses"]
    
    # 2. Net Balance calculation
    if module_name == "PETTY_CASH":
        closing_debit = (opening_debit - opening_credit) + receipts - expenses
        closing_credit = 0.0
    else:
        net_balance = (opening_debit - opening_credit) + receipts - expenses
        if net_balance >= 0:
            closing_debit = net_balance
            closing_credit = 0.0
        else:
            closing_debit = 0.0
            closing_credit = abs(net_balance)
        
    # 3. Update the record (using DB column names debit_closing, credit_closing)
    update_query = text(f"""
        UPDATE {DB_NAME_FINANCE}.tbl_opening_balance_master
        SET debit_closing = :closing_debit,
            credit_closing = :closing_credit
        WHERE org_id = :orgid
          AND branch_id = :branchid
          AND module_name = :module_name
          {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
          AND balance_month = :month_start
    """)
    await db.execute(update_query, {
        "closing_debit": closing_debit,
        "closing_credit": closing_credit,
        "orgid": org_id,
        "branchid": branch_id,
        "module_name": module_name,
        "curid": cur_id,
        "month_start": month_start
    })
    
    # 4. Propagate changes forward to subsequent months
    await propagate_forward_balances(
        db, module_name, org_id, branch_id, cur_id, month_start, closing_debit, closing_credit
    )
    
    await db.commit()
    
    return {
        "closing_debit": closing_debit,
        "closing_credit": closing_credit,
        "receipts": receipts,
        "expenses": expenses
    }

async def get_or_create_monthly_balance(
    db: AsyncSession,
    module_name: str,
    org_id: int,
    branch_id: int,
    currency_id: Optional[int],
    target_date: date,
) -> Dict[str, Any]:
    """
    Main service function.
    Finds the record for the target_date's month in tbl_opening_balance_master.
    If it doesn't exist, it rolls forward from the latest available month.
    """
    cur_id = currency_id or (3 if module_name == "PETTY_CASH" else 1)
    target_month_start = date(target_date.year, target_date.month, 1)
    # Maintain strict creation policy:
    # - If the caller requests a non-month-start date, do NOT create month rows.
    # - If the caller requests the month-start, only create the month row when
    #   the server's real date is that month's first day. This prevents client/UI
    #   filters from creating future months.
    requested_is_month_start = (target_date.day == 1)
    server_is_month_start = (date.today() == target_month_start)

    lookup_date = target_month_start if requested_is_month_start else target_date
    select_query = text(f"""
        SELECT debit_opening, credit_opening, debit_closing, credit_closing, balance_month
        FROM {DB_NAME_FINANCE}.tbl_opening_balance_master
        WHERE org_id = :orgid
          AND branch_id = :branchid
          AND module_name = :module_name
          {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
          AND balance_month = :month_lookup
        LIMIT 1
    """)
    res = await db.execute(select_query, {
        "orgid": org_id,
        "branchid": branch_id,
        "module_name": module_name,
        "curid": cur_id,
        "month_lookup": lookup_date
    })
    row = res.mappings().first()
    
    if row:
        # Record exists, let's check if the previous month's closing balance aligns with our opening balance
        prev_query = text(f"""
            SELECT debit_closing, credit_closing
            FROM {DB_NAME_FINANCE}.tbl_opening_balance_master
            WHERE org_id = :orgid
              AND branch_id = :branchid
              AND module_name = :module_name
              {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
              AND balance_month < :month_start
            ORDER BY balance_month DESC
            LIMIT 1
        """)
        prev_res = await db.execute(prev_query, {
            "orgid": org_id,
            "branchid": branch_id,
            "module_name": module_name,
            "curid": cur_id,
            "month_start": target_month_start
        })
        prev_row = prev_res.mappings().first()
        
        op_deb = float(row["debit_opening"] or 0)
        op_cred = float(row["credit_opening"] or 0)
        
        if prev_row:
            prev_close_deb = float(prev_row["debit_closing"] or 0)
            prev_close_cred = float(prev_row["credit_closing"] or 0)
            if op_deb != prev_close_deb or op_cred != prev_close_cred:
                op_deb = prev_close_deb
                op_cred = prev_close_cred
                
                # Update database record
                update_op_query = text(f"""
                    UPDATE {DB_NAME_FINANCE}.tbl_opening_balance_master
                    SET debit_opening = :op_debit,
                        credit_opening = :op_credit
                    WHERE org_id = :orgid
                      AND branch_id = :branchid
                      AND module_name = :module_name
                      {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
                      AND balance_month = :month_start
                """)
                await db.execute(update_op_query, {
                    "op_debit": op_deb,
                    "op_credit": op_cred,
                    "orgid": org_id,
                    "branchid": branch_id,
                    "module_name": module_name,
                    "curid": cur_id,
                    "month_start": target_month_start
                })
                await db.commit()
                
        closing_info = await recalculate_month_closing(
            db, module_name, org_id, branch_id, cur_id, target_month_start, op_deb, op_cred
        )
        return {
            "opening_debit": op_deb,
            "opening_credit": op_cred,
            "closing_debit": closing_info["closing_debit"],
            "closing_credit": closing_info["closing_credit"],
            "balance_month": target_month_start.isoformat()
        }
        
    # If the exact month-row exists we reconcile its opening with the previous
    # month's closing and recalculate the month's closing.

    # 2. If it does not exist (and the request is for month-start), look up the latest available month record prior to target_month_start
    latest_query = text(f"""
        SELECT debit_opening, credit_opening, debit_closing, credit_closing, balance_month
        FROM {DB_NAME_FINANCE}.tbl_opening_balance_master
        WHERE org_id = :orgid
          AND branch_id = :branchid
          AND module_name = :module_name
          {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
          AND balance_month < :month_start
        ORDER BY balance_month DESC
        LIMIT 1
    """)
    latest_res = await db.execute(latest_query, {
        "orgid": org_id,
        "branchid": branch_id,
        "module_name": module_name,
        "curid": cur_id,
        "month_start": target_month_start
    })
    latest_row = latest_res.mappings().first()

    if not latest_row:
        # Absolutely no records found, return all zeros
        return {
            "opening_debit": 0.0,
            "opening_credit": 0.0,
            "closing_debit": 0.0,
            "closing_credit": 0.0,
            "balance_month": target_month_start.isoformat()
        }
    # If the month row does not exist and the server is NOT on that month's first
    # day, do NOT create DB rows. Instead return a virtual/display opening balance
    # derived from the latest available month's stored closing values. This
    # prevents UI date filters from inserting future months.
    if not server_is_month_start:
        prev_close_deb = float(latest_row.get("debit_closing") or latest_row.get("debit_opening") or 0)
        prev_close_cred = float(latest_row.get("credit_closing") or latest_row.get("credit_opening") or 0)

        # Compute receipts/expenses for the requested month without persisting
        sums = await get_month_transactions_sum(db, module_name, org_id, branch_id, cur_id, target_month_start)
        receipts = sums["receipts"]
        expenses = sums["expenses"]

        # Compute closing based on module rules (same logic as recalculate_month_closing)
        if module_name == "PETTY_CASH":
            closing_debit = (prev_close_deb - prev_close_cred) + receipts - expenses
            closing_credit = 0.0
        else:
            net_balance = (prev_close_deb - prev_close_cred) + receipts - expenses
            if net_balance >= 0:
                closing_debit = net_balance
                closing_credit = 0.0
            else:
                closing_debit = 0.0
                closing_credit = abs(net_balance)

        return {
            "opening_debit": prev_close_deb,
            "opening_credit": prev_close_cred,
            "closing_debit": closing_debit,
            "closing_credit": closing_credit,
            "balance_month": target_month_start.isoformat(),
            "created_months": []
        }
        
    # 3. Roll forward month-by-month from latest_row["balance_month"] to target_month_start
    loop_month = latest_row["balance_month"]
    # Use the latest month's CLOSING values as the starting opening for the next month.
    # If closing values are null/zero, fall back to the stored opening values.
    current_op_debit = float(latest_row.get("debit_closing") or latest_row.get("debit_opening") or 0)
    current_op_credit = float(latest_row.get("credit_closing") or latest_row.get("credit_opening") or 0)
    
    created_months = []
    while loop_month < target_month_start:
        # A. Determine next month start
        if loop_month.month == 12:
            next_month = date(loop_month.year + 1, 1, 1)
        else:
            next_month = date(loop_month.year, loop_month.month + 1, 1)

        # B. Read the *stored* closing values for the current loop_month from DB
        # and use those as the opening for the next month. This ensures the newly
        # created month-start opening equals the previously stored closing value
        # (what users expect when the month rolls over).
        fetch_close_query = text(f"""
            SELECT debit_closing, credit_closing
            FROM {DB_NAME_FINANCE}.tbl_opening_balance_master
            WHERE org_id = :orgid
              AND branch_id = :branchid
              AND module_name = :module_name
              {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
              AND balance_month = :loop_month
            LIMIT 1
        """)
        fetch_res = await db.execute(fetch_close_query, {
            "orgid": org_id,
            "branchid": branch_id,
            "module_name": module_name,
            "curid": cur_id,
            "loop_month": loop_month
        })
        fetch_row = fetch_res.mappings().first()
        next_op_debit = float(fetch_row["debit_closing"] or 0) if fetch_row else current_op_debit
        next_op_credit = float(fetch_row["credit_closing"] or 0) if fetch_row else current_op_credit

        # C. Check if next_month row exists before inserting so we can report creations
        exists_query = text(f"""
            SELECT 1 FROM {DB_NAME_FINANCE}.tbl_opening_balance_master
            WHERE org_id = :orgid
              AND branch_id = :branchid
              AND module_name = :module_name
              {"" if module_name == "PETTY_CASH" else "AND currency_id = :curid"}
              AND balance_month = :next_month
            LIMIT 1
        """)
        exists_res = await db.execute(exists_query, {
            "orgid": org_id,
            "branchid": branch_id,
            "module_name": module_name,
            "curid": cur_id,
            "next_month": next_month
        })
        exists_row = exists_res.first()

        # Only insert if the next_month row does not already exist. This prevents
        # accidental overwrites of an existing opening value.
        if not exists_row:
            insert_query = text(f"""
                INSERT INTO {DB_NAME_FINANCE}.tbl_opening_balance_master
                (org_id, branch_id, module_name, currency_id, balance_month, debit_opening, credit_opening)
                VALUES (:orgid, :branchid, :module_name, :curid, :next_month, :op_debit, :op_credit)
            """)
            await db.execute(insert_query, {
                "orgid": org_id,
                "branchid": branch_id,
                "module_name": module_name,
                "curid": cur_id,
                "next_month": next_month,
                "op_debit": next_op_debit,
                "op_credit": next_op_credit
            })
            await db.commit()

            created_months.append(next_month.isoformat())
            print(f"Created opening balance row for {next_month.isoformat()} (module={module_name}, org={org_id}, branch={branch_id}, currency={cur_id})")

        # D. Advance loop parameters
        loop_month = next_month
        current_op_debit = next_op_debit
        current_op_credit = next_op_credit
        
    # 4. Finally recalculate the newly created target month and return it
    closing_info = await recalculate_month_closing(
        db, module_name, org_id, branch_id, cur_id, target_month_start, current_op_debit, current_op_credit
    )
    
    return {
        "opening_debit": current_op_debit,
        "opening_credit": current_op_credit,
        "closing_debit": closing_info["closing_debit"],
        "closing_credit": closing_info["closing_credit"],
        "balance_month": target_month_start.isoformat(),
        "created_months": created_months
    }
