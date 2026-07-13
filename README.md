# PANW GitOps VPN Automation (Panorama)

This branch contains two automation paths for managing PANW customer VPN configuration in **Panorama** (PAN-OS XML API), instead of Strata Cloud Manager which is used on `main`:

- Python automation for customers defined in `customers-to-add.yaml` and `customers-to-delete.yaml`.
- Terraform automation for customers defined in `customers-terraform.yaml`.

Both workflows live in the same branch. The file you change determines which workflow runs.

## Ownership Model

Keep Python-managed and Terraform-managed resources separate so the two tools do not try to manage or delete the same Panorama objects. Each path owns one template (network config) and one parent device group (policies) with nested per-customer device groups.

| Automation | Template | Parent device group | Customer device groups |
| --- | --- | --- | --- |
| Python | `PANW-Python-Template` | `PANW-Python-Global` | `PANW-Python-Customer-*` |
| Terraform | `PANW-Terraform-Template` | `PANW-Terraform-Global` | `PANW-Terraform-Customer-*` |

Per customer, the automation creates:

- In the template: a tunnel interface, a zone, an IKE gateway and an IPsec tunnel (shared: ethernet interface, virtual router, IKE/IPsec crypto profiles).
- In the customer device group: address objects and a security rule.

Both paths commit the candidate configuration to Panorama at the end of a run.

Do not put the same customer under both automation paths unless you intentionally want two separate test deployments.

## Setup

### 1. Clone and branch

```bash
git clone git@github.com:DctrG/scm-gitops-demo.git
cd scm-gitops-demo
git checkout dev
```

### 2. Panorama API key

Generate an API key for an admin account:

```bash
curl -sk "https://<panorama-host>/api/?type=keygen&user=<user>&password=<password>"
```

### 3. GitHub Secrets

GitHub Actions needs these repository secrets (Settings → Secrets and variables → Actions):

```text
PANORAMA_HOST              Panorama hostname or IP
PANORAMA_API_KEY           Panorama XML API key
TF_TOKEN_APP_TERRAFORM_IO  HCP Terraform user/team API token (Terraform workflow only)
```

### 4. HCP Terraform workspace

The Terraform state lives in HCP Terraform (see `terraform/versions.tf`, workspace `panw-gitops-panorama` in org `panw-gitops`):

1. Create the workspace (CLI-driven workflow).
2. Set the execution mode to **Local**: `Workspace → Settings → General → Execution Mode → Local`. With local execution, GitHub Actions runs `terraform plan/apply` while HCP Terraform stores the shared state and handles locking.

## Python Workflow

Python-owned customers are configured with:

- `customers-to-add.yaml`
- `customers-to-delete.yaml`
- `deploy-multi-vpn.py`

Expected workflow:

1. Create a feature branch from `dev`.
2. Edit `customers-to-add.yaml` to add/update Python-managed customers, or `customers-to-delete.yaml` to delete Python-managed customer device groups.
3. Open a PR into `dev`.
4. The Python GitHub Actions workflow validates the YAML on the PR.
5. Merge to `dev`.
6. The Python workflow runs automatically, deploys/deletes the Python-managed VPN resources, and commits to Panorama.

## Terraform Workflow

Terraform-owned customers are configured with:

- `customers-terraform.yaml`
- Terraform code under `terraform/` (uses the [PaloAltoNetworks/panos](https://registry.terraform.io/providers/PaloAltoNetworks/panos/latest/docs) v2 provider)

Expected workflow:

1. Create a feature branch from `dev`.
2. Edit `customers-terraform.yaml`.
3. Open a PR into `dev`.
4. The Terraform GitHub Actions workflow runs `terraform plan` on the PR.
5. Review the plan.
6. Merge to `dev`.
7. The Terraform workflow runs `terraform apply -auto-approve` automatically and commits to Panorama.

## Local Testing

For local testing, keep credentials in `.env` or your shell:

```text
PANORAMA_HOST=...
PANORAMA_API_KEY=...
```

Do not commit `.env`.

Python:

```bash
pip install -r requirements.txt
python deploy-multi-vpn.py
```

Terraform (the config reads `terraform/customers.yaml`, so copy the customer file first):

```bash
export PANOS_HOSTNAME="$PANORAMA_HOST"
export PANOS_API_KEY="$PANORAMA_API_KEY"
cp customers-terraform.yaml terraform/customers.yaml
terraform -chdir=terraform init
terraform -chdir=terraform plan
```

Because Terraform uses the HCP Terraform `cloud` block with local execution mode, local and GitHub Actions `plan/apply` commands use the HCP Terraform workspace for shared state.

## Safety Rules

- Python automation should only touch `PANW-Python-Template` and device groups under `PANW-Python-Global`.
- Terraform automation should only touch `PANW-Terraform-Template` and device groups under `PANW-Terraform-Global`.
- Use PRs into `dev` for both workflows.
- Review Terraform plans before merging.
- Never commit real API credentials, `.env`, state files, or generated secrets.
