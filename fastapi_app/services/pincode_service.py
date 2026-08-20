import httpx
from fastapi import HTTPException, status
from fastapi_app.schemas.pincode import PincodeResponse

class PincodeService:
    @staticmethod
    def validate_and_fetch_pincode(pincode: str) -> PincodeResponse:
        # Validate 6-digit numeric Indian pincode
        if len(pincode) != 6 or not pincode.isdigit():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Pincode must be exactly 6 digits."
            )
            
        url = f"https://api.postalpincode.in/pincode/{pincode}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url, headers=headers)
                
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Upstream postal service returned an error."
                )
                
            data = response.json()
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Upstream postal service timed out or is unavailable."
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse postal API response."
            )
            
        if not isinstance(data, list) or len(data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pincode not found."
            )
            
        result = data[0]
        if result.get("Status") != "Success":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pincode not found."
            )
            
        post_offices = result.get("PostOffice")
        if not post_offices or not isinstance(post_offices, list) or len(post_offices) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pincode not found."
            )
            
        # Extract city_name (District) from first post office
        city_name = post_offices[0].get("District")
        if not city_name:
            city_name = "Gujarat"
            
        return PincodeResponse(
            pincode=pincode,
            city_name=city_name,
            postal_data=post_offices
        )
