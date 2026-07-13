# PANW GitOps VPN Automation

This repository manages PANW customer IPsec VPN configuration for **two targets** from a single `main` branch:

| Folder | Target | API |
| --- | --- | --- |
| `scm/` | Strata Cloud Manager | REST API (OAuth2) / [scm](https://registry.terraform.io/providers/PaloAltoNetworks/scm/latest/docs) provider |
| `panorama/` | Panorama (PAN-OS) | XML API / [panos](https://registry.terraform.io/providers/PaloAltoNetworks/panos/latest/docs) provider |

Each folder contains a Python automation path and a Terraform automation path. **The file you change determines which workflow runs** — edit files under `scm/` to deploy to Strata Cloud Manager, under `panorama/` to deploy to Panorama, or both in one commit to deploy to both.

## Repository Layout

```
scm/                        # Strata Cloud Manager target
├── customers-to-add.yaml   #   Python-managed customers
├── customers-to-delete.yaml
├── deploy-multi-vpn.py
├── customers-terraform.yaml #  Terraform-managed customers
└── terraform/               #  scm provider, HCP workspace panw-gitops-dev

panorama/                   # Panorama target
├── customers-to-add.yaml
├── customers-to-delete.yaml
├── deploy-multi-vpn.py
├── customers-terraform.yaml
└── terraform/               #  panos provider, HCP workspace panw-gitops-panorama

.github/workflows/
├── scm-python.yml          # triggers on scm/customers-to-add|delete.yaml
├── scm-terraform.yml       # triggers on scm/customers-terraform.yaml, scm/terraform/**
├── panorama-python.yml     # triggers on panorama/customers-to-add|delete.yaml
└── panorama-terraform.yml  # triggers on panorama/customers-terraform.yaml, panorama/terraform/**
```

## Ownership Model

Keep Python-managed and Terraform-managed resources separate so the two tools do not manage the same objects.

| Target | Automation | Container | Customer naming |
| --- | --- | --- | --- |
| SCM | Python | folder `PANW Python Global` | `PANW-Python-Customer-*` |
| SCM | Terraform | folder `PANW Terraform Global` | `PANW-Terraform-Customer-*` |
| Panorama | Python | template `PANW-Python-Template` + device group `PANW-Python-Global` | `PANW-Python-Customer-*` |
| Panorama | Terraform | template `PANW-Terraform-Template` + device group `PANW-Terraform-Global` | `PANW-Terraform-Customer-*` |

Both Panorama paths commit the candidate configuration at the end of a run.

## Workflow

1. Create a feature branch.
2. Edit the customer YAML for the target(s) and tool you want:
   - `scm/customers-to-add.yaml` or `scm/customers-terraform.yaml` for SCM
   - `panorama/customers-to-add.yaml` or `panorama/customers-terraform.yaml` for Panorama
   - Edit files in both folders to deploy the same customer to both targets in one commit.
3. Open a PR into `main`. The matching workflows validate the YAML (Python) or run `terraform plan` (Terraform).
4. Review, then merge to `main`. The matching workflows deploy automatically.

Deleting customers:

- Python: list them in the folder's `customers-to-delete.yaml`, or simply remove/comment them in `customers-to-add.yaml` (orphan cleanup deletes anything not listed).
- Terraform: remove/comment them in the folder's `customers-terraform.yaml`; `terraform apply` destroys them.

## Setup

### GitHub Secrets

Settings → Secrets and variables → Actions:

```text
PANW_CLIENT_ID             SCM OAuth2 client ID
PANW_CLIENT_SECRET         SCM OAuth2 client secret
PANW_TSG_ID                SCM tenant service group ID
PANORAMA_HOST              Panorama hostname or IP
PANORAMA_API_KEY           Panorama XML API key
TF_TOKEN_APP_TERRAFORM_IO  HCP Terraform API token (both Terraform workflows)
```

Generate the Panorama API key with:

```bash
curl -sk "https://<panorama-host>/api/?type=keygen&user=<user>&password=<password>"
```

The Panorama management interface (port 443) must be reachable from GitHub-hosted runners.

### HCP Terraform

Two workspaces in org `panw-gitops`, both in **Local** execution mode (Workspace → Settings → General → Execution Mode → Local):

- `panw-gitops-dev` — state for `scm/terraform`
- `panw-gitops-panorama` — state for `panorama/terraform`

With local execution, GitHub Actions runs `terraform plan/apply` while HCP Terraform stores the shared state and handles locking.

## Local Testing

Keep credentials in `.env` or your shell (never commit them):

```text
PANW_CLIENT_ID=...
PANW_CLIENT_SECRET=...
PANW_TSG_ID=...
PANORAMA_HOST=...
PANORAMA_API_KEY=...
```

Python (run from inside the target folder):

```bash
pip install -r requirements.txt
cd scm        # or: cd panorama
python deploy-multi-vpn.py
```

Terraform (the config reads `terraform/customers.yaml`, so copy the customer file first):

```bash
cd panorama   # or: cd scm
export PANOS_HOSTNAME="$PANORAMA_HOST" PANOS_API_KEY="$PANORAMA_API_KEY"   # Panorama only
cp customers-terraform.yaml terraform/customers.yaml
terraform -chdir=terraform init
terraform -chdir=terraform plan
```

## Safety Rules

- Python automation only touches `PANW-Python-*` / `PANW Python Global` containers; Terraform only `PANW-Terraform-*` / `PANW Terraform Global`.
- Use PRs into `main` and review Terraform plans before merging.
- Never commit real API credentials, `.env`, state files, or generated secrets.
