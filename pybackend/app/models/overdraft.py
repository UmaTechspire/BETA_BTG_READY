from sqlalchemy import Column, Integer, String, Date, Float, Boolean, DateTime, DECIMAL
from sqlalchemy.sql import func
from ..database import Base


class TblOverDraft(Base):
    __tablename__ = "tbl_overdraft"

    OverDraftId = Column(Integer, primary_key=True, index=True, autoincrement=True)

    VoucherNo = Column(String(50), nullable=True)
    OverDraftDate = Column(Date, nullable=True)
    OverDraftType = Column(String(50), nullable=True)
    Bank = Column(String(100), nullable=True)
    InterestType = Column(String(50), nullable=True)
    ODInterest = Column(DECIMAL(15, 2), nullable=True)

    ODAmount = Column(DECIMAL(15, 2), nullable=True)
    ODAmountIDR = Column(DECIMAL(15, 2), nullable=True)

    RepayInMonths = Column(Integer, nullable=True)
    FinalSettlementAmount = Column(DECIMAL(15, 2), nullable=True)
    FinalSettlementAmountIDR = Column(DECIMAL(15, 2), nullable=True)
    FinalSettlementDate = Column(Date, nullable=True)

    bankid = Column(Integer, nullable=True)
    currencyid = Column(Integer, nullable=True)
    payment_method = Column(Integer, nullable=True)

    IsSubmitted = Column(Boolean, default=False)
    IsActive = Column(Boolean, default=True)

    OrgId = Column(Integer, nullable=True)
    BranchId = Column(Integer, nullable=True)

    CreatedBy = Column(Integer, nullable=True)
    ModifiedBy = Column(Integer, nullable=True)

    CreatedAt = Column(DateTime(timezone=True), server_default=func.now())
    ModifiedAt = Column(DateTime(timezone=True), onupdate=func.now())