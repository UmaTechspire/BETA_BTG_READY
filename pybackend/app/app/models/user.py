import os
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Text
from ..database import Base, DB_NAME_USER

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": DB_NAME_USER}

    Id = Column(Integer, primary_key=True, autoincrement=True)
    UserName = Column(String(200))
    Email = Column(String(200))
    PhoneNumber = Column(String(50))
    CreatedBy = Column(Integer)
    CreatedDate = Column(DateTime)
    CreatedIP = Column(String(255))
    LastModifiedBy = Column(Integer)
    LastModifiedDate = Column(DateTime)
    LastModifiedIP = Column(String(255))
    IsActive = Column(Boolean)
    OrgId = Column(Integer)
    BranchId = Column(Integer)
    FirstName = Column(String(100))
    MiddleName = Column(String(100))
    LastName = Column(String(100))
    Password = Column(String(255))
    Role = Column(String(100))
    Department = Column(String(100))
    FromDate = Column(Date)
    ToDate = Column(Date)
    Remarks = Column(Text)
    IsHOD = Column(Boolean)
    IsApprover = Column(Boolean)
    HomePage = Column(String(100))
    IsNotification = Column(Boolean)
    hodid = Column(Integer)
    DepartmentId = Column(Integer)  # Foreign key to departments table
