from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status, Request
from typing import List, Optional, Union, Any, Annotated
from pydantic import BeforeValidator, WithJsonSchema
from sqlalchemy.orm import Session

def validate_upload_or_str(v: Any) -> Any:
    return v

FlexibleUploadFile = Annotated[
    Union[UploadFile, str],
    BeforeValidator(validate_upload_or_str),
    WithJsonSchema({"type": "string", "format": "binary"})
]
from app.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.agent import Agent
from app.schemas.profile import AgentProfileResponse, AgentProfileUpdateRequest
from app.repositories.agent_repository import AgentRepository
from app.services.profile_service import ProfileService
from app.services.cloudinary_service import CloudinaryService
from app.utils.image_validation import validate_image_file
from app.models.agent_profile import AgentProfile
from app.models.agent_achievement_photo import AgentAchievementPhoto
import logging
import hashlib

from app.services.local_storage_service import LocalStorageService
from app.utils.companies import INSURANCE_COMPANIES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["Profile"])

@router.get("/profile", response_model=AgentProfileResponse)
def get_agent_profile(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get the complete agent profile for the authenticated agent.
    This endpoint serves as the single source of truth for the Edit Profile UI.
    """
    agent_repo = AgentRepository(db)
    profile_service = ProfileService(agent_repo)
    
    return profile_service.get_profile(current_agent.id)

@router.put("/profile", response_model=AgentProfileResponse)
def update_agent_profile(
    payload: AgentProfileUpdateRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Update the complete agent profile for the authenticated agent.
    Replaces all editable profile data in a single monolithic transaction.
    """
    agent_repo = AgentRepository(db)
    profile_service = ProfileService(agent_repo)
    
    return profile_service.update_profile(current_agent.id, payload)

@router.post("/profile/image")
async def upload_profile_image(
    request: Request,
    file: UploadFile = File(...),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Upload or update a single profile image for the authenticated agent.
    Uploads to Cloudinary, with local fallback if Cloudinary fails.
    """
    # 1. Read file and compute hash/size
    sha256 = hashlib.sha256()
    file_content = bytearray()
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        sha256.update(chunk)
        file_content.extend(chunk)
    file_bytes = bytes(file_content)
    
    # 2. Validate and sanitize
    file_bytes = validate_image_file(file_bytes, file.filename or "image.jpg", file.content_type or "image/jpeg")
    
    # 3. Get profile
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == current_agent.id).first()
    if not profile:
        profile = AgentProfile(agent_id=current_agent.id)
        db.add(profile)
        db.flush()
        
    old_path = profile.profile_photo_path
    
    # 4. Upload with Fallback
    logger.info(f"Upload started: Profile image for agent_id={current_agent.id}, filename={file.filename}")
    try:
        secure_url = CloudinaryService.upload_image(
            file_bytes,
            folder=f"agent_profiles/{current_agent.id}",
            filename="profile"
        )
        logger.info(f"Cloudinary success: URL={secure_url}")
    except Exception as e:
        logger.warning(f"Cloudinary upload failed ({type(e).__name__}): {str(e)}. Fallback to local storage initiated.")
        try:
            # Use the live request base URL so the returned URL works via ngrok / production domain
            live_base_url = str(request.base_url).rstrip("/")
            secure_url = LocalStorageService.save_file(
                file_bytes,
                subfolder="profile",
                filename=file.filename or "profile.png",
                base_url=live_base_url
            )
            logger.info(f"Local storage success: URL={secure_url}")
        except Exception as local_err:
            logger.error(f"Local storage failure: {str(local_err)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Both Cloudinary and local fallback storage failed."
            )
        
    # 5. Delete old image
    if old_path:
        if "res.cloudinary.com" in old_path:
            try:
                CloudinaryService.delete_image(old_path)
            except Exception as e:
                logger.error(f"Failed to delete old image from Cloudinary: {str(e)}")
        elif "/static/uploads/" in old_path or "/media/uploads/" in old_path:
            try:
                LocalStorageService.delete_file(old_path)
            except Exception as e:
                logger.error(f"Failed to delete old local file: {str(e)}")
            
    # 6. Update DB via service layer
    profile_service = ProfileService(AgentRepository(db))
    return profile_service.update_profile_photo(current_agent.id, secure_url)

@router.post("/profile/achievement")
async def upload_achievement_image(
    request: Request,
    file: Optional[FlexibleUploadFile] = File(None),
    files: Optional[List[FlexibleUploadFile]] = File(None),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Upload one or more achievement images for the authenticated agent.
    Supports up to 10 images. Validates actual file signature (magic bytes)
    and sanitizes image payloads by re-saving.
    """
    # 1. Combine inputs and filter out empty placeholders
    raw_uploaded_files = []
    if file:
        raw_uploaded_files.append(file)
    if files:
        raw_uploaded_files.extend(files)

    uploaded_files = []
    for f in raw_uploaded_files:
        if isinstance(f, str):
            if f.strip() != "":
                uploaded_files.append(f)
        else:
            if f.filename and f.filename.strip() != "":
                uploaded_files.append(f)

    if not uploaded_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files uploaded."
        )

    if len(uploaded_files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot upload more than 10 files in a single request."
        )

    # 2. Process all uploaded files (read, validate/sanitize, compute hash)
    processed_files = []
    batch_hashes = set()
    
    for f in uploaded_files:
        if isinstance(f, str):
            filename = "achievement.jpg"
            content_type = "image/jpeg"
            try:
                raw_bytes = f.encode('latin-1')
            except Exception:
                raw_bytes = f.encode('utf-8')
        else:
            filename = f.filename or "achievement.jpg"
            content_type = f.content_type or "image/jpeg"
            sha256 = hashlib.sha256()
            file_content = bytearray()
            while True:
                chunk = await f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
                file_content.extend(chunk)
            raw_bytes = bytes(file_content)
        
        # Validate, get sanitized bytes, and compute secure hash
        sanitized_bytes = validate_image_file(raw_bytes, filename, content_type)
        sanitized_hash = hashlib.sha256(sanitized_bytes).hexdigest()
        
        # Prevent duplicates within the same batch upload
        if sanitized_hash in batch_hashes:
            continue
        batch_hashes.add(sanitized_hash)
        
        processed_files.append({
            "filename": filename,
            "bytes": sanitized_bytes,
            "hash": sanitized_hash
        })

    # 3. Check photo limits based on subscription plan
    active_sub = next((s for s in current_agent.subscriptions if s.status == 'active'), None)
    plan_text = str(active_sub.selected_plan if active_sub else '').lower()
    max_photos = 10 if 'professional' in plan_text else 5
    
    current_count = db.query(AgentAchievementPhoto).filter(
        AgentAchievementPhoto.agent_id == current_agent.id
    ).count()

    # Identify which files are new (not already in the database for this agent)
    new_processed_files = []
    existing_photos_map = {}
    
    for pf in processed_files:
        existing = db.query(AgentAchievementPhoto).filter(
            AgentAchievementPhoto.agent_id == current_agent.id,
            AgentAchievementPhoto.file_hash == pf["hash"]
        ).first()
        
        if existing:
            existing_photos_map[pf["hash"]] = existing
        else:
            new_processed_files.append(pf)

    # Enforce plan limits
    if current_count + len(new_processed_files) > max_photos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Achievement photo limit exceeded. Your current plan allows up to {max_photos} photos."
        )

    # 4. Upload and Save new files
    uploaded_results = []
    
    for pf in processed_files:
        if pf["hash"] in existing_photos_map:
            # Re-use existing photo record
            existing = existing_photos_map[pf["hash"]]
            uploaded_results.append({
                "id": existing.id,
                "photo_url": existing.photo_path
            })
            continue

        # Upload with Fallback
        logger.info(f"Upload started: Achievement photo for agent_id={current_agent.id}, filename={pf['filename']}")
        try:
            secure_url = CloudinaryService.upload_image(
                pf["bytes"],
                folder=f"agent_achievements/{current_agent.id}",
                filename=pf["hash"]
            )
            logger.info(f"Cloudinary success: URL={secure_url}")
        except Exception as e:
            logger.warning(f"Cloudinary upload failed ({type(e).__name__}): {str(e)}. Fallback to local storage initiated.")
            try:
                # Use the live request base URL so the returned URL works via ngrok / production domain
                live_base_url = str(request.base_url).rstrip("/")
                secure_url = LocalStorageService.save_file(
                    pf["bytes"],
                    subfolder="achievements",
                    filename=pf["filename"] or f"{pf['hash']}.png",
                    base_url=live_base_url
                )
                logger.info(f"Local storage success: URL={secure_url}")
            except Exception as local_err:
                logger.error(f"Local storage failure: {str(local_err)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Both Cloudinary and local fallback storage failed."
                )

        # Store the uploaded photo URL
        pf["photo_url"] = secure_url

    # Save to DB via service layer
    profile_service = ProfileService(AgentRepository(db))
    uploaded_results = profile_service.save_achievement_photos(
        agent_id=current_agent.id,
        processed_files=processed_files,
        existing_photos_map=existing_photos_map
    )

    # Construct backward-compatible response
    first_photo = uploaded_results[0] if uploaded_results else None
    return {
        "success": True,
        "photo": first_photo,
        "photos": uploaded_results
    }

@router.get("/profile/companies")
def get_companies(current_agent: Agent = Depends(get_current_agent), db: Session = Depends(get_db)):
    """
    Get the list of insurance companies grouped by segment (health, life, motor, sme).
    Locked using authentication token for the agent.
    Fetched from the database table (seeded with initial list if empty).
    """
    from app.models.insurance_company import InsuranceCompany
    import re
    
    # Check if table is empty
    count = db.query(InsuranceCompany).count()
    if count == 0:
        # Seed the table from existing list
        def slugify(text):
            text = text.lower()
            text = re.sub(r'[^a-z0-9\s-]', '', text)
            text = re.sub(r'[\s-]+', '-', text)
            return text.strip('-')
            
        inserted_slugs = set()
        for segment_type, company_names in INSURANCE_COMPANIES.items():
            for name in company_names:
                slug = slugify(name)
                # Check for slug duplicates within current seed
                if slug in inserted_slugs:
                    slug = f"{slug}-1"
                inserted_slugs.add(slug)
                db.add(InsuranceCompany(name=name, slug=slug))
        db.commit()
    
    # Query all companies from db
    companies = db.query(InsuranceCompany).all()
    
    # Group by segment
    grouped_companies = {
        "health": [],
        "life": [],
        "motor": [],
        "sme": []
    }
    
    # Fast lookup sets for static lists
    lookup = {
        seg: {name.lower().strip() for name in names}
        for seg, names in INSURANCE_COMPANIES.items()
    }
    
    for company in companies:
        c_name_lower = company.name.lower().strip()
        matched = False
        
        # Match against static mappings
        for seg, name_set in lookup.items():
            if c_name_lower in name_set:
                grouped_companies[seg].append(company.name)
                matched = True
        
        # Fallback if company is not in the predefined static lists
        if not matched:
            if "life" in c_name_lower:
                grouped_companies["life"].append(company.name)
            elif "health" in c_name_lower:
                grouped_companies["health"].append(company.name)
            else:
                grouped_companies["motor"].append(company.name)
                grouped_companies["sme"].append(company.name)
                
    # Deduplicate and sort in alphabetical order
    for seg in grouped_companies:
        grouped_companies[seg] = sorted(list(set(grouped_companies[seg])))
        
    return grouped_companies


