# MultiCloud Edge — AWS Compute Microservice

A **FastAPI + Pulumi Automation API** microservice that provisions AWS compute
infrastructure on demand. Each resource type is an independent Pulumi stack with its
own full CRUD API. Users interact via REST — no AWS Console, no manual Pulumi commands.

This service is one microservice in the larger **MultiCloud Edge** platform, which lets
teams provision cloud resources across AWS, Azure, and GCP from a single API surface.

---

## Architecture

```
Client (REST)
     │
     ▼
FastAPI  (main.py)
     │
     ├── /security-group   → Security Group stack
     ├── /key-pair         → EC2 Key Pair stack + Secrets Manager
     └── /ec2              → EC2 Instance stack
             │
             ▼
     Pulumi Automation API
             │
             ▼
     AWS (EC2 compute resources)
             │
     State stored in S3
```

Each resource lives in its own Pulumi stack. Stacks are independent — you can
create, update, or destroy one without touching the others.

Stack references (e.g. subnet, security group, key pair) are resolved by stack name
at request time — no raw AWS IDs needed in your payloads.

---

## Project Structure

```
multi-cloudEge-backend/
├── main.py                              # Uvicorn entry point
├── Pulumi.yaml                          # Pulumi project metadata
├── requirements.txt                     # Python dependencies
├── .env.example                         # Environment variable template
├── Dockerfile                           # Container image definition
├── entrypoint.sh                        # Container entrypoint (DNS + uvicorn)
├── .gitignore
├── README.md
│
└── app/
    ├── main.py                          # FastAPI app + router registration
    │
    ├── models/
    │   ├── common.py                    # Shared StackResponse model
    │   ├── ami.py                       # AmiInfo response model
    │   ├── security_group.py            # SecurityGroupRequest + SecurityGroupPatchRequest
    │   ├── key_pair.py                  # KeyPairRequest + KeyPairPatchRequest
    │   └── ec2.py                       # Ec2Request + Ec2PatchRequest
    │
    ├── routes/
    │   ├── region.py                    # POST /region/{region} · GET /region
    │   ├── amis.py                      # GET /amis/{region} — AMI discovery (no stack)
    │   ├── security_group.py            # POST · GET list · GET · PUT · PATCH · DELETE
    │   ├── key_pair.py                  # POST · GET list · GET · GET download · PUT · PATCH · DELETE
    │   └── ec2.py                       # POST · GET list · GET · PUT · PATCH · DELETE
    │
    ├── pulumi_programs/
    │   ├── security_group.py            # Pulumi inline program — Security Group
    │   ├── key_pair.py                  # Pulumi inline program — Key Pair + Secrets Manager
    │   └── ec2.py                       # Pulumi inline program — EC2 Instance
    │
    └── utils/
        ├── stack.py                     # stack_up · stack_up_safe · stack_exists · stack_outputs
        │                                # stack_region · stack_list · stack_destroy
        ├── region_state.py              # Active region store — AwsRegion enum, get_region, set_region
        └── slack.py                     # Optional Slack notifications
```

---

## AWS Resources Per Stack

| Stack | Resources Created |
|---|---|
| `/security-group` | Security Group with configurable ingress/egress rules |
| `/key-pair` | EC2 Key Pair (public key) + Secrets Manager secret (private key) |
| `/ec2` | EC2 Instance referencing subnet, security group, and key pair by stack name |

---

## Prerequisites

| Tool | Minimum Version |
|---|---|
| Python | 3.12+ |
| Pulumi CLI | 3.x |
| AWS CLI | 2.x |

---

## Setup

### 1. Clone and create virtualenv

```bash
git clone <repo-url>
cd multi-cloudEge-backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

Required variables:

| Variable | Description |
|---|---|
| `PULUMI_BACKEND_URL` | S3 state bucket e.g. `s3://my-bucket` |
| `PULUMI_CONFIG_PASSPHRASE` | Passphrase for stack secret encryption. Set to `""` to disable |
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_DEFAULT_REGION` | Default AWS region |

Optional:

| Variable | Description |
|---|---|
| `PULUMI_ACCESS_TOKEN` | Use instead of `PULUMI_BACKEND_URL` to store state in Pulumi Cloud |
| `SLACK_WEBHOOK_URL` | Slack notifications (see Slack section below) |

### 3. Create an S3 state bucket (first time only)

```bash
aws s3 mb s3://my-pulumi-state-bucket --region us-east-1
```

Then set in `.env`:
```
PULUMI_BACKEND_URL=s3://my-pulumi-state-bucket
```

### 4. Start the server

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs: http://localhost:8000/docs

---

## API Endpoints

Every resource follows the same pattern:

| Method | Path | Action |
|---|---|---|
| `POST` | `/{resource}` | Create a new stack (409 if it already exists) |
| `GET` | `/{resource}` | List all stacks of that resource type |
| `GET` | `/{resource}/{stack_name}` | Fetch current outputs |
| `PUT` | `/{resource}/{stack_name}` | Full update — Pulumi diffs and applies |
| `PATCH` | `/{resource}/{stack_name}` | Partial update — only send fields that change |
| `DELETE` | `/{resource}/{stack_name}` | Destroy all resources in the stack |

The `region` field is **optional** on all `POST`, `PUT`, and `PATCH` requests.
Omit it after calling `POST /region/{region}` to avoid repeating it.

Key pair stacks also have a download endpoint:

| Method | Path | Action |
|---|---|---|
| `GET` | `/key-pair/{stack_name}/download` | Download private key as a `.pem` file |

### Error codes

| Code | Meaning |
|---|---|
| `400` | Bad request — invalid AWS input (bad AMI ID, invalid instance type, etc.) |
| `404` | Stack not found |
| `409` | Stack already exists — use PUT or PATCH to update |
| `422` | Missing required fields that could not be resolved from stack outputs |
| `502` | Upstream AWS service error (e.g. Secrets Manager unreachable) |
| `500` | Unexpected server error |

---

## Region

All stack endpoints accept an optional `region` field. If you omit it, the service
uses the **active region** set via `POST /region/{region}`. This saves you from
repeating the region in every request when working in a single region.

### POST `/region/{region}` — Set the active region

```bash
curl -X POST http://localhost:8000/region/us-east-1
# {"active_region": "us-east-1"}
```

Once set, every subsequent `POST`, `PUT`, and `PATCH` request that omits `region`
will use `us-east-1` automatically.

### GET `/region` — Get the active region

```bash
curl http://localhost:8000/region
# {"active_region": "us-east-1"}
```

Returns 404 if no region has been set yet.

### Supported regions

| Africa | Asia Pacific | Canada | Europe | Israel | Middle East | South America | US |
|---|---|---|---|---|---|---|---|
| af-south-1 | ap-east-1 | ca-central-1 | eu-central-1 | il-central-1 | me-central-1 | sa-east-1 | us-east-1 |
| | ap-south-1 | ca-west-1 | eu-central-2 | | me-south-1 | | us-east-2 |
| | ap-south-2 | | eu-west-1 | | | | us-west-1 |
| | ap-northeast-1 | | eu-west-2 | | | | us-west-2 |
| | ap-northeast-2 | | eu-west-3 | | | | |
| | ap-northeast-3 | | eu-north-1 | | | | |
| | ap-southeast-1 | | eu-south-1 | | | | |
| | ap-southeast-2 | | eu-south-2 | | | | |
| | ap-southeast-3 | | | | | | |
| | ap-southeast-4 | | | | | | |

### Region resolution order

For `POST` / `PUT` — region is resolved in this priority:

1. `region` field in the request body
2. Active region from `POST /region/{region}`
3. → 422 error if neither is set

For `PATCH` — one additional fallback since the stack already exists:

1. `region` field in the request body
2. Active region from `POST /region/{region}`
3. Region stored in the existing stack's Pulumi config

---

## AMI Discovery

### GET `/amis/{region}` — List available AMIs

A lightweight lookup endpoint — no Pulumi stack involved. Calls the AWS
`describe_images` API and returns results sorted newest first. Use this to find
the right AMI ID before launching an EC2 instance.

#### Query parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `platform` | string | `amazon-linux-2023` | Preset OS filter (see table below) |
| `name_filter` | string | — | Custom AMI name wildcard, e.g. `amzn2-ami-*`. Overrides `platform` |
| `arch` | string | `x86_64` | CPU architecture: `x86_64` or `arm64` |
| `owner` | string | — | Owner ID or alias (`amazon`, `099720109477`, `self`). Overrides the preset owner |
| `max_results` | int | `20` | Number of results to return (1–100) |

#### Platform presets

| `platform` value | OS | Default owner |
|---|---|---|
| `amazon-linux-2` | Amazon Linux 2 | `amazon` |
| `amazon-linux-2023` | Amazon Linux 2023 | `amazon` |
| `ubuntu-22` | Ubuntu 22.04 LTS (Jammy) | `099720109477` (Canonical) |
| `ubuntu-24` | Ubuntu 24.04 LTS (Noble) | `099720109477` (Canonical) |
| `windows-2022` | Windows Server 2022 | `amazon` |
| `windows-2019` | Windows Server 2019 | `amazon` |

#### Examples

```bash
# Latest Amazon Linux 2023 AMIs in us-east-1 (default)
curl "http://localhost:8000/amis/us-east-1"

# Latest Ubuntu 24.04 AMIs in eu-west-1
curl "http://localhost:8000/amis/eu-west-1?platform=ubuntu-24"

# Amazon Linux 2023 on ARM (Graviton)
curl "http://localhost:8000/amis/us-east-1?platform=amazon-linux-2023&arch=arm64"

# Windows Server 2022 — top 5 results
curl "http://localhost:8000/amis/us-east-1?platform=windows-2022&max_results=5"

# Custom name wildcard
curl "http://localhost:8000/amis/us-east-1?name_filter=amzn2-ami-ecs-hvm-*&owner=amazon"
```

#### Response

Each item in the returned array:

| Field | Description |
|---|---|
| `image_id` | AMI ID — use this in your `/ec2` POST request |
| `name` | AMI name |
| `description` | AMI description |
| `creation_date` | ISO 8601 creation timestamp |
| `architecture` | `x86_64` or `arm64` |
| `virtualization_type` | `hvm` |
| `state` | `available` |
| `owner_id` | AWS account ID of the AMI owner |
| `platform` | Platform details string (e.g. `Linux/UNIX`, `Windows`) |

---

## Security Group Endpoints

### POST `/security-group` — Create a security group

The `vpc_stack` field is the name of an existing VPC stack. The service resolves the
`vpc_id` from that stack's outputs automatically — no raw VPC ID needed.

```json
{
  "stack": "prod-sg",
  "region": "us-east-1",
  "name": "prod-app-sg",
  "vpc_stack": "prod-vpc",
  "description": "Allow HTTP, HTTPS and SSH",
  "ingress": [
    { "protocol": "tcp", "from_port": 22,  "to_port": 22,  "cidr_blocks": ["0.0.0.0/0"], "description": "SSH" },
    { "protocol": "tcp", "from_port": 80,  "to_port": 80,  "cidr_blocks": ["0.0.0.0/0"], "description": "HTTP" },
    { "protocol": "tcp", "from_port": 443, "to_port": 443, "cidr_blocks": ["0.0.0.0/0"], "description": "HTTPS" }
  ],
  "egress": [
    { "protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"], "description": "Allow all outbound" }
  ],
  "tags": { "Environment": "prod" }
}
```

> **Protocol values:** `tcp`, `udp`, `icmp`, or `-1` (all traffic).

**Response outputs:**

| Field | Description |
|---|---|
| `security_group_id` | AWS security group ID |
| `security_group_name` | Security group name |
| `vpc_id` | VPC the group was created in |
| `description` | Security group description |
| `ingress` | List of ingress rules as stored |
| `egress` | List of egress rules as stored |

---

### GET `/security-group` — List all security group stacks

Returns all stacks that contain a `security_group_id` output.

```bash
curl http://localhost:8000/security-group
```

---

### GET `/security-group/{stack_name}` — Get a security group stack

```bash
curl http://localhost:8000/security-group/prod-sg
```

---

### PUT `/security-group/{stack_name}` — Full update

All fields required. The `stack` field in the body must match the URL `stack_name`.
Pulumi diffs the current rules against the desired rules and applies only the diff —
rules are not recreated unless they actually changed.

```json
{
  "stack": "prod-sg",
  "region": "us-east-1",
  "name": "prod-app-sg",
  "vpc_stack": "prod-vpc",
  "description": "Allow HTTP, HTTPS, SSH and custom app port",
  "ingress": [
    { "protocol": "tcp", "from_port": 22,   "to_port": 22,   "cidr_blocks": ["10.0.0.0/8"], "description": "SSH internal only" },
    { "protocol": "tcp", "from_port": 80,   "to_port": 80,   "cidr_blocks": ["0.0.0.0/0"],  "description": "HTTP" },
    { "protocol": "tcp", "from_port": 443,  "to_port": 443,  "cidr_blocks": ["0.0.0.0/0"],  "description": "HTTPS" },
    { "protocol": "tcp", "from_port": 8080, "to_port": 8080, "cidr_blocks": ["0.0.0.0/0"],  "description": "App" }
  ],
  "egress": [
    { "protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"], "description": "Allow all outbound" }
  ],
  "tags": { "Environment": "prod" }
}
```

---

### PATCH `/security-group/{stack_name}` — Partial update

Only include the fields you want to change. Omitted fields are taken from the current
stack outputs. The `stack` field, if provided, must match the URL `stack_name`.
`vpc_stack` falls back to the stored `vpc_id` if not supplied.

Add a rule without resending the whole config:

```json
{
  "ingress": [
    { "protocol": "tcp", "from_port": 22,  "to_port": 22,  "cidr_blocks": ["0.0.0.0/0"], "description": "SSH" },
    { "protocol": "tcp", "from_port": 80,  "to_port": 80,  "cidr_blocks": ["0.0.0.0/0"], "description": "HTTP" },
    { "protocol": "tcp", "from_port": 443, "to_port": 443, "cidr_blocks": ["0.0.0.0/0"], "description": "HTTPS" },
    { "protocol": "tcp", "from_port": 8080,"to_port": 8080, "cidr_blocks": ["0.0.0.0/0"], "description": "App" }
  ]
}
```

> **Note:** `ingress` and `egress` are replaced as a whole list — there is no
> "add one rule" primitive. To add a rule, send the complete desired rule set.

---

### DELETE `/security-group/{stack_name}` — Delete a security group

Destroys the security group. Returns 404 if the stack does not exist. AWS will reject
the destroy if any running EC2 instances are still attached to the group — delete or
update those instances first.

```bash
curl -X DELETE http://localhost:8000/security-group/prod-sg
```

---

## Key Pair Endpoints

### POST `/key-pair` — Create a key pair

Mirrors the AWS Console "Create key pair" flow. The service generates a 4096-bit RSA
key pair, registers the public key with EC2, and stores the private key in
**AWS Secrets Manager** at path `ec2/keypair/{name}/private-key`. The private key
never appears in the API response — retrieve it via the `/download` endpoint.

```json
{
  "stack": "prod-keypair",
  "region": "us-east-1",
  "name": "prod-key",
  "tags": { "Environment": "prod" }
}
```

**Response outputs:**

| Field | Description |
|---|---|
| `key_name` | EC2 key pair name |
| `key_pair_id` | EC2 key pair resource ID |
| `private_key_secret_arn` | ARN of the Secrets Manager secret holding the private key |
| `private_key_secret_name` | Name/path of the secret: `ec2/keypair/{name}/private-key` |

---

### GET `/key-pair` — List all key pair stacks

Returns all stacks that contain a `key_name` output.

```bash
curl http://localhost:8000/key-pair
```

---

### GET `/key-pair/{stack_name}` — Get a key pair stack

```bash
curl http://localhost:8000/key-pair/prod-keypair
```

---

### GET `/key-pair/{stack_name}/download` — Download the private key

Fetches the private key from AWS Secrets Manager and streams it as a `.pem` file
attachment. This is the equivalent of downloading the key file from the AWS Console.

```bash
curl -O http://localhost:8000/key-pair/prod-keypair/download
chmod 400 prod-key.pem
```

The downloaded file is named `{key_name}.pem`.

To SSH into an instance using the key:

```bash
ssh -i prod-key.pem ec2-user@<public_ip>
```

You can also retrieve the raw key directly from Secrets Manager:

```bash
aws secretsmanager get-secret-value \
  --secret-id ec2/keypair/prod-key/private-key \
  --query SecretString --output text > prod-key.pem
chmod 400 prod-key.pem
```

---

### PUT `/key-pair/{stack_name}` — Full update

All fields required. The `stack` field in the body must match the URL `stack_name`.

```json
{
  "stack": "prod-keypair",
  "region": "us-east-1",
  "name": "prod-key",
  "tags": { "Environment": "prod", "Team": "platform" }
}
```

> **Note:** Changing `name` renames the EC2 key pair. Pulumi will delete the old key pair
> and create a new one, then update the Secrets Manager secret to match.

---

### PATCH `/key-pair/{stack_name}` — Partial update

Only include the fields you want to change. Omitted fields are taken from the current
stack outputs. The `stack` field, if provided, must match the URL `stack_name`.

```json
{
  "tags": { "Environment": "prod", "Team": "platform" }
}
```

---

### DELETE `/key-pair/{stack_name}` — Delete a key pair

Destroys the EC2 key pair and its Secrets Manager secret. Returns 404 if the stack
does not exist.

```bash
curl -X DELETE http://localhost:8000/key-pair/prod-keypair
```

---

## EC2 Endpoints

### POST `/ec2` — Launch an EC2 instance

The `subnet_stack`, `security_group_stack`, and `key_pair_stack` fields are stack names.
The service resolves the actual AWS IDs from each stack's outputs — no raw IDs needed
in your payloads.

```json
{
  "stack": "prod-ec2",
  "region": "us-east-1",
  "name": "prod-app",
  "ami": "ami-0c02fb55956c7d316",
  "instance_type": "t3.micro",
  "subnet_stack": "prod-subnet",
  "security_group_stack": "prod-sg",
  "key_pair_stack": "prod-keypair",
  "associate_public_ip": true,
  "user_data": "",
  "tags": { "Environment": "prod" }
}
```

**Response outputs:**

| Field | Description |
|---|---|
| `instance_id` | EC2 instance ID |
| `private_ip` | Private IP address |
| `public_ip` | Public IP address (empty if no public IP assigned) |
| `instance_state` | Current state: `running`, `pending`, etc. |
| `name` | Instance name tag |
| `ami` | AMI ID used |
| `instance_type` | Instance type |
| `subnet_id` | Resolved subnet ID |
| `security_group_id` | Resolved security group ID |
| `key_name` | Key pair name attached to the instance |
| `associate_public_ip` | Whether a public IP was assigned |
| `user_data` | User data script (empty string if none) |

> **Finding an AMI:**
> ```bash
> aws ec2 describe-images --owners amazon \
>   --filters "Name=name,Values=amzn2-ami-hvm-*-x86_64-gp2" \
>   --query "Images | sort_by(@, &CreationDate) | [-1].ImageId" \
>   --region us-east-1
> ```

---

### GET `/ec2` — List all EC2 stacks

Returns all stacks that contain an `instance_id` output.

```bash
curl http://localhost:8000/ec2
```

---

### GET `/ec2/{stack_name}` — Get an EC2 stack

```bash
curl http://localhost:8000/ec2/prod-ec2
```

---

### PUT `/ec2/{stack_name}` — Full update

All fields required. The `stack` field in the body must match the URL `stack_name`.
Pulumi diffs the current state and applies only what changed.

```json
{
  "stack": "prod-ec2",
  "region": "us-east-1",
  "name": "prod-app",
  "ami": "ami-0c02fb55956c7d316",
  "instance_type": "t3.small",
  "subnet_stack": "prod-subnet",
  "security_group_stack": "prod-sg",
  "key_pair_stack": "prod-keypair",
  "associate_public_ip": true,
  "tags": { "Environment": "prod", "Team": "platform" }
}
```

> **Note:** Changing `ami` or `instance_type` causes AWS to stop, modify, and restart
> the instance. Changing `subnet_id` or `security_group_id` requires instance replacement.

---

### PATCH `/ec2/{stack_name}` — Partial update

Only include the fields you want to change. Omitted fields are taken from the current
stack outputs. Networking stack references (`subnet_stack`, `security_group_stack`,
`key_pair_stack`) fall back to the resolved IDs stored from the last deploy — you only
need to supply them if you want to point the instance at a different resource.

```json
{
  "instance_type": "t3.small",
  "tags": { "Environment": "prod", "CostCenter": "eng" }
}
```

---

### DELETE `/ec2/{stack_name}` — Terminate an EC2 instance

Destroys the instance and removes the stack record. Returns 404 if the stack does
not exist.

```bash
curl -X DELETE http://localhost:8000/ec2/prod-ec2
```

---

## Typical Provisioning Order

Resources must be created in dependency order. The EC2 instance depends on a subnet,
security group, and key pair — all of which must exist as stacks first.

```
1. POST /key-pair
        │  key_name  (resolved by stack name)
        │
2. POST /security-group  ◄── requires an existing VPC stack
        │  security_group_id  (resolved by stack name)
        │
        │  subnet already exists as a stack from the networking service
        │  subnet_id  (resolved by stack name)
        │
        ▼
3. POST /ec2
        │
        ▼
4. GET /key-pair/{stack_name}/download  ──►  prod-key.pem
        │
        ▼
5. ssh -i prod-key.pem ec2-user@<public_ip>
```

---

## Stack Naming Convention

Use a consistent naming pattern to keep stacks identifiable:

```
{env}-{resource}-{region}

prod-keypair-us-east-1
prod-sg-us-east-1
prod-ec2-us-east-1
```

---

## How Pulumi State Works

Each stack has a state file in S3 that tracks the AWS resources it manages.

- **POST** creates a new stack. Returns 409 if the stack already exists.
- **PUT** and **PATCH** both call `stack.up()` — Pulumi diffs current vs desired state
  and applies only what changed. Re-running is safe and idempotent.
- **DELETE** calls `stack.destroy()` then removes the stack record from S3.
- Stacks are fully isolated — destroying one never touches another.
- If a **POST** fails mid-way, the partially-created stack is automatically destroyed
  and removed so the name is free to retry.

---

## Docker

### 1. Build the image

```bash
docker build -t multicloud-demo-backend .
```

### 2. Prepare your environment file

```bash
cp .env.example .env
# Fill in real values — at minimum the five required variables below
```

### 3. Run the container

```bash
docker run -d \
  --name multicloud-demo \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  multicloud-demo-backend
```

API available at: http://localhost:8000/docs

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `PULUMI_BACKEND_URL` | Yes (or token) | S3 state bucket, e.g. `s3://my-pulumi-state-bucket` |
| `PULUMI_ACCESS_TOKEN` | Yes (or URL) | Pulumi Cloud token — alternative to S3 backend |
| `PULUMI_CONFIG_PASSPHRASE` | Yes | Passphrase for stack secret encryption. Set to empty string `""` to disable |
| `AWS_ACCESS_KEY_ID` | Yes | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | AWS secret key |
| `AWS_DEFAULT_REGION` | Yes | Fallback AWS region (e.g. `us-east-1`) |
| `SLACK_WEBHOOK_URL` | No | Slack notifications webhook URL |

> `PULUMI_CONFIG_PASSPHRASE` is **required** even when using an S3 backend. Set it to an
> empty string only in non-production environments where secret encryption is not needed.

### Health check

The image has a built-in Docker health check that polls `GET /health`:

```bash
docker inspect --format='{{.State.Health.Status}}' multicloud-demo
# starting → healthy (allow ~60 s on first run for Pulumi plugin downloads)
```

### Docker Compose

For local development or multi-container setups, create a `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      start_period: 60s
      retries: 3
```

```bash
docker compose up -d
docker compose logs -f api
```

### Useful commands

```bash
# Tail logs
docker logs -f multicloud-demo

# Open a shell inside the container
docker exec -it multicloud-demo /bin/sh

# Stop and remove
docker stop multicloud-demo && docker rm multicloud-demo

# Rebuild after code changes
docker build -t multicloud-demo-backend . && \
  docker stop multicloud-demo && docker rm multicloud-demo && \
  docker run -d --name multicloud-demo -p 8000:8000 --env-file .env multicloud-demo-backend
```

---

## Slack Notifications (disabled by default)

Slack is not active in the current code. To enable it:

**1.** Create an Incoming Webhook at https://api.slack.com/messaging/webhooks

**2.** Add to `.env`:
```
SLACK_WEBHOOK_URL=<your-slack-incoming-webhook-url>.../B.../xxx
```

**3.** In any route file (e.g. `app/routes/ec2.py`), add at the top:
```python
from app.utils.slack import send_slack_message
```

Then call it after a successful `stack_up_safe(...)`:
```python
send_slack_message(f":white_check_mark: *{req.stack}* created — Instance: {outputs.get('instance_id')}")
```

The `send_slack_message` function silently skips if the webhook URL is missing.

---

## Running in Production

```bash
pip install gunicorn
gunicorn main:app -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:8000
```

---

## Extending to Other Cloud Providers

To add Azure or GCP compute resources:

1. Add models in `app/models/`
2. Add a Pulumi program in `app/pulumi_programs/`
3. Add a router in `app/routes/` and register it in `app/main.py`

No existing files need to change.
