from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Dict, Any, List
import re


ALLOWED_BANNER_STYLES = {
    "profile",
    "gradient_navy",
    "gradient_emerald",
    "gradient_indigo",
    "gradient_sunset",
    "gradient_purple",
    "custom",
}


class DigitalCardConfigSchema(BaseModel):
    agency_name: str = ""
    tagline: str = ""
    bio: str = ""
    theme_color: str = "#0B1F3A"
    banner_style: str = "profile"
    custom_banner_path: str = ""
    whatsapp_msg: str = ""
    show_call: bool = True
    show_whatsapp: bool = True
    show_email: bool = True
    show_address: bool = True
    show_save_contact: bool = True
    show_lead_form: bool = True
    show_services: bool = True
    show_reviews: bool = True
    show_qr_card: bool = True
    custom_button_label: str = ""
    custom_button_url: str = ""


class DigitalCardUpdateRequest(BaseModel):
    agency_name: Optional[str] = Field(None, max_length=255)
    card_tagline: Optional[str] = Field(None, max_length=255)
    card_bio: Optional[str] = Field(None, max_length=1000)
    theme_color: Optional[str] = None
    banner_style: Optional[str] = None
    whatsapp_msg: Optional[str] = Field(None, max_length=500)
    show_call: Optional[bool] = None
    show_whatsapp: Optional[bool] = None
    show_email: Optional[bool] = None
    show_address: Optional[bool] = None
    show_save_contact: Optional[bool] = None
    show_lead_form: Optional[bool] = None
    show_services: Optional[bool] = None
    show_reviews: Optional[bool] = None
    show_qr_card: Optional[bool] = None
    custom_button_label: Optional[str] = Field(None, max_length=100)
    custom_button_url: Optional[str] = Field(None, max_length=500)

    @field_validator("theme_color")
    @classmethod
    def validate_theme_color(cls, v):
        if v is None or v == "":
            return v
        if not re.match(r"^#[A-Fa-f0-9]{6}$", v.strip()):
            raise ValueError("theme_color must be a hex color like #0B1F3A")
        return v.strip()

    @field_validator("banner_style")
    @classmethod
    def validate_banner_style(cls, v):
        if v is None or v == "":
            return v
        if v not in ALLOWED_BANNER_STYLES:
            raise ValueError(f"banner_style must be one of: {sorted(ALLOWED_BANNER_STYLES)}")
        return v


class StudioPermissionsSchema(BaseModel):
    allow_theme_customization: bool = True
    allow_custom_banner: bool = True
    allow_custom_logo: bool = True
    allow_custom_button: bool = True
    allow_lead_form_toggle: bool = True


class DigitalCardStudioStateResponse(BaseModel):
    success: bool = True
    feature_enabled: bool
    is_card_visible: bool = True
    studio: Dict[str, Any] = {}
    permissions: StudioPermissionsSchema
    card_config: DigitalCardConfigSchema
    effective_sections: Dict[str, bool] = {}
    agency_logo_url: Optional[str] = None
    card_banner_css: Optional[str] = None
    card_url: Optional[str] = None
    qr_url: Optional[str] = None
    vcard_url: Optional[str] = None
    profile_photo_url: Optional[str] = None
    display_name: Optional[str] = None
    message: Optional[str] = None


class DigitalCardUpdateResponse(BaseModel):
    success: bool
    message: str
    card_config: DigitalCardConfigSchema
    agency_logo_url: Optional[str] = None
    card_banner_css: Optional[str] = None
    agency_name: str = ""
    card_tagline: str = ""


class DigitalCardShareResponse(BaseModel):
    success: bool = True
    card_url: str
    qr_url: str
    vcard_url: str
    whatsapp_share_url: Optional[str] = None
    invite_templates: List[Dict[str, Any]] = []


class PublicDigitalCardResponse(BaseModel):
    success: bool = True
    slug: str
    display_name: str
    agency_name: str = ""
    tagline: str = ""
    bio: str = ""
    theme_color: str = "#0B1F3A"
    banner_style: str = "profile"
    card_banner_css: Optional[str] = None
    agency_logo_url: Optional[str] = None
    profile_photo_url: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    whatsapp_url: Optional[str] = None
    call_url: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    effective_sections: Dict[str, bool] = {}
    custom_button_label: str = ""
    custom_button_url: str = ""
    card_url: str = ""
    qr_url: str = ""
    vcard_url: str = ""
    average_rating: float = 0.0
    review_count: int = 0
    services: List[str] = []
    show_powered_by: bool = True
    powered_by_text: str = "Powered by PadosiAgent"


class DigitalCardLeadRequest(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_mobile: str = Field(..., min_length=10, max_length=15)
    customer_email: Optional[str] = None
    customer_pincode: Optional[str] = None
    insurance_type: Optional[str] = None
    service_type: Optional[str] = None
    message: Optional[str] = None


class DigitalCardLeadResponse(BaseModel):
    success: bool
    message: str
    already_submitted: bool = False
    lead_id: Optional[int] = None


class InviteStudioResponse(BaseModel):
    success: bool = True
    languages: Dict[str, Any] = {}
    links: Dict[str, str] = {}
    rendered_defaults: Dict[str, str] = {}
