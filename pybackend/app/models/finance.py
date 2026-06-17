from sqlalchemy import Column, Integer, String, DECIMAL, Date, DateTime, Boolean
from sqlalchemy.sql import func
from ..database import Base

class ARReceipt(Base):
    __tablename__ = "tbl_ar_receipt"

    # Primary Key
    receipt_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    transaction_type = Column(String(50), nullable=True, default='Receipt')
    
    ar_id = Column(Integer, nullable=True) 

    # Core Data
    receipt_date = Column(Date, nullable=False)
    customer_id = Column(Integer, nullable=True)
    currencyid = Column(Integer, nullable=True)
    
    # Financials
    cash_amount = Column(DECIMAL(18, 2), nullable=False, default=0.00)
    bank_amount = Column(DECIMAL(18, 2), nullable=False, default=0.00)
    contra_amount = Column(DECIMAL(18, 2), nullable=False, default=0.00)
    bank_charges = Column(DECIMAL(18, 2), nullable=True, default=0.00)
    tax_rate = Column(DECIMAL(18, 2), nullable=True, default=0.00)
    
    # --- NEW COLUMNS ADDED HERE ---
    reference_no = Column(String(255), nullable=True)
    sales_person_id = Column(Integer, nullable=True)
    send_notification = Column(Boolean, default=False)
    is_posted = Column(Boolean, default=False)
    linked_receipt_id = Column(Integer, nullable=True)
    # ------------------------------

    # Bank Details
    deposit_bank_id = Column(String(50), nullable=True)
    deposit_account_number = Column(String(50), nullable=True)
    cheque_number = Column(String(50), nullable=True)
    giro_number = Column(String(50), nullable=True)
    bank_payment_via = Column(Integer, nullable=True)
    
    # Status & Meta
    pending_verification = Column(Boolean, default=False)
    is_submitted = Column(Boolean, default=False)
    flag = Column(Boolean, default=False)
    is_cleared = Column(Boolean, default=False)
    proof_missing = Column(Boolean, default=False)
    contra_reference = Column(String(50), nullable=True)
    
    # Organization Info
    orgid = Column(Integer, nullable=True)
    branchid = Column(Integer, nullable=True)
    
    # Audit Fields
    combine_group_id = Column(Integer, nullable=True)
    custom_voucher_no = Column(String(100), nullable=True)
    is_combined = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_date = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(50), nullable=False)
    created_ip = Column(String(45), nullable=False)

class ARReceiptMessage(Base):
    __tablename__ = "tbl_ar_receipt_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    receipt_id = Column(Integer, nullable=False, index=True)
    sender_role = Column(String(50), nullable=False) # 'Marketing' or 'Finance'
    message_text = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())