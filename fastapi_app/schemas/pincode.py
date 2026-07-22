from pydantic import BaseModel, Field
from typing import List, Dict, Any

class PincodeResponse(BaseModel):
    pincode: str = Field(..., description="The 6-digit Indian postal code")
    city_name: str = Field(..., description="The resolved district/city name")
    postal_data: List[Dict[str, Any]] = Field(..., description="Raw array of post office details from the postal directory")
