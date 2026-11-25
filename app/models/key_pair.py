from pydantic import BaseModel, Field
from typing import Dict, Optional


class KeyPairRequest(BaseModel):
    stack: str = Field(..., description="Pulumi stack name")
    region: Optional[str] = Field(None, description="AWS region — omit to use the pre-selected region")
    name: str = Field(..., description="EC2 key pair name")
    tags: Dict[str, str] = {}


# class KeyPairPatchRequest(BaseModel):
#     stack: Optional[str] = None
#     region: Optional[str] = None
#     name: Optional[str] = None
#     tags: Optional[Dict[str, str]] = None
