"""Digital Visiting Card service — keeps FastAPI in sync with Django card studio."""

from __future__ import annotations

import io
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fastapi_app.config import settings
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_lead import AgentLead
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.models.agent_review import AgentReview
from fastapi_app.models.site_setting import SiteSetting
from fastapi_app.schemas.digital_card import (
    ALLOWED_BANNER_STYLES,
    DigitalCardConfigSchema,
    DigitalCardUpdateRequest,
    StudioPermissionsSchema,
)
from fastapi_app.services.local_storage_service import LocalStorageService

logger = logging.getLogger(__name__)

SECTION_POLICY_MAP = {
    "call": "policy_call",
    "whatsapp": "policy_whatsapp",
    "email": "policy_email",
    "address": "policy_address",
    "save_contact": "policy_save_contact",
    "lead_form": "policy_lead_form",
    "services": "policy_services",
    "reviews": "policy_reviews",
    "qr_card": "policy_qr_card",
}

SHOW_KEY_MAP = {
    "call": "show_call",
    "whatsapp": "show_whatsapp",
    "email": "show_email",
    "address": "show_address",
    "save_contact": "show_save_contact",
    "lead_form": "show_lead_form",
    "services": "show_services",
    "reviews": "show_reviews",
    "qr_card": "show_qr_card",
}

BANNER_GRADIENTS = {
    "gradient_navy": "linear-gradient(135deg, #0B1F3A 0%, #1E3A8A 50%, #0D9488 100%)",
    "gradient_emerald": "linear-gradient(135deg, #064E3B 0%, #059669 50%, #10B981 100%)",
    "gradient_indigo": "linear-gradient(135deg, #1E1B4B 0%, #4338CA 50%, #6366F1 100%)",
    "gradient_sunset": "linear-gradient(135deg, #7C2D12 0%, #C2410C 50%, #F59E0B 100%)",
    "gradient_purple": "linear-gradient(135deg, #4C1D95 0%, #7C3AED 50%, #A855F7 100%)",
}


class DigitalCardService:
    def __init__(self, db: Session):
        self.db = db

    # ── Site / studio helpers ───────────────────────────────────────────

    def is_feature_enabled(self) -> bool:
        try:
            from apps.admin_panel.services.digital_card_studio import (
                get_digital_card_studio_config,
            )

            return bool(get_digital_card_studio_config().get("enabled", True))
        except Exception:
            row = (
                self.db.query(SiteSetting)
                .filter(SiteSetting.key == "agent_digital_card_enabled")
                .first()
            )
            if not row:
                return True
            return str(row.value or "").strip().lower() in ("1", "true", "yes", "on")

    def get_studio_config(self) -> Dict[str, Any]:
        try:
            from apps.admin_panel.services.digital_card_studio import (
                get_digital_card_studio_config,
            )

            return get_digital_card_studio_config()
        except Exception as e:
            logger.warning("digital_card_studio_config fallback: %s", e)
            return {"enabled": self.is_feature_enabled()}

    def _require_feature(self):
        if not self.is_feature_enabled():
            raise HTTPException(
                status_code=403,
                detail="Digital Visiting Card feature is currently disabled by administrator.",
            )

    # ── Profile / media URL helpers ─────────────────────────────────────

    def get_or_create_profile(self, agent_id: int) -> AgentProfile:
        profile = (
            self.db.query(AgentProfile)
            .filter(AgentProfile.agent_id == agent_id)
            .first()
        )
        if not profile:
            profile = AgentProfile(agent_id=agent_id)
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        return profile

    def get_profile_by_slug(self, slug: str) -> Tuple[Optional[Agent], Optional[AgentProfile]]:
        if not slug:
            return None, None
        raw = str(slug).strip()
        profile = (
            self.db.query(AgentProfile)
            .filter(AgentProfile.slug == raw)
            .first()
        )
        if not profile:
            profile = (
                self.db.query(AgentProfile)
                .filter(AgentProfile.slug.ilike(raw))
                .first()
            )
        if profile:
            agent = self.db.query(Agent).filter(Agent.id == profile.agent_id).first()
            return agent, profile
        if raw.isdigit():
            agent = self.db.query(Agent).filter(Agent.id == int(raw)).first()
            if agent:
                return agent, self.get_or_create_profile(agent.id)
        return None, None

    @staticmethod
    def media_url(path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        path_clean = re.sub(r"[\'\"<>\(\)\s;]", "", str(path).strip())
        if not path_clean:
            return None
        if path_clean.startswith(("http://", "https://")):
            return path_clean
        path_norm = path_clean.replace("\\", "/").lstrip("/")
        if path_norm.startswith("static/") or path_norm.startswith("media/"):
            return f"/{path_norm}"
        return f"/media/{path_norm}"

    @staticmethod
    def delete_stored_path(path: Optional[str]) -> None:
        """Delete a Django-relative storage path (e.g. app/public/agency_logos/...)."""
        if not path:
            return
        path_norm = str(path).replace("\\", "/").lstrip("/")
        if path_norm.startswith("media/"):
            path_norm = path_norm[len("media/") :]
        if ".." in path_norm or path_norm.startswith("/"):
            return
        full = os.path.join(settings.LOCAL_STORAGE_PATH, path_norm)
        try:
            if os.path.isfile(full):
                os.remove(full)
        except Exception:
            pass
        try:
            LocalStorageService.delete_file(f"/media/{path_norm}")
        except Exception:
            pass

    def app_base(self) -> str:
        return (settings.APP_URL or "http://localhost:8000").rstrip("/")

    def card_urls(self, slug: str) -> Dict[str, str]:
        base = self.app_base()
        api = f"{base}/api"
        return {
            "card_url": f"{base}/card/{slug}/",
            "qr_url": f"{api}/v1/public/digital-card/{slug}/qr.png",
            "vcard_url": f"{api}/v1/public/digital-card/{slug}/vcard",
        }

    # ── card_config merge (mirrors AgentProfile.get_card_config) ────────

    def merge_card_config(
        self, profile: AgentProfile, agent: Optional[Agent] = None
    ) -> Dict[str, Any]:
        cfg = dict(profile.card_config) if isinstance(profile.card_config, dict) else {}
        agent_name = (
            (profile.display_name or "")
            or (agent.fullname if agent else "")
            or "Advisor"
        ).strip()
        defaults = {
            "agency_name": (profile.agency_name or "").strip(),
            "tagline": (profile.card_tagline or "").strip(),
            "bio": "",
            "theme_color": "#0B1F3A",
            "banner_style": "profile",
            "custom_banner_path": "",
            "whatsapp_msg": (
                f"Hello {agent_name}, I viewed your Digital Visiting Card and "
                "would like consultation regarding insurance plans."
            ),
            "show_call": True,
            "show_whatsapp": True,
            "show_email": True,
            "show_address": True,
            "show_save_contact": True,
            "show_lead_form": True,
            "show_services": True,
            "show_reviews": True,
            "show_qr_card": True,
            "custom_button_label": "",
            "custom_button_url": "",
        }
        for k, v in defaults.items():
            if k not in cfg:
                cfg[k] = v
        if profile.card_tagline and not cfg.get("tagline"):
            cfg["tagline"] = profile.card_tagline
        if profile.agency_name and not cfg.get("agency_name"):
            cfg["agency_name"] = profile.agency_name
        return cfg

    def resolve_effective_sections(
        self, cfg: Dict[str, Any], studio_cfg: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        studio_cfg = studio_cfg or self.get_studio_config()
        try:
            from apps.admin_panel.services.digital_card_studio import (
                resolve_effective_section_visibility,
            )

            resolve = resolve_effective_section_visibility
        except Exception:

            def resolve(policy_key, agent_val, studio=None):
                policy = (studio or studio_cfg).get(policy_key, "allow_agent")
                if policy == "always_show":
                    return True
                if policy == "always_hide":
                    return False
                return True if agent_val is None else bool(agent_val)

        out = {}
        for section, policy_key in SECTION_POLICY_MAP.items():
            show_key = SHOW_KEY_MAP[section]
            out[section] = resolve(policy_key, cfg.get(show_key, True), studio_cfg)
        return out

    def card_banner_css(self, profile: AgentProfile, cfg: Dict[str, Any]) -> str:
        style = cfg.get("banner_style", "profile")
        if style in BANNER_GRADIENTS:
            return BANNER_GRADIENTS[style]
        if style == "custom" and cfg.get("custom_banner_path"):
            url = self.media_url(cfg.get("custom_banner_path"))
            if url:
                return f"url('{url}') center/cover no-repeat"
        return BANNER_GRADIENTS["gradient_navy"]

    def _sanitize_custom_url(self, custom_url: str) -> str:
        if not custom_url:
            return ""
        lower_url = re.sub(r"[\x00-\x20\x7f]+", "", custom_url).lower()
        if lower_url.startswith(("javascript:", "data:", "vbscript:")):
            return ""
        if not lower_url.startswith(("http://", "https://")):
            return f"https://{custom_url.lstrip('/')}"
        return custom_url

    # ── Authenticated studio ────────────────────────────────────────────

    def get_studio_state(self, agent: Agent) -> Dict[str, Any]:
        feature_enabled = self.is_feature_enabled()
        profile = self.get_or_create_profile(agent.id)
        studio = self.get_studio_config()
        cfg = self.merge_card_config(profile, agent)
        slug = (profile.slug or "").strip() or str(agent.id)
        urls = self.card_urls(slug)
        permissions = StudioPermissionsSchema(
            allow_theme_customization=bool(studio.get("allow_theme_customization", True)),
            allow_custom_banner=bool(studio.get("allow_custom_banner", True)),
            allow_custom_logo=bool(studio.get("allow_custom_logo", True)),
            allow_custom_button=bool(studio.get("allow_custom_button", True)),
            allow_lead_form_toggle=bool(studio.get("allow_lead_form_toggle", True)),
        )
        return {
            "success": True,
            "feature_enabled": feature_enabled,
            "is_card_visible": bool(getattr(profile, "is_card_visible", True)),
            "studio": {
                "studio_title": studio.get("studio_title"),
                "studio_subtitle": studio.get("studio_subtitle"),
                "default_theme_color": studio.get("default_theme_color"),
                "default_banner_style": studio.get("default_banner_style"),
                "default_card_tagline": studio.get("default_card_tagline"),
                "default_card_bio": studio.get("default_card_bio"),
                "show_powered_by_badge": studio.get("show_powered_by_badge", True),
                "powered_by_text": studio.get("powered_by_text", "Powered by PadosiAgent"),
                "policies": {k: studio.get(v, "allow_agent") for k, v in SECTION_POLICY_MAP.items()},
            },
            "permissions": permissions,
            "card_config": DigitalCardConfigSchema(**{k: cfg.get(k) for k in DigitalCardConfigSchema.model_fields}),
            "effective_sections": self.resolve_effective_sections(cfg, studio),
            "agency_logo_url": self.media_url(profile.agency_logo_path),
            "card_banner_css": self.card_banner_css(profile, cfg),
            "card_url": urls["card_url"],
            "qr_url": urls["qr_url"],
            "vcard_url": urls["vcard_url"],
            "profile_photo_url": self.media_url(profile.profile_photo_path),
            "display_name": (profile.display_name or agent.fullname or "").strip(),
            "message": None
            if feature_enabled
            else "Digital Visiting Card feature is currently disabled by administrator.",
        }

    def update_card(
        self, agent: Agent, payload: DigitalCardUpdateRequest
    ) -> Dict[str, Any]:
        self._require_feature()
        profile = self.get_or_create_profile(agent.id)
        studio = self.get_studio_config()
        cfg = self.merge_card_config(profile, agent)
        data = payload.model_dump(exclude_unset=True)

        if "agency_name" in data and data["agency_name"] is not None:
            agency_name = (data["agency_name"] or "")[:255]
            profile.agency_name = agency_name
            cfg["agency_name"] = agency_name

        if "card_tagline" in data and data["card_tagline"] is not None:
            tagline = (data["card_tagline"] or "")[:255]
            profile.card_tagline = tagline
            cfg["tagline"] = tagline

        if "card_bio" in data and data["card_bio"] is not None:
            cfg["bio"] = (data["card_bio"] or "")[:1000]

        if data.get("theme_color") and studio.get("allow_theme_customization", True):
            cfg["theme_color"] = data["theme_color"]

        if data.get("banner_style") and (
            data["banner_style"] != "custom" or studio.get("allow_custom_banner", True)
        ):
            if data["banner_style"] in ALLOWED_BANNER_STYLES:
                cfg["banner_style"] = data["banner_style"]

        if "whatsapp_msg" in data and data["whatsapp_msg"] is not None:
            cfg["whatsapp_msg"] = (data["whatsapp_msg"] or "")[:500]

        for key in (
            "show_call",
            "show_whatsapp",
            "show_email",
            "show_address",
            "show_save_contact",
            "show_services",
            "show_reviews",
            "show_qr_card",
        ):
            if key in data and data[key] is not None:
                cfg[key] = bool(data[key])

        if "show_lead_form" in data and data["show_lead_form"] is not None:
            if studio.get("allow_lead_form_toggle", True):
                cfg["show_lead_form"] = bool(data["show_lead_form"])

        if studio.get("allow_custom_button", True):
            if "custom_button_label" in data and data["custom_button_label"] is not None:
                cfg["custom_button_label"] = (data["custom_button_label"] or "")[:100]
            if "custom_button_url" in data and data["custom_button_url"] is not None:
                cfg["custom_button_url"] = self._sanitize_custom_url(
                    (data["custom_button_url"] or "")[:500]
                )

        profile.card_config = cfg
        self.db.commit()
        self.db.refresh(profile)
        cfg = self.merge_card_config(profile, agent)
        return {
            "success": True,
            "message": "Digital Visiting Card customizations saved successfully!",
            "card_config": DigitalCardConfigSchema(
                **{k: cfg.get(k) for k in DigitalCardConfigSchema.model_fields}
            ),
            "agency_logo_url": self.media_url(profile.agency_logo_path),
            "card_banner_css": self.card_banner_css(profile, cfg),
            "agency_name": profile.agency_name or "",
            "card_tagline": profile.card_tagline or "",
        }

    def upload_logo(self, agent: Agent, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        self._require_feature()
        studio = self.get_studio_config()
        if not studio.get("allow_custom_logo", True):
            raise HTTPException(status_code=403, detail="Custom logo is not allowed.")
        from fastapi_app.utils.image_validation import validate_image_file

        sanitized = validate_image_file(file_bytes, filename or "logo.jpg", "image/jpeg")
        profile = self.get_or_create_profile(agent.id)
        if profile.agency_logo_path:
            self.delete_stored_path(profile.agency_logo_path)
        ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = ".jpg"
        relative = f"app/public/agency_logos/agent_{agent.id}_{int(time.time())}{ext}"
        LocalStorageService.save_django_path_file(sanitized, relative)
        profile.agency_logo_path = relative
        self.db.commit()
        self.db.refresh(profile)
        return {
            "success": True,
            "message": "Agency logo uploaded.",
            "agency_logo_url": self.media_url(profile.agency_logo_path),
        }

    def delete_logo(self, agent: Agent) -> Dict[str, Any]:
        self._require_feature()
        profile = self.get_or_create_profile(agent.id)
        if profile.agency_logo_path:
            self.delete_stored_path(profile.agency_logo_path)
        profile.agency_logo_path = None
        self.db.commit()
        return {"success": True, "message": "Agency logo removed.", "agency_logo_url": None}

    def upload_banner(
        self, agent: Agent, file_bytes: bytes, filename: str
    ) -> Dict[str, Any]:
        self._require_feature()
        studio = self.get_studio_config()
        if not studio.get("allow_custom_banner", True):
            raise HTTPException(status_code=403, detail="Custom banner is not allowed.")
        from fastapi_app.utils.image_validation import validate_image_file

        sanitized = validate_image_file(file_bytes, filename or "banner.jpg", "image/jpeg")
        profile = self.get_or_create_profile(agent.id)
        cfg = self.merge_card_config(profile, agent)
        old = cfg.get("custom_banner_path")
        if old:
            self.delete_stored_path(old)
        ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = ".jpg"
        relative = f"app/public/card_banners/agent_{agent.id}_{int(time.time())}{ext}"
        LocalStorageService.save_django_path_file(sanitized, relative)
        cfg["custom_banner_path"] = relative
        cfg["banner_style"] = "custom"
        profile.card_config = cfg
        self.db.commit()
        self.db.refresh(profile)
        cfg = self.merge_card_config(profile, agent)
        return {
            "success": True,
            "message": "Custom banner uploaded.",
            "card_config": DigitalCardConfigSchema(
                **{k: cfg.get(k) for k in DigitalCardConfigSchema.model_fields}
            ),
            "card_banner_css": self.card_banner_css(profile, cfg),
        }

    def delete_banner(self, agent: Agent) -> Dict[str, Any]:
        self._require_feature()
        profile = self.get_or_create_profile(agent.id)
        cfg = self.merge_card_config(profile, agent)
        old = cfg.get("custom_banner_path")
        if old:
            self.delete_stored_path(old)
        cfg["custom_banner_path"] = ""
        if cfg.get("banner_style") == "custom":
            cfg["banner_style"] = "profile"
        profile.card_config = cfg
        self.db.commit()
        self.db.refresh(profile)
        cfg = self.merge_card_config(profile, agent)
        return {
            "success": True,
            "message": "Custom banner removed.",
            "card_config": DigitalCardConfigSchema(
                **{k: cfg.get(k) for k in DigitalCardConfigSchema.model_fields}
            ),
            "card_banner_css": self.card_banner_css(profile, cfg),
        }

    def get_preview(self, agent: Agent) -> Dict[str, Any]:
        state = self.get_studio_state(agent)
        public = self.build_public_payload(agent, self.get_or_create_profile(agent.id))
        return {"success": True, "studio": state, "preview": public}

    def get_share_pack(self, agent: Agent) -> Dict[str, Any]:
        profile = self.get_or_create_profile(agent.id)
        slug = (profile.slug or "").strip() or str(agent.id)
        urls = self.card_urls(slug)
        display = (profile.display_name or agent.fullname or "Advisor").strip()
        wa_text = quote(f"Here is my Digital Visiting Card on PadosiAgent:\n{urls['card_url']}")
        invite = self.get_invite_studio(agent)
        return {
            "success": True,
            "card_url": urls["card_url"],
            "qr_url": urls["qr_url"],
            "vcard_url": urls["vcard_url"],
            "whatsapp_share_url": f"https://api.whatsapp.com/send?text={wa_text}",
            "invite_templates": invite.get("rendered_defaults_list", []),
            "display_name": display,
        }

    def get_invite_studio(self, agent: Agent) -> Dict[str, Any]:
        profile = self.get_or_create_profile(agent.id)
        slug = (profile.slug or "").strip() or str(agent.id)
        state = (profile.state or "gj").strip().lower()[:2] or "gj"
        base = self.app_base()
        links = {
            "card_link": f"{base}/card/{slug}/",
            "review_link": f"{base}/{state}/{slug}/review/",
            "profile_link": f"{base}/{state}/{slug}/",
            "referral_link": f"{base}/register/?ref={agent.id}",
        }
        display = (profile.display_name or agent.fullname or "Advisor").strip()
        rendered = {}
        languages = {}
        try:
            from apps.agents.services.invite_studio import (
                get_invite_studio_config,
                render_template_text,
                STUDIO_TEMPLATES,
            )

            cfg = get_invite_studio_config()
            languages = cfg if isinstance(cfg, dict) else {}
            # Prefer built-in review EN first template as default rendered samples
            for section_key, section in STUDIO_TEMPLATES.items():
                langs = section.get("languages") or {}
                en = langs.get("en") or {}
                templates = en.get("templates") or []
                if templates:
                    raw = templates[0].get("text") or ""
                    rendered[section_key] = render_template_text(
                        raw,
                        display,
                        links["profile_link"],
                        links["review_link"],
                        links["card_link"],
                        links["referral_link"],
                    )
        except Exception as e:
            logger.warning("invite studio load failed: %s", e)
            rendered = {
                "review": f"Please leave a review: {links['review_link']}",
                "social": f"My digital card: {links['card_link']}",
            }
        return {
            "success": True,
            "languages": languages or {},
            "links": links,
            "rendered_defaults": rendered,
            "rendered_defaults_list": [
                {"id": k, "text": v} for k, v in rendered.items()
            ],
        }

    # ── Public card ─────────────────────────────────────────────────────

    def _agent_hidden(self, agent: Agent) -> bool:
        try:
            from apps.agents.services.account_auth import agent_account_is_active

            if not agent_account_is_active(agent):
                return True
        except Exception:
            pass
        status = (getattr(agent, "status", "") or "").lower()
        if status in (
            "suspended",
            "blacklisted",
            "rejected",
            "deleted",
            "pending_payment",
            "pending",
        ):
            # pending_payment / unpaid should hide — match Django _PUBLIC_HIDDEN if possible
            try:
                from apps.agents.views.qr import _hidden_from_public
                from apps.agents.models import Agent as DjangoAgent

                dj = DjangoAgent.objects.filter(id=agent.id).first()
                if dj is not None:
                    return _hidden_from_public(dj)
            except Exception:
                pass
            if status in ("suspended", "blacklisted", "rejected", "deleted"):
                return True
        return bool(getattr(agent, "is_blacklisted", False))

    def build_public_payload(
        self, agent: Agent, profile: AgentProfile
    ) -> Dict[str, Any]:
        self._require_feature()
        if self._agent_hidden(agent):
            raise HTTPException(status_code=404, detail="Agent not found")
        if not bool(getattr(profile, "is_card_visible", True)):
            raise HTTPException(status_code=404, detail="Digital card is not available")

        studio = self.get_studio_config()
        cfg = self.merge_card_config(profile, agent)
        sections = self.resolve_effective_sections(cfg, studio)
        slug = (profile.slug or "").strip() or str(agent.id)
        urls = self.card_urls(slug)
        display = (profile.display_name or agent.fullname or "Advisor").strip()

        tagline = (
            cfg.get("tagline")
            or profile.card_tagline
            or studio.get("default_card_tagline")
            or ""
        ).strip()
        bio = (
            cfg.get("bio")
            or profile.career_highlights
            or studio.get("default_card_bio")
            or ""
        ).strip()
        theme = cfg.get("theme_color") or studio.get("default_theme_color") or "#0B1F3A"
        if not re.match(r"^#[A-Fa-f0-9]{6}$", str(theme)):
            theme = "#0B1F3A"

        mobile_raw = str(getattr(agent, "mobile", "") or profile.whatsapp or "").strip()
        whatsapp_raw = str(profile.whatsapp or getattr(agent, "mobile", "") or "").strip()
        mobile_digits = re.sub(r"[^0-9]", "", mobile_raw)
        whatsapp_digits = re.sub(r"[^0-9]", "", whatsapp_raw)
        if len(whatsapp_digits) == 10:
            whatsapp_digits = "91" + whatsapp_digits
        wa_msg = cfg.get("whatsapp_msg") or studio.get("default_whatsapp_msg") or ""
        wa_msg = str(wa_msg).replace("{agent_name}", display)
        whatsapp_url = (
            f"https://api.whatsapp.com/send?phone={whatsapp_digits}&text={quote(wa_msg)}"
            if whatsapp_digits and sections.get("whatsapp")
            else None
        )
        call_url = None
        if sections.get("call") and len(mobile_digits) >= 10:
            call_url = f"tel:+91{mobile_digits[-10:]}"

        address = (profile.office_address or profile.address or "").strip()
        maps = (
            f"https://www.google.com/maps/search/?api=1&query={quote(address)}"
            if address and sections.get("address")
            else None
        )

        approved = (
            self.db.query(AgentReview)
            .filter(
                AgentReview.agent_id == agent.id,
                AgentReview.is_approved == True,
            )
            .all()
        )
        review_count = len(approved)
        avg = (
            round(sum(r.rating for r in approved) / review_count, 1)
            if review_count
            else 0.0
        )

        services = []
        try:
            from fastapi_app.models.agent_insurance_segment import AgentInsuranceSegment

            segs = (
                self.db.query(AgentInsuranceSegment)
                .filter(AgentInsuranceSegment.agent_id == agent.id)
                .all()
            )
            services = [s.segment_type for s in segs if getattr(s, "segment_type", None)]
        except Exception:
            pass

        return {
            "success": True,
            "slug": slug,
            "display_name": display,
            "agency_name": (cfg.get("agency_name") or profile.agency_name or "").strip(),
            "tagline": tagline,
            "bio": bio,
            "theme_color": theme,
            "banner_style": cfg.get("banner_style") or "profile",
            "card_banner_css": self.card_banner_css(profile, cfg),
            "agency_logo_url": self.media_url(profile.agency_logo_path),
            "profile_photo_url": self.media_url(profile.profile_photo_path),
            "mobile": mobile_digits[-10:] if len(mobile_digits) >= 10 else mobile_digits or None,
            "email": agent.email if sections.get("email") else None,
            "whatsapp_url": whatsapp_url,
            "call_url": call_url,
            "address": address if sections.get("address") else None,
            "google_maps_url": maps,
            "effective_sections": sections,
            "custom_button_label": cfg.get("custom_button_label") or "",
            "custom_button_url": cfg.get("custom_button_url") or "",
            "card_url": urls["card_url"],
            "qr_url": urls["qr_url"],
            "vcard_url": urls["vcard_url"],
            "average_rating": avg,
            "review_count": review_count,
            "services": services if sections.get("services") else [],
            "show_powered_by": bool(studio.get("show_powered_by_badge", True)),
            "powered_by_text": studio.get("powered_by_text") or "Powered by PadosiAgent",
        }

    def get_public_card(self, slug: str) -> Dict[str, Any]:
        agent, profile = self.get_profile_by_slug(slug)
        if not agent or not profile:
            raise HTTPException(status_code=404, detail="Agent not found")
        return self.build_public_payload(agent, profile)

    def build_vcard(self, slug: str) -> Tuple[bytes, str]:
        agent, profile = self.get_profile_by_slug(slug)
        if not agent or not profile:
            raise HTTPException(status_code=404, detail="Agent not found")
        self._require_feature()
        if self._agent_hidden(agent) or not bool(getattr(profile, "is_card_visible", True)):
            raise HTTPException(status_code=404, detail="Digital card is not available")

        name = (profile.display_name or agent.fullname or "Insurance Advisor").strip()
        parts = name.split(" ", 1)
        first_name, last_name = parts[0], (parts[1] if len(parts) > 1 else "")
        mobile = getattr(agent, "mobile", "") or profile.whatsapp or ""
        email = agent.email or ""
        agency = profile.agency_name or "PadosiAgent"
        address = profile.office_address or profile.address or ""
        agent_slug = (profile.slug or "").strip() or str(slug)
        state = (profile.state or "gj").strip().lower()[:2] or "gj"
        profile_url = f"{self.app_base()}/{state}/{agent_slug}/"

        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN;CHARSET=UTF-8:{name}",
            f"N;CHARSET=UTF-8:{last_name};{first_name};;;",
            f"ORG;CHARSET=UTF-8:{agency}",
            "TITLE;CHARSET=UTF-8:Certified Insurance Advisor",
        ]
        if mobile:
            lines.append(f"TEL;TYPE=CELL,VOICE;CHARSET=UTF-8:{mobile}")
        if email:
            lines.append(f"EMAIL;TYPE=PREF,INTERNET:{email}")
        if profile_url:
            lines.append(f"URL;CHARSET=UTF-8:{profile_url}")
        if address:
            lines.append(f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{address};;;;India")
        lines.append("NOTE;CHARSET=UTF-8:Registered Insurance Advisor on PadosiAgent")
        lines.append("END:VCARD")
        content = ("\r\n".join(lines) + "\r\n").encode("utf-8")
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", agent_slug).strip("-") or "advisor"
        return content, f"PadosiAgent-{safe}.vcf"

    def build_qr_png(self, slug: str) -> bytes:
        agent, profile = self.get_profile_by_slug(slug)
        if not agent or not profile:
            raise HTTPException(status_code=404, detail="Agent not found")
        self._require_feature()
        if self._agent_hidden(agent) or not bool(getattr(profile, "is_card_visible", True)):
            raise HTTPException(status_code=404, detail="Digital card is not available")

        agent_slug = (profile.slug or "").strip() or str(slug)
        card_url = f"{self.app_base()}/card/{agent_slug}/"
        try:
            from django.core.cache import cache

            cache_key = f"pure_card_qr:{agent_slug}:v2"
            cached = cache.get(cache_key)
            if cached:
                return cached
        except Exception:
            cache = None
            cache_key = None

        import qrcode

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=12,
            border=2,
        )
        qr.add_data(card_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color=(0, 0, 0), back_color=(255, 255, 255)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        if cache is not None and cache_key:
            try:
                cache.set(cache_key, png_bytes, 86400)
            except Exception:
                pass
        return png_bytes

    def submit_lead(
        self, slug: str, payload: Dict[str, Any], client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        self._require_feature()
        agent, profile = self.get_profile_by_slug(slug)
        if not agent or not profile:
            raise HTTPException(status_code=404, detail="Agent not found")
        if self._agent_hidden(agent) or not bool(getattr(profile, "is_card_visible", True)):
            raise HTTPException(status_code=404, detail="Agent not found")

        # Prefer Django path for rate-limit + notifications parity
        try:
            from apps.agents.models import Agent as DjangoAgent, AgentLead as DjangoLead
            from django.utils import timezone
            from django.core.cache import cache
            from apps.wa_agent_bot.services.notification_service import notify_agent_new_lead

            dj_agent = DjangoAgent.objects.filter(id=agent.id).first()
            if not dj_agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            customer_name = (payload.get("customer_name") or "").strip()
            customer_mobile = (payload.get("customer_mobile") or "").strip()
            clean_mobile = re.sub(r"[^0-9]", "", customer_mobile)
            if len(clean_mobile) > 10 and clean_mobile.startswith("91"):
                clean_mobile = clean_mobile[-10:]
            if not customer_name:
                raise HTTPException(status_code=400, detail="Please enter your full name.")
            if len(clean_mobile) < 10:
                raise HTTPException(
                    status_code=400, detail="Please enter a valid 10-digit mobile number."
                )

            if client_ip:
                rl_keys = (
                    (f"rl_card_lead_10m_{client_ip}", 5, 10 * 60),
                    (f"rl_card_lead_day_{client_ip}", 20, 24 * 60 * 60),
                )
                if any((cache.get(key, 0) or 0) >= limit for key, limit, _w in rl_keys):
                    raise HTTPException(
                        status_code=429,
                        detail="Too many enquiries submitted from your network. Please try again later.",
                    )

            ten_mins_ago = timezone.now() - timezone.timedelta(minutes=10)
            existing = DjangoLead.objects.filter(
                agent=dj_agent,
                customer_mobile=clean_mobile,
                created_at__gte=ten_mins_ago,
            ).first()
            if existing:
                return {
                    "success": True,
                    "message": "We have already received your enquiry. The advisor will connect with you shortly!",
                    "already_submitted": True,
                    "lead_id": existing.id,
                }

            insurance_type = (payload.get("insurance_type") or "").strip() or "General Insurance"
            service_type = (payload.get("service_type") or "").strip() or "Enquiry"
            message = (payload.get("message") or "").strip()
            parts = []
            if service_type:
                parts.append(f"Requirement: {service_type}")
            if insurance_type:
                parts.append(f"Insurance: {insurance_type}")
            if message:
                parts.append(f"Message: {message}")
            enquiry = " | ".join(parts) if parts else "Digital Card Enquiry"

            lead = DjangoLead.objects.create(
                agent=dj_agent,
                customer_name=customer_name,
                customer_mobile=clean_mobile,
                customer_email=(payload.get("customer_email") or None),
                customer_pincode=(payload.get("customer_pincode") or None),
                insurance_type=insurance_type,
                service_type=service_type,
                enquiry_requirements=enquiry,
                interaction_type="digital_card_enquiry",
                lead_status="new",
                source_page="digital-card",
                ip_address=client_ip,
            )
            if client_ip:
                for key, _limit, window in (
                    (f"rl_card_lead_10m_{client_ip}", 5, 10 * 60),
                    (f"rl_card_lead_day_{client_ip}", 20, 24 * 60 * 60),
                ):
                    try:
                        if not cache.add(key, 1, timeout=window):
                            cache.incr(key)
                    except Exception:
                        pass
            try:
                notify_agent_new_lead(lead)
            except Exception as e:
                logger.warning("card lead notify failed: %s", e)
            return {
                "success": True,
                "message": "Enquiry submitted successfully. The advisor will contact you soon!",
                "already_submitted": False,
                "lead_id": lead.id,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("digital card lead via Django failed, using SQLAlchemy: %s", e)

        # Fallback SQLAlchemy create (no notify)
        customer_name = (payload.get("customer_name") or "").strip()
        clean_mobile = re.sub(r"[^0-9]", "", payload.get("customer_mobile") or "")
        if len(clean_mobile) > 10 and clean_mobile.startswith("91"):
            clean_mobile = clean_mobile[-10:]
        if not customer_name or len(clean_mobile) < 10:
            raise HTTPException(status_code=400, detail="Invalid name or mobile.")
        from datetime import datetime

        now = datetime.now()
        lead = AgentLead(
            agent_id=agent.id,
            customer_name=customer_name,
            customer_mobile=clean_mobile,
            customer_email=payload.get("customer_email"),
            customer_pincode=payload.get("customer_pincode"),
            insurance_type=payload.get("insurance_type") or "General Insurance",
            service_type=payload.get("service_type") or "Enquiry",
            enquiry_requirements=payload.get("message") or "Digital Card Enquiry",
            interaction_type="digital_card_enquiry",
            lead_status="new",
            source_page="digital-card",
            ip_address=client_ip,
            created_at=now,
            updated_at=now,
        )
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return {
            "success": True,
            "message": "Enquiry submitted successfully. The advisor will contact you soon!",
            "already_submitted": False,
            "lead_id": lead.id,
        }
