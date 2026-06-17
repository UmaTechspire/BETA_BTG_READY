from pydantic import BaseModel
from typing import List, Optional, Union
from datetime import date  # 🟢 Essential Import

class ArReceiptInput(BaseModel):
    receipt_id: int = 0
    payment_amount: float = 0
    ar_id: int = 0  
    cash_amount: float = 0
    bank_amount: float = 0
    contra_amount: float = 0
    tax_rate: float = 0
    bank_payment_via: int = 0
    cheque_number: Optional[str] = None
    giro_number: Optional[str] = None
    
    # 🟢 Updated to allow int or string "0" / "" from frontend
    deposit_bank_id: Union[int, str] = 0 
    
    deposit_account_number: Optional[str] = None
    contra_reference: Optional[str] = None
    proof_missing: bool = False
    bank_charges: float = 0
    pending_verification: bool = False
    customer_id: int
    transaction_type: Optional[str] = 'Receipt'
    
    # --- NEW FIELDS ---
    reference_no: Optional[str] = None
    sales_person_id: Optional[int] = None
    currencyid: Optional[int] = None
    send_notification: bool = False
    is_posted: bool = False
    
    # 🟢 ADDED MISSING FIELD
    receipt_date: Optional[date] = None 

class CreateARCommand(BaseModel):
    orgId: int
    branchId: int
    userId: int
    userIp: str
    header: List[ArReceiptInput]

# ... (Rest of your classes InvoiceAllocation, VerifyCustomerUpdate etc. remain unchanged) ...
class InvoiceAllocation(BaseModel):
    invoice_id: int
    invoice_no: str
    payment_type: str 
    amount_allocated: float
    record_type: str = "INV"

class VerifyCustomerUpdate(BaseModel):
    customer_id: int
    bank_charges: float
    tax_deduction: float
    exchange_rate: float = 1.0
    allocations: List[InvoiceAllocation]
    advance_payment: float = 0.0 
    reply_message: Optional[str] = None
    user_id: Optional[int] = None

class SaveDraftRequest(BaseModel):
    customer_id: int
    bank_charges: float
    tax_deduction: float
    exchange_rate: float = 1.0 
    allocations: List[InvoiceAllocation]
    advance_payment: float = 0.0
    reply_message: Optional[str] = None 

class UpdateReferenceRequest(BaseModel):
    id: int
    new_reference: str

class BulkUpdateReferenceRequest(BaseModel):
    ids: List[int]
    new_reference: str

class PostInvoiceToARRequest(BaseModel):
    orgId: int
    branchId: int
    userId: int
    invoiceId: int
    oldInvoiceNumber: Optional[str] = None

class CombineVouchersRequest(BaseModel):
    receipt_ids: List[int]
    new_reference: Optional[str] = None
    custom_voucher_no: Optional[str] = None
    userId: int
    orgId: int
    branchId: int
    userIp: str

class ARMessage(BaseModel):
    receipt_id: int
    sender_role: str # 'Marketing' or 'Finance'
    message_text: str