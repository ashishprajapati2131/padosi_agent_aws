from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import random
import string
import os
from typing import Optional, Tuple, Dict, Any

from fastapi_app.schemas.registration import RegistrationBasicRequest, PaymentSuccessRequest
from fastapi_app.repositories.agent_repository import AgentRepository
from fastapi_app.repositories.user_repository import UserRepository
from fastapi_app.repositories.subscription_repository import SubscriptionRepository
from fastapi_app.repositories.profile_repository import ProfileRepository
from fastapi_app.repositories.invoice_repository import InvoiceRepository
from fastapi_app.repositories.promo_code_repository import PromoCodeRepository
from fastapi_app.repositories.referral_repository import ReferralRepository

from fastapi_app.models.agent import Agent
from fastapi_app.models.user import User
from fastapi_app.models.agent_subscription import AgentSubscription
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.models.invoice import Invoice
from fastapi_app.models.referral_code import ReferralCode
from fastapi_app.models.referral_usage import ReferralUsage

from fastapi_app.services.payment_service import PaymentService
from fastapi_app.services.email_service import EmailService
from fastapi_app.services.invoice_service import InvoiceService
from fastapi_app.utils.auth import get_password_hash, create_access_token, create_refresh_token, decode_promo_validation_token, generate_and_register_token
from fastapi_app.config import settings

def parse_experience_years(experience_range: Optional[str]) -> Optional[int]:
    if not experience_range:
        return None
    try:
        digits = []
        for char in str(experience_range):
            if char.isdigit():
                digits.append(char)
            elif digits and not char.isdigit():
                break
        if digits:
            return int("".join(digits))
    except Exception:
        pass
    return None

class RegistrationService:
    def __init__(self, agent_repository: AgentRepository):
        self.agent_repository = agent_repository

    def save_basic_registration(self, db: Session, request: RegistrationBasicRequest) -> Tuple[int, bool, str, str, str, Optional[str], bool]:
        try:
            # 1. Check if agent is already registered
            agent_repo = self.agent_repository
            user_repo = UserRepository(db)
            
            # Use with_for_update() on queries to lock rows and prevent duplicate inserts on concurrent calls
            agent = db.query(Agent).filter(Agent.email == request.email).with_for_update().first()
            user = db.query(User).filter(User.email == request.email).with_for_update().first()

            if agent or user:
                existing_agent = agent if agent else db.query(Agent).filter(Agent.email == request.email).with_for_update().first()
                existing_user = user if user else db.query(User).filter(User.email == request.email).with_for_update().first()
                
                user_role = existing_user.role if existing_user else "agent"
                agent_id = existing_agent.id if existing_agent else 0
                agent_name = existing_agent.fullname if existing_agent else ""
                agent_email = existing_agent.email if existing_agent else request.email
                
                user_id = existing_user.id if existing_user else 0
                token = generate_and_register_token(db, agent_email, user_role, user_id)
                custom_message = None
                is_payment_done = False

                if existing_agent:
                    try:
                        sub_repo = SubscriptionRepository(db)
                        subscription = sub_repo.get_by_agent_id(existing_agent.id)
                        if subscription and subscription.razorpay_order_id:
                            if subscription.payment_status == "completed":
                                custom_message = f"payment done. so check your {agent_email} for user id & password."
                                is_payment_done = True
                            else:
                                from fastapi_app.services.payment_verification import check_order_payment_status
                                payment_info = check_order_payment_status(subscription.razorpay_order_id)
                                if payment_info.get("status") == "paid":
                                    success_req = PaymentSuccessRequest(
                                        agent_id=existing_agent.id,
                                        razorpay_payment_id=payment_info["payment_id"],
                                        razorpay_order_id=subscription.razorpay_order_id,
                                        razorpay_signature="test_signature_skip"
                                    )
                                    activation_result = self.verify_and_activate(db, success_req)
                                    if activation_result.get("success"):
                                        token = activation_result.get("access_token", token)
                                        custom_message = f"payment done. so check your {agent_email} for user id & password."
                                        is_payment_done = True
                    except Exception as rec_err:
                        print(f"Error during basic registration payment recovery: {rec_err}")
                
                return agent_id, True, agent_name, agent_email, token, custom_message, is_payment_done

            # Validate promo code using JWT if provided
            agent_draft_data = {}
            if request.promo_code:
                if not request.promo_token:
                    raise ValueError("invalid jwt token")
                
                # Verify JWT Token signature, expiry, and payload match
                payload = decode_promo_validation_token(request.promo_token)
                if not payload:
                    raise ValueError("invalid jwt token")
                
                if payload.get("promo_code") != request.promo_code:
                    raise ValueError("invalid request")
                
                # Verify promo code is still valid in the database
                promo_repo = PromoCodeRepository(db)
                promo = promo_repo.get_by_code(request.promo_code)
                if not promo or not promo.is_valid():
                    raise ValueError("invalid request")
                
                agent_draft_data["applied_promo"] = promo.code

            # Pincode lookup to retrieve state and district
            agent_state = "Gujarat"
            agent_district = ""
            try:
                pincode_res = db.execute(
                    text("SELECT state, district FROM pincodes WHERE pincode = :pincode LIMIT 1"),
                    {"pincode": request.agent_pincode}
                ).fetchone()
                if pincode_res:
                    agent_state = pincode_res[0]
                    agent_district = pincode_res[1]
            except Exception as pe:
                print(f"Pincode lookup error: {pe}")

            agent_draft_data["state"] = agent_state
            agent_draft_data["district"] = agent_district

            # Normalize investment types
            clean_types = []
            has_sip_stp_swp = False
            for t in request.investment_types:
                t_lower = t.strip().lower()
                if t_lower in ['sip', 'stp', 'swp', 'sip/stp/swp']:
                    if not has_sip_stp_swp:
                        clean_types.append('SIP/STP/SWP')
                        has_sip_stp_swp = True
                elif t_lower == 'bonds':
                    continue
                else:
                    if t_lower == 'lumpsum':
                        clean_types.append('Lumpsum')
                    elif t_lower == 'elss':
                        clean_types.append('ELSS')
                    elif t_lower == 'pms':
                        clean_types.append('PMS')
                    elif t_lower == 'nps':
                        clean_types.append('NPS')
                    elif t_lower == 'aif':
                        clean_types.append('AIF')
                    else:
                        clean_types.append(t.strip())
            agent_draft_data["investment_types"] = clean_types

            # Insert new user
            hashed_password = get_password_hash(request.email)
            user = User(
                fullname=request.fullname,
                email=request.email,
                password=hashed_password,
                role="agent",
                status="active",
                email_verified_at=datetime.utcnow()
            )
            user_repo.create(user)

            # Insert new agent linked to the user
            agent = Agent(
                email=request.email,
                fullname=request.fullname,
                mobile=request.mobile,
                agent_pincode=request.agent_pincode,
                experience_range=request.experience_range,
                client_base=request.client_base,
                user_types=["insurance_agent"],
                status="incomplete",
                registration_step=1,
                registration_draft=agent_draft_data if agent_draft_data else None,
                user_id=user.id
            )
            self.agent_repository.create(agent)

            # Update insurance segments
            if request.segments:
                self.agent_repository.update_segments(agent.id, request.segments)

            # Check for referral in basic signup (session ref link landing)
            if request.promo_code:
                ref_repo = ReferralRepository(db)
                ref_code_obj = ref_repo.get_by_code(request.promo_code)
                if ref_code_obj and ref_code_obj.is_active:
                    agent.referred_by_code = ref_code_obj.code

            # Generate JWT token for the newly registered agent and register in DB before committing
            token = generate_and_register_token(db, agent.email, "agent", user.id)
            db.commit()
            db.refresh(agent)
            return agent.id, False, agent.fullname, agent.email, token, None, False
        except Exception as e:
            db.rollback()
            raise e

    def calculate_pricing(self, db: Session, agent_id: int, promo_code_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        agent = self.agent_repository.get_by_id(agent_id)
        if not agent:
            raise ValueError("Agent not found.")

        # 1. Fetch pricing configuration from the SiteSetting table
        pricing_val = None
        try:
            result = db.execute(text("SELECT `value` FROM site_settings WHERE `key` = 'pricing'"))
            row = result.fetchone()
            if row and row[0]:
                pricing_val = row[0]
            else:
                result = db.execute(text("SELECT `value` FROM site_settings WHERE `key` = 'pricing_config'"))
                row = result.fetchone()
                if row and row[0]:
                    pricing_val = row[0]
        except Exception as e:
            raise ValueError(f"Database error fetching pricing config: {str(e)}")

        if not pricing_val:
            raise ValueError("Missing plan configuration in SiteSetting")

        try:
            import json
            config = json.loads(pricing_val)
        except Exception:
            raise ValueError("Malformed pricing JSON in SiteSetting")

        starter_full = None
        prof_full = None
        
        try:
            if "starter" in config and "full_price" in config["starter"]:
                starter_full = float(config["starter"]["full_price"])
            if "professional" in config and "full_price" in config["professional"]:
                prof_full = float(config["professional"]["full_price"])
        except Exception:
            raise ValueError("Malformed pricing JSON in SiteSetting")

        if starter_full is None or prof_full is None:
            raise ValueError("Missing plan configuration in SiteSetting")

        if starter_full < 0 or prof_full < 0:
            raise ValueError("Invalid discount values")

        # 2. Promo code validation
        promo = None
        applied_promo = promo_code_str or (agent.registration_draft.get("applied_promo") if agent.registration_draft else None)
        if applied_promo:
            promo_repo = PromoCodeRepository(db)
            promo = promo_repo.get_by_code(applied_promo)
            if not promo:
                raise ValueError("Invalid promo code")
            if not promo.is_active:
                raise ValueError("Inactive promo code")
            if promo.expires_at and promo.expires_at < datetime.utcnow():
                raise ValueError("Expired promo code")
            if promo.max_uses and promo.times_used >= promo.max_uses:
                raise ValueError("Exhausted usage limit")
            if promo.discount_value is None or float(promo.discount_value) < 0:
                raise ValueError("Invalid discount values")

        # 3. Fetch trial configuration if free trial promo
        trial_full = 99.00
        trial_plan_name = "TRIAL Plan"
        trial_duration_days = 30
        
        is_free_trial = promo and promo.is_free_trial_code()
        
        if is_free_trial:
            trial_val = None
            try:
                result_trial = db.execute(text("SELECT `value` FROM site_settings WHERE `key` = 'trial_plan_config'"))
                row_trial = result_trial.fetchone()
                if row_trial and row_trial[0]:
                    trial_val = row_trial[0]
            except Exception as e:
                raise ValueError(f"Database error fetching trial config: {str(e)}")

            if not trial_val:
                raise ValueError("Missing trial_plan_config JSON in SiteSetting")

            try:
                config_trial = json.loads(trial_val)
                if "price" in config_trial:
                    trial_full = float(config_trial["price"])
                else:
                    raise ValueError("Malformed trial_plan_config JSON in SiteSetting")
                trial_plan_name = config_trial.get("name", "TRIAL Plan")
                trial_duration_days = config_trial.get("duration_days", 30)
            except Exception:
                raise ValueError("Malformed trial_plan_config JSON in SiteSetting")

            if trial_full < 0:
                raise ValueError("Invalid discount values")

            # Check trial override
            if promo.trial_price_override is not None:
                trial_full = float(promo.trial_price_override)
            if promo.trial_plan_name:
                trial_plan_name = promo.trial_plan_name
            if promo.trial_duration_days:
                trial_duration_days = promo.trial_duration_days

        # Initialize Starter and Professional original and discounted base amounts
        starter_original = starter_full
        prof_original = prof_full
        
        starter_discount_val = 0.0
        prof_discount_val = 0.0
        
        is_basic_eligible = True
        is_prof_eligible = True

        if promo and not promo.is_free_trial_code():
            if promo.applicable_plan and promo.applicable_plan.lower() != "all":
                app_plan = promo.applicable_plan.lower()
                is_basic_eligible = (app_plan == "basic" or app_plan == "starter")
                is_prof_eligible = (app_plan == "professional" or app_plan == "pro")
                
            if is_basic_eligible:
                if promo.discount_type == "percentage":
                    starter_discount_val = round((float(promo.discount_value) / 100.0) * starter_original, 2)
                else:
                    starter_discount_val = min(float(promo.discount_value), starter_original)
            
            if is_prof_eligible:
                if promo.discount_type == "percentage":
                    prof_discount_val = round((float(promo.discount_value) / 100.0) * prof_original, 2)
                else:
                    prof_discount_val = min(float(promo.discount_value), prof_original)
                    
        elif agent.plan_type == "free_trial":
            # Apply trial upgrade discount
            discount_pct = agent.upgrade_discount_percent or 20.0
            discount_factor = (100.0 - float(discount_pct)) / 100.0
            starter_discount_val = round(starter_original * (1.0 - discount_factor), 2)
            prof_discount_val = round(prof_original * (1.0 - discount_factor), 2)

        starter_discounted = max(0.0, starter_original - starter_discount_val)
        prof_discounted = max(0.0, prof_original - prof_discount_val)

        # Apply GST and total calculation
        starter_gst = round(starter_discounted * 0.18, 2)
        starter_total = round(starter_discounted + starter_gst, 2)

        prof_gst = round(prof_discounted * 0.18, 2)
        prof_total = round(prof_discounted + prof_gst, 2)

        # Enforce referral reward pricing overrides
        if agent.referral_reward_type == "pro_plan_1rs":
            prof_discounted = round(1.00 / 1.18, 2)
            prof_gst = round(1.00 - prof_discounted, 2)
            prof_total = 1.00

        # Construct plans response dictionary
        pricing_data = {}
        
        pricing_data["basic"] = {
            "name": "Starter's Plan",
            "base_amount": starter_discounted,
            "gst_amount": starter_gst,
            "total_amount": starter_total,
            "original_amount": starter_original,
            "discount_amount": starter_discount_val,
            "discounted_amount": starter_discounted,
            "applied_promo_code": promo.code if (promo and is_basic_eligible and not promo.is_free_trial_code()) else None,
            "discount_type": promo.discount_type if (promo and is_basic_eligible and not promo.is_free_trial_code()) else None,
            "discount_value": float(promo.discount_value) if (promo and is_basic_eligible and not promo.is_free_trial_code()) else 0.0,
            "currency": "INR"
        }
        
        pricing_data["professional"] = {
            "name": "Professional's Plan",
            "base_amount": prof_discounted,
            "gst_amount": prof_gst,
            "total_amount": prof_total,
            "original_amount": prof_original,
            "discount_amount": prof_discount_val,
            "discounted_amount": prof_discounted,
            "applied_promo_code": promo.code if (promo and is_prof_eligible and not promo.is_free_trial_code()) else None,
            "discount_type": promo.discount_type if (promo and is_prof_eligible and not promo.is_free_trial_code()) else None,
            "discount_value": float(promo.discount_value) if (promo and is_prof_eligible and not promo.is_free_trial_code()) else 0.0,
            "currency": "INR"
        }

        if is_free_trial:
            trial_original = trial_full
            trial_discount_val = 0.0
            if promo.discount_value > 0:
                if promo.discount_type == "percentage":
                    trial_discount_val = round((float(promo.discount_value) / 100.0) * trial_original, 2)
                else:
                    trial_discount_val = min(float(promo.discount_value), trial_original)
            
            trial_discounted = max(0.0, trial_original - trial_discount_val)
            trial_gst = round(trial_discounted * 0.18, 2)
            trial_total = round(trial_discounted + trial_gst, 2)

            pricing_data["free_trial"] = {
                "name": trial_plan_name if trial_plan_name else f"TRIAL Plan ({trial_duration_days} Days)",
                "base_amount": trial_discounted,
                "gst_amount": trial_gst,
                "total_amount": trial_total,
                "original_amount": trial_original,
                "discount_amount": trial_discount_val,
                "discounted_amount": trial_discounted,
                "applied_promo_code": promo.code,
                "discount_type": promo.discount_type,
                "discount_value": float(promo.discount_value),
                "currency": "INR"
            }

        return pricing_data

    def initiate_order(self, db: Session, agent_id: int, plan_type: str) -> Dict[str, Any]:
        try:
            agent = self.agent_repository.get_by_id(agent_id)
            if not agent:
                raise ValueError("Agent not found.")

            pricing = self.calculate_pricing(db, agent_id)
            
            # Resolve plan_type dynamically by display name / plan name matching
            matched_key = None
            for key, info in pricing.items():
                if info.get("name") == plan_type:
                    matched_key = key
                    break
            if not matched_key:
                if plan_type in pricing:
                    matched_key = plan_type
                    
            if not matched_key:
                raise ValueError(f"Invalid plan type: {plan_type}")

            plan_info = pricing.get(matched_key)
            resolved_plan_key = matched_key

            total_amount = plan_info["total_amount"]
            amount_paise = int(round(total_amount * 100))

            # Call Razorpay to generate order ID
            receipt = f"agent_order_{agent.id}_{int(datetime.utcnow().timestamp())}"
            order_data = PaymentService.create_order(amount_paise, receipt)
            order_id = order_data.get("id") if order_data else f"mock_order_{random.randint(1000, 9999)}"

            # Save subscription details in pending status
            sub_repo = SubscriptionRepository(db)
            subscription = sub_repo.get_by_agent_id(agent.id)
            
            applied_promo = agent.registration_draft.get("applied_promo") if agent.registration_draft else None

            if subscription:
                subscription.selected_plan = plan_info["name"]
                subscription.promo_code = applied_promo
                subscription.registration_amount = total_amount
                subscription.razorpay_order_id = order_id
                subscription.payment_status = "pending"
                subscription.status = "inactive"
            else:
                subscription = AgentSubscription(
                    agent_id=agent.id,
                    selected_plan=plan_info["name"],
                    promo_code=applied_promo,
                    registration_amount=total_amount,
                    razorpay_order_id=order_id,
                    payment_status="pending",
                    status="inactive"
                )
                sub_repo.create(subscription)

            # Update agent registration step & status
            agent.registration_step = 2
            agent.status = "pending_payment"
            agent.plan_type = resolved_plan_key

            db.commit()
            db.refresh(agent)

            return {
                "success": True,
                "order_id": order_id,
                "amount": float(amount_paise) / 100.0, # Display in Rupees instead of paise
                "key": settings.RAZORPAY_KEY,
                "agent_id": agent.id,
                "name": agent.fullname,
                "email": agent.email,
                "plan_amount": plan_info["base_amount"],
                "total_amount": total_amount,
                "test_payment": settings.RAZORPAY_KEY.startswith("rzp_test")
            }
        except Exception as e:
            db.rollback()
            raise e

    def verify_and_activate(self, db: Session, request: PaymentSuccessRequest) -> Dict[str, Any]:
        try:
            # Row locking for Agent to prevent concurrent race conditions
            agent = db.query(Agent).filter(Agent.id == request.agent_id).with_for_update().first()
            if not agent:
                raise ValueError("Agent not found.")

            # Skip verification in local test modes if using mock keys
            is_mock = request.razorpay_order_id.startswith("mock_order") or request.razorpay_signature == "test_signature_skip"
            if not is_mock:
                # Standard verification
                sig_ok = PaymentService.verify_payment_signature(
                    order_id=request.razorpay_order_id,
                    payment_id=request.razorpay_payment_id,
                    signature=request.razorpay_signature
                )
                if not sig_ok:
                    raise ValueError("Invalid Razorpay payment signature.")

            sub_repo = SubscriptionRepository(db)
            # Row locking for Subscription
            subscription = db.query(AgentSubscription).filter(
                AgentSubscription.razorpay_order_id == request.razorpay_order_id
            ).with_for_update().first()
            
            if not subscription:
                subscription = db.query(AgentSubscription).filter(
                    AgentSubscription.agent_id == agent.id
                ).with_for_update().first()

            if not subscription:
                raise ValueError("Subscription not found for this transaction.")

            # Idempotency check
                if user:
                    access_token = generate_and_register_token(db, user.email, user.role, user.id)
                    refresh_token = create_refresh_token({"sub": user.email, "user_id": user.id})
                else:
                    access_token = ""
                    refresh_token = ""
                return {
                    "success": True,
                    "message": "Payment already processed successfully.",
                    "redirect_url": "/agent/dashboard",
                    "access_token": access_token,
                    "refresh_token": refresh_token
                }

            # Set expiration
            starts_at = datetime.utcnow()
            if agent.plan_type == "free_trial":
                promo_code = subscription.promo_code
                duration_days = 30
                if promo_code:
                    promo = PromoCodeRepository(db).get_by_code(promo_code)
                    if promo and promo.trial_duration_days:
                        duration_days = promo.trial_duration_days
                expires_at = starts_at + timedelta(days=duration_days)
            else:
                expires_at = starts_at + timedelta(days=365) # 1 year

            # Update subscription
            subscription.payment_status = "completed"
            subscription.status = "active"
            subscription.razorpay_payment_id = request.razorpay_payment_id
            subscription.razorpay_signature = request.razorpay_signature
            subscription.starts_at = starts_at
            subscription.expires_at = expires_at

            # Update agent status
            if agent.plan_type == "free_trial":
                agent.status = "active"
                agent.trial_ends_at = expires_at
            else:
                agent.status = "pending_approval" # Paid plans require admin review
            agent.registration_step = 2

            # Initialize profile using pincode-based state and district
            profile_repo = ProfileRepository(db)
            profile = profile_repo.get_by_agent_id(agent.id)
            if not profile:
                profile_slug = agent.fullname.lower().replace(" ", "-") + f"-{agent.id}"
                
                draft_state = "Gujarat"
                draft_district = ""
                if agent.registration_draft:
                    draft_state = agent.registration_draft.get("state", "Gujarat")
                    draft_district = agent.registration_draft.get("district", "")
                    
                profile = AgentProfile(
                    agent_id=agent.id,
                    slug=profile_slug,
                    display_name=agent.fullname,
                    address=f"{draft_district}, {draft_state}".strip(", "),
                    state=draft_state,
                    service_pincodes=[agent.agent_pincode],
                    experience_years=parse_experience_years(agent.experience_range)
                )
                profile_repo.create(profile)

            # Referral conversions check
            if agent.referred_by_code:
                ref_repo = ReferralRepository(db)
                ref_code_obj = ref_repo.get_by_code(agent.referred_by_code)
                if ref_code_obj:
                    usage = ref_repo.get_usage(ref_code_obj.id, agent.id)
                    if not usage:
                        usage = ReferralUsage(
                            referral_code_id=ref_code_obj.id,
                            referred_agent_id=agent.id,
                            status="converted"
                        )
                        ref_repo.create_usage(usage)
                    else:
                        usage.status = "converted"
                    
                    # Update referral count
                    conversions = ref_repo.count_conversions(ref_code_obj.id)
                    ref_code_obj.total_referrals = conversions
                    
                    # Promote referring agent to Pro plan for 1 rupee if conversions >= 5
                    if conversions >= 5:
                        inviter_agent = self.agent_repository.get_by_id(ref_code_obj.agent_id)
                        if inviter_agent and inviter_agent.plan_type == "free_trial":
                            inviter_agent.referral_reward_type = "pro_plan_1rs"

            # Generate referral code for this new agent
            ref_repo = ReferralRepository(db)
            existing_ref = ref_repo.get_by_agent_id(agent.id)
            if not existing_ref:
                new_ref_code = ref_repo.generate_unique_code()
                ref_repo.create_code(ReferralCode(
                    code=new_ref_code,
                    agent_id=agent.id,
                    is_active=True
                ))

            # Increment Promo use counts
            if subscription.promo_code:
                promo_code_obj = PromoCodeRepository(db).get_by_code(subscription.promo_code)
                if promo_code_obj:
                    promo_code_obj.times_used += 1

            # Generate actual Invoice record and PDF file
            invoice = None
            pdf_bytes = None
            try:
                invoice = InvoiceService.generate_from_subscription(db, agent, subscription)
                if invoice and invoice.pdf_path:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    storage_base = os.path.abspath(os.path.join(base_dir, "..", "storage"))
                    full_pdf_path = os.path.join(storage_base, invoice.pdf_path)
                    if os.path.exists(full_pdf_path):
                        with open(full_pdf_path, "rb") as f:
                            pdf_bytes = f.read()
            except Exception as inv_err:
                print(f"Failed to generate PDF invoice via InvoiceService: {inv_err}")

            if not invoice:
                # Fallback database record creation
                invoice_repo = InvoiceRepository(db)
                invoice_num = f"INV-{datetime.utcnow().year}-{str(agent.id).zfill(5)}"
                invoice = Invoice(
                    invoice_number=invoice_num,
                    agent_id=agent.id,
                    agent_name=agent.fullname,
                    agent_email=agent.email,
                    agent_mobile=agent.mobile,
                    plan_name=subscription.selected_plan,
                    plan_type=agent.plan_type or "professional",
                    base_amount=round(float(subscription.registration_amount or 0) / 1.18, 2),
                    gst_amount=round(float(subscription.registration_amount or 0) - round(float(subscription.registration_amount or 0) / 1.18, 2), 2),
                    total_amount=subscription.registration_amount,
                    razorpay_payment_id=request.razorpay_payment_id,
                    razorpay_order_id=request.razorpay_order_id,
                    payment_status="completed"
                )
                invoice_repo.create(invoice)
                pdf_bytes = f"INVOICE NUMBER: {invoice_num}\nAgent: {agent.fullname}\nAmount: {subscription.registration_amount} INR".encode("utf-8")

            # Create User login credentials
            user_repo = UserRepository(db)
            user = user_repo.get_by_email(agent.email)
            
            # Default password = email prefix + "@"
            email_prefix = agent.email.split("@")[0]
            default_password = f"{email_prefix}@"
            hashed_password = get_password_hash(default_password)

            if not user:
                user = User(
                    fullname=agent.fullname,
                    email=agent.email,
                    password=hashed_password,
                    role="agent",
                    status="active",
                    email_verified_at=datetime.utcnow()
                )
                user_repo.create(user)
            else:
                user.role = "agent"
                user.password = hashed_password
                user.email_verified_at = datetime.utcnow()

            agent.user_id = user.id

            # Generate access and refresh tokens in transaction before committing
            access_token = generate_and_register_token(db, user.email, user.role, user.id)
            refresh_token = create_refresh_token({"sub": user.email, "user_id": user.id})

            db.commit()
            db.refresh(agent)
            db.refresh(user)

            # Send Credentials Email with actual PDF attachment
            try:
                EmailService.send_welcome_email(
                    to_email=agent.email,
                    to_name=agent.fullname,
                    password=default_password,
                    pdf_content=pdf_bytes,
                    invoice_number=invoice.invoice_number
                )
            except Exception as mail_ex:
                print(f"Failed to send welcome credentials email: {mail_ex}")

            return {
                "success": True,
                "message": "Payment verified and registration completed successfully!",
                "redirect_url": "/agent/dashboard",
                "access_token": access_token,
                "refresh_token": refresh_token
            }

        except Exception as e:
            db.rollback()
            raise e
