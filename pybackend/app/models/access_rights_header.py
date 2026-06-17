from sqlalchemy import Column, Integer, String, DateTime, Boolean
from ..database import Base, DB_NAME_MASTER

class MasterAccessRightsHeader(Base):
    __tablename__ = "master_accessrights_header"
    __table_args__ = {"schema": DB_NAME_MASTER}

    Id = Column(Integer, primary_key=True, autoincrement=True)
    Role = Column(String(450))
    Department = Column(String(450))
    DepartmentId = Column(Integer)
    Hod = Column(Boolean) # tinyint(1)
    BranchId = Column(Integer)
    OrgId = Column(Integer)
    IsActive = Column(Boolean) # bit(1)
    CreatedBy = Column(Integer)
    CreatedDate = Column(DateTime)
    CreatedIP = Column(String(100))
    ModifiedBy = Column(Integer)
    LastModifiedDate = Column(DateTime)
    ModifiedIP = Column(String(100))
    EffectiveFrom = Column(DateTime)
    RoleId = Column(String(450))
