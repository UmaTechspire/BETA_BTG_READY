from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, func, ForeignKey, Boolean, Date as DateType
from ..database import Base

class CreditNotes(Base):
    __tablename__ = "Credit_Notes"
    __table_args__ = {"schema": "btggasify_finance_live"}

    CreditNoteId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    CreditNoteNumber = Column(String(50), nullable=True)
    TransactionDate = Column(DateType, nullable=True)
    Amount = Column(DECIMAL(18, 2), default=0.00)
    Description = Column(String(255), nullable=True)
    CustomerId = Column(Integer, nullable=True)
    SupplierId = Column(Integer, nullable=True)
    InvoiceId = Column(Integer, nullable=True)
    GLAccountCode = Column(String(50), nullable=True)
    CurrencyId = Column(Integer, nullable=True)
    IsSubmitted = Column(Boolean, default=False)
    GasCodeId = Column(Integer, default=0)
    Qty = Column(DECIMAL(18, 2), default=1)
    UomId = Column(Integer, default=0)
    
    # Audit fields removed as they don't exist in DB
    # CreatedBy = Column(String(50), nullable=True)
    # CreatedAt = Column(DateTime(timezone=True), server_default=func.now())
    # ModifiedBy = Column(String(50), nullable=True)
    # ModifiedAt = Column(DateTime(timezone=True), onupdate=func.now())

class DebitNotes(Base):
    __tablename__ = "Debit_Notes"
    __table_args__ = {"schema": "btggasify_finance_live"}

    DebitNoteId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    DebitNoteNumber = Column(String(50), nullable=True)
    TransactionDate = Column(DateType, nullable=True)
    Amount = Column(DECIMAL(18, 2), default=0.00)
    Description = Column(String(255), nullable=True)
    CustomerId = Column(Integer, nullable=True)
    SupplierId = Column(Integer, nullable=True)
    InvoiceId = Column(Integer, nullable=True)
    GLAccountCode = Column(String(50), nullable=True)
    CurrencyId = Column(Integer, nullable=True)
    IsSubmitted = Column(Boolean, default=False)
    GasCodeId = Column(Integer, default=0)
    Qty = Column(DECIMAL(18, 2), default=1)
    UomId = Column(Integer, default=0)
    
    # Audit
    # CreatedBy = Column(String(50), nullable=True)
    # CreatedAt = Column(DateTime(timezone=True), server_default=func.now())
    # ModifiedBy = Column(String(50), nullable=True)
    # ModifiedAt = Column(DateTime(timezone=True), onupdate=func.now())

class CreditInvoice(Base):
    __tablename__ = "credit_invoice"
    __table_args__ = {"schema": "btggasify_finance_live"} 

    Id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    CreditNoteId = Column(Integer, nullable=False) # FK
    InvoiceNo = Column(String(50), nullable=True)

class DebitInvoice(Base):
    __tablename__ = "debit_invoice"
    __table_args__ = {"schema": "btggasify_finance_live"}

    Id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    DebitNoteId = Column(Integer, nullable=False) # FK
    InvoiceNo = Column(String(50), nullable=True)
