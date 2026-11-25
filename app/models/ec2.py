from pydantic import BaseModel, Field
from typing import Dict, Optional


class Ec2Request(BaseModel):
    stack: str = Field(..., description="Pulumi stack name")
    region: Optional[str] = Field(None, description="AWS region — omit to use the pre-selected region")
    name: str = Field(..., description="Instance name tag")
    ami: str = Field(..., description="AMI ID")
    instance_type: str = Field(..., description="EC2 instance type, e.g. t3.micro")
    subnet_id: str = Field(..., description="subnet_ids")
    security_group_stack: str = Field(..., description="Pulumi stack name that exported security_group_id")
    key_pair_stack: Optional[str] = Field(None, description="Pulumi stack name that exported key_name")
    associate_public_ip: bool = False
    user_data: Optional[str] = None
    tags: Dict[str, str] = {}


class Ec2PatchRequest(BaseModel):
    stack: Optional[str] = None
    region: Optional[str] = None
    name: Optional[str] = None
    ami: Optional[str] = None
    instance_type: Optional[str] = None
    subnet_id: Optional[str] = None
    security_group_stack: Optional[str] = None
    key_pair_stack: Optional[str] = None
    associate_public_ip: Optional[bool] = None
    user_data: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
