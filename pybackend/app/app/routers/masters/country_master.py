from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

class CountryResponse(BaseModel):
    countryId: int
    countryCode: str
    countryName: str
    isActive: bool
    createdDate: Optional[datetime] = None # made optional to avoid validation errors if null
    createdBy: int
    createdIp: Optional[str] = None

class CreateCountryRequest(BaseModel):
    countryCode: str
    countryName: str
    isActive: bool
    createdBy: int
    createdIp: Optional[str] = ""

class CheckCountryIdHeader(BaseModel):
    CountryId: int

class UpdateCountryRequest(BaseModel):
    Header: CheckCountryIdHeader
    countryCode: Optional[str]
    countryName: Optional[str]
    isActive: Optional[bool]
    modifiedBy: int
    modifiedIp: Optional[str] = ""



