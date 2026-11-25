import boto3
from botocore.exceptions import ClientError
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.ami import AmiInfo

router = APIRouter(prefix="/amis", tags=["AMIs"])

# Name patterns and owner IDs for common platforms.
# owner IDs: "amazon" = AWS, "099720109477" = Canonical (Ubuntu)
_PLATFORMS = {
    "amazon-linux-2": {
        "owners": ["amazon"],
        "x86_64": "amzn2-ami-hvm-*-x86_64-gp2",
        "arm64":  "amzn2-ami-hvm-*-arm64-gp2",
    },
    "amazon-linux-2023": {
        "owners": ["amazon"],
        "x86_64": "al2023-ami-*-x86_64",
        "arm64":  "al2023-ami-*-arm64",
    },
    "ubuntu-22": {
        "owners": ["099720109477"],
        "x86_64": "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*",
        "arm64":  "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-arm64-server-*",
    },
    "ubuntu-24": {
        "owners": ["099720109477"],
        "x86_64": "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
        "arm64":  "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*",
    },
    "windows-2022": {
        "owners": ["amazon"],
        "x86_64": "Windows_Server-2022-English-Full-Base-*",
        "arm64":  None,
    },
    "windows-2019": {
        "owners": ["amazon"],
        "x86_64": "Windows_Server-2019-English-Full-Base-*",
        "arm64":  None,
    },
}

VALID_PLATFORMS = list(_PLATFORMS.keys())


@router.get("/{region}", response_model=List[AmiInfo])
def list_amis(
    region: str,
    platform: Optional[str] = Query(
        None,
        description=f"Preset OS filter. One of: {', '.join(VALID_PLATFORMS)}. "
                    "Defaults to amazon-linux-2023 when omitted.",
    ),
    name_filter: Optional[str] = Query(
        None,
        description="Custom AMI name wildcard pattern, e.g. 'amzn2-ami-*'. "
                    "Overrides platform when supplied.",
    ),
    owner: Optional[str] = Query(
        None,
        description="Owner ID or alias (e.g. 'amazon', '099720109477', 'self'). "
                    "Overrides the platform preset owner when supplied.",
    ),
    arch: str = Query("x86_64", description="CPU architecture: x86_64 or arm64"),
    max_results: int = Query(20, ge=1, le=100, description="Maximum number of results to return"),
):
    """
    List available AMIs in the given region, sorted newest first.

    Use `platform` for common OS presets, or `name_filter` for a custom wildcard.
    When neither is provided the endpoint returns the latest Amazon Linux 2023 images.
    """
    if arch not in ("x86_64", "arm64"):
        raise HTTPException(status_code=400, detail="arch must be 'x86_64' or 'arm64'")

    if platform and platform not in _PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform '{platform}'. Valid options: {VALID_PLATFORMS}",
        )

    # Resolve owners and name pattern
    if name_filter:
        owners = [owner] if owner else ["amazon"]
        name_pattern = name_filter
    else:
        preset = _PLATFORMS.get(platform or "amazon-linux-2023")
        owners = [owner] if owner else preset["owners"]
        name_pattern = preset.get(arch)
        if not name_pattern:
            raise HTTPException(
                status_code=400,
                detail=f"Platform '{platform}' does not support arch '{arch}'",
            )

    try:
        client = boto3.client("ec2", region_name=region)
        response = client.describe_images(
            Owners=owners,
            Filters=[
                {"Name": "name",               "Values": [name_pattern]},
                {"Name": "architecture",       "Values": [arch]},
                {"Name": "state",              "Values": ["available"]},
                {"Name": "virtualization-type","Values": ["hvm"]},
            ],
        )
    except ClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc2:
        raise HTTPException(status_code=502, detail=f"AWS describe_images failed: {exc2}") from exc

    images = sorted(
        response.get("Images", []),
        key=lambda img: img.get("CreationDate", ""),
        reverse=True,
    )[:max_results]

    return [
        AmiInfo(
            image_id=img["ImageId"],
            name=img.get("Name", ""),
            description=img.get("Description", ""),
            creation_date=img.get("CreationDate", ""),
            architecture=img.get("Architecture", ""),
            virtualization_type=img.get("VirtualizationType", ""),
            state=img.get("State", ""),
            owner_id=img.get("OwnerId", ""),
            platform=img.get("PlatformDetails"),
        )
        for img in images
    ]
