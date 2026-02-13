from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from jose import jwt, JWTError
import os
import logging

# Configuration
PUBLIC_KEY_PATH = "public_key.pem"
ALGORITHM = "RS256"

logger = logging.getLogger(__name__)

class LicenseSchema(BaseModel):
    customer: str
    expiration: datetime
    max_devices: int
    features: List[str]
    is_valid: bool
    status: str

class LicenseVerifier:
    def __init__(self):
        self.public_key = self._load_public_key()
        self.cached_license: Optional[LicenseSchema] = None

    def _load_public_key(self):
        """Load public key from file"""
        if not os.path.exists(PUBLIC_KEY_PATH):
            logger.warning("Public key not found. License verification disabled (Dev Mode).")
            return None
            
        with open(PUBLIC_KEY_PATH, "rb") as f:
            return f.read()

    def verify_license(self, token: str) -> LicenseSchema:
        """Verify JWT signature and claims"""
        if not self.public_key:
            return self._create_dev_license()

        try:
            # Decode & Verify Signature
            payload = jwt.decode(token, self.public_key, algorithms=[ALGORITHM])
            
            # Check Expiration
            exp = datetime.fromtimestamp(payload["exp"])
            if exp < datetime.utcnow():
                return self._create_invalid_license("Expired", payload)

            return LicenseSchema(
                customer=payload["sub"],
                expiration=exp,
                max_devices=payload["limits"]["devices"],
                features=payload["features"],
                is_valid=True,
                status="Active"
            )

        except JWTError as e:
            return self._create_invalid_license(f"Invalid Signature: {str(e)}")
        except Exception as e:
            return self._create_invalid_license(f"Error: {str(e)}")

    def _create_invalid_license(self, status: str, payload: dict = None) -> LicenseSchema:
        return LicenseSchema(
            customer=payload.get("sub", "Unknown") if payload else "Unknown",
            expiration=datetime.utcnow(),
            max_devices=0,
            features=[],
            is_valid=False,
            status=status
        )

    def _create_dev_license(self) -> LicenseSchema:
        """Fallback for when no public key exists (Development)"""
        return LicenseSchema(
            customer="Developer",
            expiration=datetime(2099, 12, 31),
            max_devices=999,
            features=["all"],
            is_valid=True,
            status="Developer Mode"
        )

license_verifier = LicenseVerifier()
