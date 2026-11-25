import os
from dotenv import load_dotenv
load_dotenv()
from fastapi import Depends, FastAPI

from app.utils.auth import get_current_user
from app.routes.region import router as region_router
from app.routes.security_group import router as security_group_router
from app.routes.key_pair import router as key_pair_router
from app.routes.ec2 import router as ec2_router
from app.routes.amis import router as amis_router



# Pulumi state backend — S3 takes priority; fall back to Pulumi Cloud token.
_backend_url = os.getenv("PULUMI_BACKEND_URL")
_pulumi_token = os.getenv("PULUMI_ACCESS_TOKEN")

if _backend_url:
    os.environ["PULUMI_BACKEND_URL"] = _backend_url
elif _pulumi_token:
    os.environ["PULUMI_ACCESS_TOKEN"] = _pulumi_token
else:
    raise RuntimeError(
        "No Pulumi backend configured. Set either PULUMI_BACKEND_URL (S3) "
        "or PULUMI_ACCESS_TOKEN (Pulumi Cloud) in your .env file."
    )

# Required when using a self-hosted backend (S3).
_passphrase = os.getenv("PULUMI_CONFIG_PASSPHRASE")
if _passphrase is None:
    raise RuntimeError(
        "PULUMI_CONFIG_PASSPHRASE is not set. Add it to your .env file. "
        "Set to empty string to disable passphrase encryption."
    )
os.environ["PULUMI_CONFIG_PASSPHRASE"] = _passphrase

app = FastAPI(
    title="MultiCloud — AWS Compute Service",
    description=(
        "Microservice for provisioning AWS compute resources via the Pulumi Automation API. "
        "Each resource type (Security Group, Key Pair, EC2 Instance) is an "
        "independent Pulumi stack with full CRUD endpoints."
    ),
    version="2.0.0",
)

app.include_router(region_router, dependencies=[Depends(get_current_user)])
app.include_router(security_group_router, dependencies=[Depends(get_current_user)])
app.include_router(key_pair_router, dependencies=[Depends(get_current_user)])
app.include_router(ec2_router, dependencies=[Depends(get_current_user)])
app.include_router(amis_router, dependencies=[Depends(get_current_user)])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "aws-compute"}
