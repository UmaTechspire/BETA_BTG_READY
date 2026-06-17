from sqlalchemy import Column, Integer, String, Boolean
from ..database import Base, DB_NAME_MASTER

class MasterAccessRightsDetails(Base):
    __tablename__ = "master_accessrights_details"
    __table_args__ = {"schema": DB_NAME_MASTER}

    Id = Column(Integer, primary_key=True, autoincrement=True)
    HeaderId = Column(Integer)
    Module = Column(String(50))
    Screen = Column(String(100))
    View = Column(Boolean) # tinyint(1)
    Edit = Column(Boolean) # tinyint(1)
    Delete = Column(Boolean) # tinyint(1)
    Post = Column(Boolean) # tinyint(1)
    Save = Column(Boolean) # tinyint(1)
    Print = Column(Boolean) # tinyint(1)
    ViewRate = Column(Boolean) # tinyint(1)
    SendMail = Column(Boolean) # tinyint(1)
    ViewDetails = Column(Boolean) # tinyint(1)
    Records = Column(Integer)
    IsActive = Column(Boolean) # bit(1)
    ScreenId = Column(Integer)
    ModuleId = Column(Integer)
    New = Column(Boolean) # tinyint(1)
