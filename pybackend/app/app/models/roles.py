from sqlalchemy import Column, String, Text
from ..database import Base, DB_NAME_USER

class AspNetRoles(Base):
    __tablename__ = "AspNetRoles"
    __table_args__ = {"schema": DB_NAME_USER}

    Id = Column(String(450), primary_key=True)
    Name = Column(String(256))
    NormalizedName = Column(String(256))
    ConcurrencyStamp = Column(Text)
