from sqlalchemy import Column, Integer, String, DateTime, text
from ..database import Base
import os

# Get the Purchase DB name from env or default
purchase_db = os.getenv('DB_NAME_PURCHASE', 'btggasify_purchase_live')

class PrAttachment(Base):
    __tablename__ = "tbl_purchaserequisition_attachment"
    __table_args__ = {"schema": purchase_db}

    prattachid = Column(Integer, primary_key=True, index=True)
    prid = Column(Integer, nullable=True)
    filepath = Column(String(500), nullable=True)
    filename = Column(String(255), nullable=True)
    isactive = Column(Integer, default=1)
    
    # Audit fields
    modifiedby = Column(Integer, nullable=True)
    modifieddate = Column(DateTime, nullable=True)
    modifiedip = Column(String(50), nullable=True)
    
    # Add other columns if necessary based on existing schema, 
    # but these are the ones required for the task.
