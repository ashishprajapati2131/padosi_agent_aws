from pydantic import BaseModel, Field
from typing import Optional


class AppVersionResponse(BaseModel):
    platform: str = Field(..., description="android or ios")
    latest_version: str = Field(..., description="Newest version available on the store")
    min_supported_version: str = Field(..., description="Oldest version allowed to keep running")
    current_version: Optional[str] = Field(None, description="Version the client reported, echoed back")
    update_available: bool = Field(..., description="True if a newer version than current exists")
    update_required: bool = Field(..., description="True if the app must update before continuing")
    force_update: bool = Field(..., description="Platform-level force flag")
    update_message: str = Field("", description="Message to show on the update prompt")
    store_url: str = Field("", description="Store link to open")
