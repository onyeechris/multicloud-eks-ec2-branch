from pydantic import BaseModel
from typing import Optional


class AmiInfo(BaseModel):
    image_id: str
    name: str
    description: str
    creation_date: str
    architecture: str
    virtualization_type: str
    state: str
    owner_id: str
    platform: Optional[str] = None
