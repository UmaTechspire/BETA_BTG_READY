from sqlalchemy import Column, String
from ..database import Base, DB_NAME_USER

class AspNetUserRoles(Base):
    __tablename__ = "AspNetUserRoles"
    __table_args__ = {"schema": DB_NAME_USER}

    UserId = Column(String(450), primary_key=True)
    RoleId = Column(String(450), primary_key=True)
