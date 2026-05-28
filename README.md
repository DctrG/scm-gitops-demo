# PANW GitOps VPN Automation

This repository shows two GitOps-style automation paths for managing PANW customer VPN configuration in Strata Cloud Manager:

- Python automation driven by `customers-to-add.yaml` and `customers-to-delete.yaml`.
- Terraform automation driven by `customers-terraform.yaml`.

Both workflows can live in the same repository. The file you change determines which GitHub Actions workflow runs.

## Repository Layout

```text
.
├── customers-to-add.yaml          # Python-managed customer add/update list
├── customers-to-delete.yaml       # Python-managed customer delete list
├── customers-terraform.yaml       # Terraform-managed desired state
├── deploy-multi-vpn.py            # Python deployment script
├── requirements.txt               # Python dependencies
├── .github/workflows/
│   ├── python-vpn.yml             # Python workflow
│   └── deploy-vpn.yml             # Terraform workflow
└── terraform/                     # Terraform implementation
```

## Ownership Model

Keep Python-managed and Terraform-managed resources separate so the two tools do not manage or delete the same SCM objects.

| Automation | Root folder | Customer folder naming |
| --- | --- | --- |
| Python | `PANW Python Global` | `PANW-Python-Customer-*` |
| Terraform | `PANW Terraform Global` | `PANW-Terraform-Customer-*` |

Do not put the same customer under both automation paths unless you intentionally want two separate test deployments.

## 1. Clone The Repository

```bash
git clone https://github.com/DctrG/scm-gitops-demo.git
cd scm-gitops-demo
```

Create a working branch for changes:

```bash
git checkout -b vpn/customer-change
```

## 2. Configure Strata Cloud Manager Credentials

Create or identify an SCM service account with permissions to manage the folders and VPN objects used by this repository.

You need:

```text
PANW_CLIENT_ID
PANW_CLIENT_SECRET
PANW_TSG_ID
```

`PANW_TSG_ID` should be the raw TSG ID only, not `tsg_id:<id>`.

Do not commit these values to Git.

## 3. Configure HCP Terraform

Terraform state is stored in HCP Terraform. The workspace is configured in `terraform/versions.tf`:

```hcl
cloud {
  organization = "panw-gitops"

  workspaces {
    name = "panw-gitops-dev"
  }
}
```

If you use a different organization or workspace, update `terraform/versions.tf`.

In HCP Terraform:

1. Create or select the organization.
2. Create a workspace, for example `panw-gitops-dev`.
3. Set the workspace execution mode to **Local**:

```text
Workspace -> Settings -> General -> Execution Mode -> Local
```

With Local execution, GitHub Actions runs `terraform plan/apply`, while HCP Terraform stores remote state and handles locking.

Optional workspace variables for local/manual Terraform use:

```text
panw_client_id
panw_client_secret
panw_tsg_id
```

Set them as Terraform variables and mark them sensitive.

## 4. Configure GitHub Secrets

In GitHub, go to:

```text
Repository -> Settings -> Secrets and variables -> Actions -> New repository secret
```

Add these repository secrets:

```text
PANW_CLIENT_ID
PANW_CLIENT_SECRET
PANW_TSG_ID
TF_TOKEN_APP_TERRAFORM_IO
```

The `PANW_*` secrets authenticate to Strata Cloud Manager. `TF_TOKEN_APP_TERRAFORM_IO` authenticates Terraform CLI to HCP Terraform.

To create the Terraform token:

1. Open HCP Terraform.
2. Go to user settings or organization settings for API tokens.
3. Create a token that can access the workspace.
4. Store it in GitHub as `TF_TOKEN_APP_TERRAFORM_IO`.

## 5. Python Workflow

Python-owned customers are managed with:

```text
customers-to-add.yaml
customers-to-delete.yaml
```

Use `customers-to-add.yaml` to add or update Python-managed customer VPNs:

```yaml
customers:
  - customer_name: "Customer-AB"
    folder_name: "PANW-Python-Customer-AB"
    customer_network: "10.24.0.0/16"
    customer_network_object: "customer-AB-Net"
    peer_ip: "203.0.113.20"
    psk: "replace-with-real-psk"
    tunnel_number: 11
    zone_name: "Customer-AB-Zone"
    ike_gateway_name: "Customer-AB-IKE-GW"
    ipsec_tunnel_name: "Customer-AB-Tunnel"
    security_rule_name: "allow-customer-ab-to-panw-python"
```

Use `customers-to-delete.yaml` to delete Python-managed folders:

```yaml
folders_to_delete:
  - "PANW-Python-Customer-AB"
```

Expected workflow:

1. Edit `customers-to-add.yaml` or `customers-to-delete.yaml`.
2. Commit and push your branch.
3. Open a pull request into `main`.
4. The Python workflow validates the YAML on the pull request.
5. Merge to `main`.
6. The Python workflow runs automatically.

## 6. Terraform Workflow

Terraform-owned customers are managed with:

```text
customers-terraform.yaml
```

Add customers to the `customers` list:

```yaml
customers:
  - customer_name: "Customer-AB"
    folder_name: "PANW-Terraform-Customer-AB"
    customer_network: "10.24.0.0/16"
    customer_network_object: "customer-AB-Net"
    peer_ip: "203.0.113.20"
    psk: "replace-with-real-psk"
    tunnel_number: 11
    zone_name: "Customer-AB-Zone"
    ike_gateway_name: "Customer-AB-IKE-GW"
    ipsec_tunnel_name: "Customer-AB-Tunnel"
    security_rule_name: "allow-customer-ab-to-panw-terraform"
    enabled: true
```

To remove a Terraform-managed customer, remove that customer from `customers-terraform.yaml`. Terraform will plan to destroy the resources it manages for that customer.

Expected workflow:

1. Edit `customers-terraform.yaml`.
2. Commit and push your branch.
3. Open a pull request into `main`.
4. The Terraform workflow runs `terraform plan`.
5. Review the plan.
6. Merge to `main`.
7. The Terraform workflow runs `terraform apply -auto-approve`.

## 7. Local Testing

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For local Python testing, set credentials in your shell or a local `.env` file:

```text
PANW_CLIENT_ID=...
PANW_CLIENT_SECRET=...
PANW_TSG_ID=...
```

Run the Python workflow locally:

```bash
python deploy-multi-vpn.py
```

For local Terraform testing, copy the Terraform customer file into the Terraform module directory, then run Terraform:

```bash
cp customers-terraform.yaml terraform/customers.yaml
terraform -chdir=terraform init
terraform -chdir=terraform plan
```

Do not commit `.env`, `terraform.tfvars`, Terraform state files, or plan files.

## 8. Safety Rules

- Python automation should only touch resources under `PANW Python Global`.
- Terraform automation should only touch resources under `PANW Terraform Global`.
- Use pull requests into `main` for both workflows.
- Review Terraform plans before merging.
- Never commit real API credentials, `.env`, `terraform.tfvars`, state files, generated secrets, or real PSKs.
