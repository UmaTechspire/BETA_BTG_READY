from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, func, ForeignKey
from ..database import Base

class LedgerBook(Base):
    __tablename__ = "tbl_ledgerbook"

    ledger_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    gl_id = Column(Integer, nullable=True) # linked to tbl_GLcode_master
    reference_no = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    party_id = Column(Integer, nullable=True)
    party = Column(String(255), nullable=True)
    currency_id = Column(Integer, nullable=True) # linked to master_currency
    debit = Column(DECIMAL(18, 2), default=0.00)
    credit = Column(DECIMAL(18, 2), default=0.00)
    narration = Column(String(200), nullable=True)
    exchange_rate = Column(DECIMAL(18, 6), default=1.000000) # for respective currency_id
    org_id = Column(Integer, default=1)
    branch_id = Column(Integer, default=1)
    
    # Audit fields
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    modified_by = Column(String(50), nullable=True)
    modified_at = Column(DateTime(timezone=True), onupdate=func.now())