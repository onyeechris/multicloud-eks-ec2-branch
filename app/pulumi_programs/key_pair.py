from typing import Dict
import pulumi
import pulumi_aws as aws
import pulumi_tls as tls


def create_key_pair_program(
    name: str,
    region: str,
    tags: Dict[str, str],
):
    def program():
        base_tags = {"ManagedBy": "Pulumi", **tags, "Name": name}

        generated = tls.PrivateKey(f"{name}-tls-key", algorithm="RSA", rsa_bits=4096)

        kp = aws.ec2.KeyPair(
            f"{name}-keypair",
            key_name=name,
            public_key=generated.public_key_openssh,
            tags=base_tags,
        )

        # Store the private key in Secrets Manager so it is maintained entirely in AWS,
        # mirroring console behaviour where the key material never leaves the AWS environment.
        secret = aws.secretsmanager.Secret(
            f"{name}-private-key-secret",
            name=f"ec2/keypair/{name}/private-key",
            description=f"Private key for EC2 key pair: {name}",
            tags=base_tags,
            recovery_window_in_days=0,
        )

        aws.secretsmanager.SecretVersion(
            f"{name}-private-key-secret-version",
            secret_id=secret.id,
            secret_string=generated.private_key_pem,
        )

        pulumi.export("key_name", kp.key_name)
        pulumi.export("key_pair_id", kp.id)
        pulumi.export("key_region", region)
        pulumi.export("private_key_secret_arn", secret.arn)
        pulumi.export("private_key_secret_name", secret.name)

    return program
