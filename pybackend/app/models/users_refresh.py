from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean
from ..database import Base, DB_NAME_USER

class AspNetUsers(Base):
    __tablename__ = "AspNetUsers"
    __table_args__ = {"schema": DB_NAME_USER}

    Id = Column(String(450), primary_key=True)
    RefreshToken = Column(Text)
    RefreshTokenExpiryTime = Column(DateTime) # datetime(6)
    UserName = Column(String(256))
    NormalizedUserName = Column(String(256))
    Email = Column(String(256))
    NormalizedEmail = Column(String(256))
    EmailConfirmed = Column(Boolean) # tinyint
    PasswordHash = Column(Text)
    SecurityStamp = Column(Text)
    ConcurrencyStamp = Column(Text)
    PhoneNumber = Column(Text)
    PhoneNumberConfirmed = Column(Boolean) # tinyint
    TwoFactorEnabled = Column(Boolean) # tinyint
    LockoutEnd = Column(DateTime) # datetime(6)
    LockoutEnabled = Column(Boolean) # tinyint
    AccessFailedCount = Column(Integer)
    CreatedBy = Column(Integer)
    CreatedDate = Column(DateTime)
    LastModifiedDate = Column(DateTime)
    LastModifiedBy = Column(Integer)
    OrgId = Column(Integer)
    IsActive = Column(Boolean) # bit(1)
    userid = Column(Integer)
