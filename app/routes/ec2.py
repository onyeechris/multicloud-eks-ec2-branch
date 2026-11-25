from typing import List

from fastapi import APIRouter, HTTPException

from app.models.common import StackResponse
from app.models.ec2 import Ec2Request, Ec2PatchRequest
from app.pulumi_programs.ec2 import create_ec2_program
from app.utils.region_state import get_region
from app.utils.stack import (
    stack_up_safe, stack_outputs, stack_destroy,
    stack_list, stack_region, stack_exists,
)

router = APIRouter(prefix="/ec2", tags=["EC2"])


# def _resolve_subnet_id(subnet_stack: str) -> str:
#     try:
#         ids = stack_outputs(subnet_stack)["subnet_ids"]
#         return ids[0] if isinstance(ids, list) else ids
#     except KeyError:
#         raise HTTPException(status_code=404, detail=f"subnet_ids not found in stack '{subnet_stack}'")
#     except Exception as exc:
#         raise HTTPException(status_code=404, detail=f"Could not resolve subnet stack '{subnet_stack}': {exc}")


def _resolve_sg_id(sg_stack: str) -> str:
    try:
        return stack_outputs(sg_stack)["security_group_id"]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"security_group_id not found in stack '{sg_stack}'")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not resolve security group stack '{sg_stack}': {exc}")


def _resolve_key_name(kp_stack: str) -> str:
    try:
        return stack_outputs(kp_stack)["key_name"]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"key_name not found in stack '{kp_stack}'")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not resolve key pair stack '{kp_stack}': {exc}")


@router.get("", response_model=List[StackResponse])
def list_ec2():
    """List all EC2 instance stacks."""
    try:
        all_stacks = stack_list()
        region_h = get_region()
        vipe = [stack for stack in all_stacks if "instance_id" in stack["outputs"] and stack["outputs"].get("ec2_region")==region_h]
        return [
            StackResponse(status="ok", stack=s["name"], outputs=s["outputs"])
            for s in vipe
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("", response_model=StackResponse, status_code=201)
def create_ec2(req: Ec2Request):
    """Create a new EC2 instance stack."""
    if stack_exists(req.stack):
        raise HTTPException(status_code=409, detail=f"EC2 stack '{req.stack}' already exists")
    region = req.region or get_region()
    if not region:
        raise HTTPException(status_code=422, detail="No region provided and no active region selected.")
    try:
        # subnet_id = _resolve_subnet_id(req.subnet_stack)
        sg_id = _resolve_sg_id(req.security_group_stack)
        key_name = _resolve_key_name(req.key_pair_stack) if req.key_pair_stack else None
        program = create_ec2_program(
            name=req.name,
            ami=req.ami,
            instance_type=req.instance_type,
            subnet_id=req.subnet_id,
            region=region,
            security_group_id=sg_id,
            key_name=key_name,
            associate_public_ip=req.associate_public_ip,
            user_data=req.user_data,
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

@router.get("/{stack_name}", response_model=StackResponse)
def get_ec2(stack_name: str):
    """Fetch outputs of an existing EC2 instance stack."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        outputs = stack_outputs(stack_name)
        return StackResponse(status="ok", stack=stack_name, outputs=outputs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# @router.put("/{stack_name}", response_model=StackResponse)
# def update_ec2(stack_name: str, req: Ec2Request):
#     """Fully update an existing EC2 instance stack."""
#     if req.stack != stack_name:
#         raise HTTPException(status_code=400, detail="YOU CAN NOT CHANGE STACK NAME")
#     if not stack_exists(stack_name):
#         raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
#     region = req.region or get_region()
#     if not region:
#         raise HTTPException(status_code=422, detail="No region provided and no active region selected. Call POST /region/{region} first.")
#     try:
#         subnet_id = _resolve_subnet_id(req.subnet_stack)
#         sg_id = _resolve_sg_id(req.security_group_stack)
#         key_name = _resolve_key_name(req.key_pair_stack) if req.key_pair_stack else None
#         program = create_ec2_program(
#             name=req.name,
#             ami=req.ami,
#             instance_type=req.instance_type,
#             subnet_id=subnet_id,
#             region=region,
#             security_group_id=sg_id,
#             key_name=key_name,
#             associate_public_ip=req.associate_public_ip,
#             user_data=req.user_data,
#             tags=req.tags,
#         )
#         outputs = stack_up_safe(stack_name, region, program)
#         return StackResponse(status="updated", stack=stack_name, outputs=outputs)
#     except Exception as exc:
#         raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/{stack_name}", response_model=StackResponse)
def patch_ec2(stack_name: str, req: Ec2PatchRequest):
    """Partially update an EC2 stack — only send the fields you want to change.

    Networking fields (subnet_stack, security_group_stack, key_pair_stack) fall back
    to the IDs stored in the previous deploy outputs when omitted.
    """
    if req.stack is not None and req.stack != stack_name:
        raise HTTPException(status_code=400, detail="YOU CAN NOT CHANGE STACK NAME")
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        current = stack_outputs(stack_name)
        region = req.region or get_region() or current.get("ec2_region")            #or stack_region(stack_name)

        name = req.name if req.name is not None else current.get("name", stack_name)
        ami = req.ami if req.ami is not None else current.get("ami")
        instance_type = req.instance_type if req.instance_type is not None else current.get("instance_type")

        # Prefer fresh stack-reference resolution; fall back to stored IDs from last deploy.
        subnet_id = req.subnet_stack if req.subnet_id else current.get("subnet_id")
        sg_id = _resolve_sg_id(req.security_group_stack) if req.security_group_stack else current.get("security_group_id")
        key_name = _resolve_key_name(req.key_pair_stack) if req.key_pair_stack else (current.get("key_name") or None)

        associate_public_ip = req.associate_public_ip if req.associate_public_ip is not None else current.get("associate_public_ip", False)
        user_data = req.user_data if req.user_data is not None else (current.get("user_data") or None)
        tags = req.tags if req.tags is not None else {}

        missing = [f for f, v in [("ami", ami), ("instance_type", instance_type), ("subnet_id", subnet_id), ("security_group_id", sg_id)] if not v]
        if missing:
            raise HTTPException(status_code=422, detail=f"Could not resolve required fields from request or stack outputs: {missing}")

        program = create_ec2_program(
            name=name,
            ami=ami,
            instance_type=instance_type,
            subnet_id=subnet_id,
            region=region,
            security_group_id=sg_id,
            key_name=key_name,
            associate_public_ip=associate_public_ip,
            user_data=user_data,
            tags=tags,
        )
        outputs = stack_up_safe(stack_name, region, program)
        return StackResponse(status="updated", stack=stack_name, outputs=outputs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{stack_name}")
def delete_ec2(stack_name: str):
    """Destroy the EC2 instance stack."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        stack_destroy(stack_name)
        return {"status": "deleted", "stack": stack_name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
