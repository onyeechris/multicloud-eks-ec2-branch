from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class IngressRule(BaseModel):
    protocol: str = Field(..., description="IP protocol, e.g. 'tcp', 'udp', '-1'")
    from_port: int
    to_port: int
    cidr_blocks: List[str]
    description: Optional[str] = None


class EgressRule(BaseModel):
    protocol: str = Field(..., description="IP protocol, e.g. 'tcp', 'udp', '-1'")
    from_port: int
    to_port: int
    cidr_blocks: List[str]
    description: Optional[str] = None


class SecurityGroupRequest(BaseModel):
    stack: str = Field(..., description="Pulumi stack name")
    region: Optional[str] = Field(None, description="AWS region — omit to use the pre-selected region")
    name: str = Field(..., description="Security group name")
    vpc_stack: str = Field(..., description="Pulumi stack name that exported vpc_id")
    description: Optional[str] = None
    ingress: List[IngressRule] = []
    egress: List[EgressRule] = []
    tags: Dict[str, str] = {}


class SecurityGroupPatchRequest(BaseModel):
    stack: Optional[str] = None
    region: Optional[str] = None
    name: Optional[str] = None
    vpc_stack: Optional[str] = None
    description: Optional[str] = None
    ingress: Optional[List[IngressRule]] = None
    egress: Optional[List[EgressRule]] = None
    tags: Optional[Dict[str, str]] = None
