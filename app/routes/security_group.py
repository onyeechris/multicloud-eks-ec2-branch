from typing import List

from fastapi import APIRouter, HTTPException

from app.models.common import StackResponse
from app.models.security_group import SecurityGroupRequest, SecurityGroupPatchRequest, IngressRule, EgressRule
from app.pulumi_programs.security_group import create_security_group_program
from app.utils.region_state import get_region
from app.utils.stack import (
    stack_up_safe, stack_outputs, stack_destroy,
    stack_list, stack_region, stack_exists,
)

router = APIRouter(prefix="/security-group", tags=["Security Group"])


def _resolve_vpc_id(vpc_stack: str) -> str:
    try:
        return stack_outputs(vpc_stack)["vpc_id"]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"vpc_id not found in stack '{vpc_stack}'")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not resolve vpc stack '{vpc_stack}': {exc}")


@router.post("", response_model=StackResponse, status_code=201)
def create_security_group(req: SecurityGroupRequest):
    """Create a new security group stack."""
    if stack_exists(req.stack):
        raise HTTPException(status_code=409, detail=f"Security group stack '{req.stack}' already exists")
    region = req.region or get_region()
    if not region:
        raise HTTPException(status_code=422, detail="No region provided and no active region selected. Call POST /region/{region} first.")
    try:
        vpc_id = _resolve_vpc_id(req.vpc_stack)
        program = create_security_group_program(
            name=req.name,
            vpc_id=vpc_id,
            region=region,
            description=req.description,
            ingress=req.ingress,
            egress=req.egress,
            tags=req.tags,
        )
        outputs = stack_up_safe(req.stack, region, program)
        return StackResponse(status="created", stack=req.stack, outputs=outputs)
    except Exception as exc:
        if stack_exists(req.stack):
            try:
                stack_destroy(req.stack)
            except Exception as exc2:
                raise HTTPException(
                    status_code=500,
                    detail=f"Original error: {exc}. Also failed to cleanup: {exc2}. Manually check stack {req.stack}"
                )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("", response_model=List[StackResponse])
def list_security_groups():
    """List all security group stacks."""
    try:
        all_stacks = stack_list()
        region_h = get_region()
        vipes = [stack for stack in all_stacks if "security_group_id" in stack["outputs"] and stack["outputs"].get("sg_region") == region_h]
        return [
            StackResponse(status="ok", stack=s["name"], outputs=s["outputs"])
            for s in vipes
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{stack_name}", response_model=StackResponse)
def get_security_group(stack_name: str):
    """Fetch outputs of an existing security group stack."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        outputs = stack_outputs(stack_name)
        return StackResponse(status="ok", stack=stack_name, outputs=outputs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# @router.put("/{stack_name}", response_model=StackResponse)
# def update_security_group(stack_name: str, req: SecurityGroupRequest):
#     """Fully update an existing security group stack."""
#     if req.stack != stack_name:
#         raise HTTPException(status_code=400, detail="YOU CAN NOT CHANGE STACK NAME")
#     if not stack_exists(stack_name):
#         raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
#     region = req.region or get_region()
#     if not region:
#         raise HTTPException(status_code=422, detail="No region provided and no active region selected. Call POST /region/{region} first.")
#     try:
#         vpc_id = _resolve_vpc_id(req.vpc_stack)
#         program = create_security_group_program(
#             name=req.name,
#             vpc_id=vpc_id,
#             region=region,
#             description=req.description,
#             ingress=req.ingress,
#             egress=req.egress,
#             tags=req.tags,
#         )
#         outputs = stack_up_safe(stack_name, region, program)
#         return StackResponse(status="updated", stack=stack_name, outputs=outputs)
#     except Exception as exc:
#         raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/{stack_name}", response_model=StackResponse)
def patch_security_group(stack_name: str, req: SecurityGroupPatchRequest):
    """Partially update a security group stack — only send the fields you want to change."""
    if req.stack is not None and req.stack != stack_name:
        raise HTTPException(status_code=400, detail="YOU CAN NOT CHANGE STACK NAME")
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        current = stack_outputs(stack_name)
        region = req.region or current.get("sg_region") or get_region()  #or stack_region(stack_name)

        name = req.name if req.name is not None else current.get("security_group_name", stack_name)
        description = req.description if req.description is not None else current.get("description")
        tags = req.tags if req.tags is not None else {}

        # Prefer fresh VPC stack resolution; fall back to the stored vpc_id from last deploy.
        vpc_id = _resolve_vpc_id(req.vpc_stack) if req.vpc_stack else current.get("vpc_id")
        if not vpc_id:
            raise HTTPException(status_code=422, detail="'vpc_id' could not be resolved from request or stack outputs")

        # Reconstruct rule objects from stored output dicts when not supplied in the request.
        ingress = req.ingress if req.ingress is not None else [IngressRule(**r) for r in current.get("ingress", [])]
        egress = req.egress if req.egress is not None else [EgressRule(**r) for r in current.get("egress", [])]

        program = create_security_group_program(
            name=name,
            vpc_id=vpc_id,
            region=region,
            description=description,
            ingress=ingress,
            egress=egress,
            tags=tags,
        )
        outputs = stack_up_safe(stack_name, region, program)
        return StackResponse(status="updated", stack=stack_name, outputs=outputs)
    # except HTTPException:
    #     raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{stack_name}")
def delete_security_group(stack_name: str):
    """Destroy the security group stack."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        stack_destroy(stack_name)
        return {"status": "deleted", "stack": stack_name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
