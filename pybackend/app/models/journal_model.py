from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class PartyRequest(BaseModel):
    party_type: str  # 'customer', 'supplier', 'bank'

class JournalDetailItem(BaseModel):
    gl_code: Optional[str] = None
    type: str # 'Debit', 'Credit'
    description: Optional[str] = None
    amount: float
    reference_no: Optional[str] = None
    party_name: Optional[str] = None
    id: Optional[int] = None # Ensure we can parse detail IDs for updating

class JournalCreateRequest(BaseModel):
    journal_date: date
    description: Optional[str] = None
    party_type: str
    party_id: Optional[int] = None
    party_name: Optional[str] = None
    reference_no: Optional[str] = None
    total_amount: float
    status: str # 'Saved', 'Posted'
    created_by: str
    is_posted: int = 0
    journal_id: Optional[int] = None
    details: List[JournalDetailItem]

class JournalResponse(BaseModel):
    status: bool
    message: str
    journal_id: Optional[int] = None