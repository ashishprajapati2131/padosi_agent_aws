from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/v1/email", tags=["Email Service"])

class TestEmailRequest(BaseModel):
    to_email: EmailStr = "ashisprajapati2131@gmail.com"
    subject: str = "FastAPI Email Service Test"
    to_name: Optional[str] = "Ashis Prajapati"

@router.post("/test-send", status_code=status.HTTP_200_OK)
async def send_test_email(request: TestEmailRequest):
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; background-color: #f8fafc; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h2 style="color: #273c8e; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-top: 0;">FastAPI Email Service Status</h2>
            <p>Hello <strong>{request.to_name}</strong>,</p>
            <p>This is a verification email from the newly implemented FastAPI Email Sending Service.</p>
            
            <div style="background-color: #f0fdf4; color: #166534; padding: 15px; border-radius: 6px; border: 1px solid #bbf7d0; margin: 20px 0; font-weight: bold;">
                ✓ The SMTP Email Sending Service is configured and functioning successfully!
            </div>
            
            <p>All SMTP server connection tests, authentication checks, and formatting workflows completed successfully. Emails are transmitted asynchronously to optimize API performance.</p>
            
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0;" />
            <p style="font-size: 12px; color: #64748b; margin-bottom: 0;">This email was sent automatically as part of a service verification test. Please do not reply to this message.</p>
        </div>
    </body>
    </html>
    """
    
    result = await EmailService.send_smtp_email(
        to_email=request.to_email,
        subject=request.subject,
        html_content=html_body,
        to_name=request.to_name
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
        
    return result
