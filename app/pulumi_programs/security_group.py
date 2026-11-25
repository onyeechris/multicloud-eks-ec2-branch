from typing import Dict, List
import pulumi
import pulumi_aws as aws

from app.models.security_group import IngressRule, EgressRule


def create_security_group_program(
    name: str,
    vpc_id: str,
    region: str,
    description: str,
    ingress: List[IngressRule],
    egress: List[EgressRule],
    tags: Dict[str, str],
):
    def program():
        base_tags = {"ManagedBy": "Pulumi", **tags, "Name": name}
        resolved_description = description or f"Security group for {name}"

        sg = aws.ec2.SecurityGroup(
            f"{name}-sg",
            name=name,
            description=resolved_description,
            vpc_id=vpc_id,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol=r.protocol,
                    from_port=r.from_port,
                    to_port=r.to_port,
                    cidr_blocks=r.cidr_blocks,
                    description=r.description,
                )
                for r in ingress
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol=r.protocol,
                    from_port=r.from_port,
                    to_port=r.to_port,
                    cidr_blocks=r.cidr_blocks,
                    description=r.description,
                )
                for r in egress
            ],
            tags=base_tags,
        )

        pulumi.export("security_group_id", sg.id)
        pulumi.export("security_group_name", sg.name)
        pulumi.export("vpc_id", vpc_id)
        pulumi.export("sg_region", region)
        # Store resolved inputs so PATCH can reconstruct without requiring all fields.
        pulumi.export("description", resolved_description)
        pulumi.export("ingress", [
            {"protocol": r.protocol, "from_port": r.from_port, "to_port": r.to_port,
             "cidr_blocks": r.cidr_blocks, "description": r.description}
            for r in ingress
        ])
        pulumi.export("egress", [
            {"protocol": r.protocol, "from_port": r.from_port, "to_port": r.to_port,
             "cidr_blocks": r.cidr_blocks, "description": r.description}
            for r in egress
        ])

    return program
