from typing import Dict, Optional
import pulumi
import pulumi_aws as aws


def create_ec2_program(
    name: str,
    ami: str,
    instance_type: str,
    subnet_id: str,
    region: str,
    security_group_id: str,
    key_name: Optional[str],
    associate_public_ip: bool,
    user_data: Optional[str],
    tags: Dict[str, str],
):
    def program():
        base_tags = {"ManagedBy": "Pulumi", **tags, "Name": name}

        instance = aws.ec2.Instance(
            f"{name}-instance",
            ami=ami,
            instance_type=instance_type,
            subnet_id=subnet_id,
            vpc_security_group_ids=[security_group_id],
            key_name=key_name or None,
            associate_public_ip_address=associate_public_ip,
            user_data=user_data or None,
            tags=base_tags,
        )

        pulumi.export("instance_id", instance.id)
        pulumi.export("private_ip", instance.private_ip)
        pulumi.export("public_ip", instance.public_ip)
        pulumi.export("instance_state", instance.instance_state)
        # Store resolved inputs so PATCH can reconstruct without requiring stack references.
        pulumi.export("name", name)
        pulumi.export("ami", ami)
        pulumi.export("instance_type", instance_type)
        pulumi.export("subnet_id", subnet_id)
        pulumi.export("security_group_id", security_group_id)
        pulumi.export("key_name", key_name or "")
        pulumi.export("associate_public_ip", associate_public_ip)
        pulumi.export("user_data", user_data or "")
        pulumi.export("ec2_region", region)

    return program
