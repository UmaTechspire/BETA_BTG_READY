from sqlalchemy import Column, Integer, String, Date, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class TblPettyCash(Base):
    __tablename__ = "tbl_petty_cash"

    PettyCashId = Column(Integer, primary_key=True, index=True, autoincrement=True)

    pc_number = Column(String(50), nullable=True)

    VoucherNo = Column(String(50), nullable=True)
    ExpDate = Column(Date, nullable=True)

    # foreign keys to master tables (adjust table/column names if different in your DB)
    # category_id = Column(Integer, ForeignKey('master_expense_category.id'), index=True, nullable=True)
    # expense_type_id = Column(Integer, ForeignKey('master_expense_type.id'), index=True, nullable=True)
    category_id = Column(Integer, index=True, nullable=True)
    expense_type_id = Column(Integer, index=True, nullable=True)
    ExpenseDescription = Column(String(250), nullable=True)

    # relationships (commented out as master models are not defined yet)
    # category = relationship("MasterExpenseCategory", backref="petty_cash")
    # expense_type = relationship("MasterExpenseType", backref="petty_cash")



    AmountIDR = Column(Float, nullable=True)
    Amount = Column(Float, nullable=True)

    ExpenseFileName = Column(String(250), nullable=True)
    ExpenseFilePath = Column(String(500), nullable=True)

    IsSubmitted = Column(Boolean, default=False)

    OrgId = Column(Integer, nullable=True)
    BranchId = Column(Integer, nullable=True)

    Who = Column(String(100), nullable=True)
    Whom = Column(String(250), nullable=True)

    currencyid = Column(Integer, nullable=True)
    exchangeRate = Column(Float, nullable=True)

    CreatedBy = Column(Integer, nullable=True)
    ModifiedBy = Column(Integer, nullable=True)

    CreatedAt = Column(DateTime(timezone=True), server_default=func.now())
    ModifiedAt = Column(DateTime(timezone=True), onupdate=func.now())