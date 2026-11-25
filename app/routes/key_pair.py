import io
import boto3
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.common import StackResponse
from app.models.key_pair import KeyPairRequest
from app.pulumi_programs.key_pair import create_key_pair_program
from app.utils.region_state import get_region
from app.utils.stack import (
    stack_up_safe, stack_outputs, stack_destroy,
    stack_list, stack_region, stack_exists,
)

router = APIRouter(prefix="/key-pair", tags=["Key Pair"])


@router.post("", response_model=StackResponse, status_code=201)
def create_key_pair(req: KeyPairRequest):
    """Create a new EC2 key pair and store the private key in AWS Secrets Manager."""
    if stack_exists(req.stack):
        raise HTTPException(status_code=409, detail=f"Key pair stack '{req.stack}' already exists")
    region = req.region or get_region()
    if not region:
        raise HTTPException(status_code=422, detail="No region provided and no active region selected. Call POST /region/{region} first.")
    try:
        program = create_key_pair_program(name=req.name, region=region, tags=req.tags)
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
def list_key_pairs():
    """List all key pair stacks."""
    try:
        all_stacks = stack_list()
        region_h = get_region()
        vipe = [stack for stack in all_stacks if "key_name" in stack["outputs"] and stack["outputs"].get("key_region") == region_h]
        return [
            StackResponse(status="ok", stack=s["name"], outputs=s["outputs"])
            for s in vipe
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{stack_name}/download")
def download_key_pair(stack_name: str):
    """Download the private key PEM file from AWS Secrets Manager."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")

    try:
        outputs = stack_outputs(stack_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    secret_id = outputs.get("private_key_secret_name") or outputs.get("private_key_secret_arn")
    if not secret_id:
        raise HTTPException(status_code=404, detail="No private key secret found in stack outputs")

    key_name = outputs.get("key_name", stack_name)

    try:
        region = outputs.get("key_region")                # stack_region(stack_name)
    except Exception:
        region = get_region()

    try:
        client = boto3.client("secretsmanager", region_name=region)
        pem = client.get_secret_value(SecretId=secret_id)["SecretString"]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve private key from Secrets Manager: {exc}")

    return StreamingResponse(
        io.BytesIO(pem.encode()),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{key_name}.pem"'},
    )


@router.get("/{stack_name}", response_model=StackResponse)
def get_key_pair(stack_name: str):
    """Fetch outputs of an existing key pair stack."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        outputs = stack_outputs(stack_name)
        return StackResponse(status="ok", stack=stack_name, outputs=outputs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{stack_name}")
def delete_key_pair(stack_name: str):
    """Destroy the key pair stack and all associated AWS resources."""
    if not stack_exists(stack_name):
        raise HTTPException(status_code=404, detail=f"Stack '{stack_name}' not found")
    try:
        stack_destroy(stack_name)
        return {"status": "deleted", "stack": stack_name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
