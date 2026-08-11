from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.database import get_db
from app.utils.auth import decode_token
from app.schemas.registration import (
    RegistrationBasicRequest, 
    RegistrationBasicResponse,
    PricingResponse,
    OrderRequest,
    OrderResponse,
    PaymentSuccessRequest,
    PaymentSuccessResponse,
    PricingRequest
)
from app.repositories.agent_repository import AgentRepository
from app.repositories.user_repository import UserRepository
from app.services.registration_service import RegistrationService
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/v1/agents/registration", tags=["Agent Registration"])
security = HTTPBearer(auto_error=False)

def get_agent_repository(db: Session = Depends(get_db)) -> AgentRepository:
    return AgentRepository(db)

def get_registration_service(agent_repo: AgentRepository = Depends(get_agent_repository)) -> RegistrationService:
    return RegistrationService(agent_repo)

@router.post("/basic", response_model=RegistrationBasicResponse, status_code=status.HTTP_200_OK)
def save_basic_registration_endpoint(
    request: RegistrationBasicRequest, 
    db: Session = Depends(get_db),
    registration_service: RegistrationService = Depends(get_registration_service)
):
    try:
        agent_id, already_registered, name, email, token, custom_message, is_payment_done = registration_service.save_basic_registration(db, request)
        if already_registered:
            msg = custom_message if custom_message else f"Agent already registered with {email}"
            return RegistrationBasicResponse(
                success=True,
                agent_id=agent_id,
                message=msg,
                name=name,
                email=email,
                token=token,
                jwt_token=token,
                is_payment_done=is_payment_done
            )
        return RegistrationBasicResponse(
            success=True,
            agent_id=agent_id,
            message="Basic registration details saved successfully.",
            name=name,
            email=email,
            token=token,
            jwt_token=token,
            is_payment_done=is_payment_done
        )
    except ValueError as val_err:
        msg = str(val_err)
        if msg in ["invalid jwt token", "invalid request"]:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": msg
                }
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving registration: {str(e)}"
        )

@router.get("/pricing", response_model=PricingResponse, status_code=status.HTTP_200_OK)
def get_pricing_endpoint(
    agent_id: int,
    promo_code: Optional[str] = None,
    db: Session = Depends(get_db),
    registration_service: RegistrationService = Depends(get_registration_service)
):
    try:
        plans = registration_service.calculate_pricing(db, agent_id, promo_code)
        return PricingResponse(
            success=True,
            plans=plans,
            applied_promo=promo_code
        )
    except ValueError as val_err:
        msg = str(val_err)
        if msg == "Agent not found.":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating pricing: {str(e)}"
        )

@router.post("/pricing", response_model=PricingResponse, status_code=status.HTTP_200_OK)
def post_pricing_endpoint(
    request: PricingRequest,
    req: Request,
    db: Session = Depends(get_db),
    registration_service: RegistrationService = Depends(get_registration_service),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    try:
        # 1. Read and validate Authorization header existence
        auth_header = req.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != "Bearer":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )
            
        token = parts[1]
        if not token:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )

        # 2. Validate JWT token validity
        payload = decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # 3. Extract email and fetch user & agent
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user_repo = UserRepository(db)
        agent_repo = AgentRepository(db)
        user = user_repo.get_by_email(email)
        agent = agent_repo.get_by_email(email)
        
        if not user or not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found."
            )

        # 4. Cross-validate provided agent_id
        if agent.id != request.agent_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "message": "Unauthorized access. Agent ID does not match the authenticated user."
                }
            )

        plans = registration_service.calculate_pricing(db, request.agent_id)
        # Find if agent registered with promo code to return in applied_promo
        applied_promo = None
        if agent.registration_draft:
            applied_promo = agent.registration_draft.get("applied_promo")
            
        from datetime import timedelta
        from app.utils.auth import create_access_token
        new_token = create_access_token({"sub": agent.email, "role": "agent"}, expires_delta=timedelta(minutes=5))
        return PricingResponse(
            success=True,
            plans=plans,
            applied_promo=applied_promo,
            jwt_token=new_token
        )
    except ValueError as val_err:
        msg = str(val_err)
        if msg == "Agent not found.":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating pricing: {str(e)}"
        )

@router.post("/payment-order", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def create_payment_order_endpoint(
    request: OrderRequest,
    req: Request,
    db: Session = Depends(get_db),
    registration_service: RegistrationService = Depends(get_registration_service),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    try:
        # 1. Read and validate Authorization header existence
        auth_header = req.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != "Bearer":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )
            
        token = parts[1]
        if not token:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )

        # 2. Validate JWT token validity
        payload = decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # 3. Extract email and fetch user & agent
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user_repo = UserRepository(db)
        agent_repo = AgentRepository(db)
        user = user_repo.get_by_email(email)
        agent = agent_repo.get_by_email(email)
        
        if not user or not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found."
            )

        # 4. Cross-validate provided agent_id
        if agent.id != request.agent_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "message": "Unauthorized access. Agent ID does not match the authenticated user."
                }
            )

        # 5. Initiate Order using authenticated agent context
        checkout_data = registration_service.initiate_order(db, agent.id, request.plan_type)
        
        # 6. Generate fresh token with 16-minute expiry
        from datetime import timedelta
        from app.utils.auth import create_access_token
        new_token = create_access_token({"sub": agent.email, "role": "agent"}, expires_delta=timedelta(minutes=16))
        
        checkout_data["jwt_token"] = new_token
        return OrderResponse(**checkout_data)

    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating order: {str(e)}"
        )

@router.post("/payment/success", response_model=PaymentSuccessResponse, status_code=status.HTTP_200_OK)
def verify_payment_endpoint(
    request: PaymentSuccessRequest,
    req: Request,
    db: Session = Depends(get_db),
    registration_service: RegistrationService = Depends(get_registration_service),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    try:
        # 1. Read and validate Authorization header existence
        auth_header = req.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != "Bearer":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )
            
        token = parts[1]
        if not token:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Bad Request"
                }
            )

        # 2. Validate JWT token validity
        payload = decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # 3. Extract email and fetch user & agent
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user_repo = UserRepository(db)
        agent_repo = AgentRepository(db)
        user = user_repo.get_by_email(email)
        agent = agent_repo.get_by_email(email)
        
        if not user or not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found."
            )

        # 4. Cross-validate provided agent_id
        if agent.id != request.agent_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "message": "Unauthorized access. Agent ID does not match the authenticated user."
                }
            )

        # 5. Execute verification using authenticated agent context
        activation_result = registration_service.verify_and_activate(db, request)
        return PaymentSuccessResponse(**activation_result)

    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing payment: {str(e)}"
        )

@router.post("/payment/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    registration_service: RegistrationService = Depends(get_registration_service)
):
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    from app.middleware.api_logger import log_request_to_db

    client_host = request.client.host if request.client else None
    payload_text = payload.decode("utf-8", errors="replace")[:100000]

    try:
        # Verify webhook signature
        sig_ok = PaymentService.verify_webhook_signature(payload, signature)
        if not sig_ok:
            await log_request_to_db("razorpay", str(request.url), "POST", payload_text, 400, client_host)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

        event_data = json.loads(payload_text)
        event = event_data.get("event")
        if event in ["order.paid", "payment.captured"]:
            # Extract payment context
            payment_entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = payment_entity.get("order_id")
            payment_id = payment_entity.get("id")
            
            if order_id and payment_id:
                from app.repositories.subscription_repository import SubscriptionRepository
                sub_repo = SubscriptionRepository(db)
                sub = sub_repo.get_by_order_id(order_id)
                if sub:
                    success_req = PaymentSuccessRequest(
                        agent_id=sub.agent_id,
                        razorpay_payment_id=payment_id,
                        razorpay_order_id=order_id,
                        razorpay_signature="test_signature_skip" # Webhook signature is already verified above
                    )
                    registration_service.verify_and_activate(db, success_req)

        await log_request_to_db("razorpay", str(request.url), "POST", payload_text, 200, client_host)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        await log_request_to_db("razorpay", str(request.url), "POST", payload_text, 500, client_host)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing error: {str(e)}"
        )
