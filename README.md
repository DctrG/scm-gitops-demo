# PANW GitOps VPN Automation

This repository contains two automation paths for managing PANW customer VPN configuration in Strata Cloud Manager:

- Python automation for customers defined in `customers-to-add.yaml` and `customers-to-delete.yaml`.
- Terraform automation for customers defined in `customers-terraform.yaml`.

Both workflows can live in the same repository. The file you change determines which workflow runs.

## Ownership Model

Keep Python-managed and Terraform-managed resources separate so the two tools do not try to manage or delete the same SCM objects.

| Automation | Root folder | Customer folder naming |
| --- | --- | --- |
| Python | `PANW Python Global` | `PANW-Python-Customer-*` |
| Terraform | `PANW Terraform Global` | `PANW-Terraform-Customer-*` |

Do not put the same customer under both automation paths unless you intentionally want two separate test deployments.

## Python Workflow

Python-owned customers are configured with:

- `customers-to-add.yaml`
- `customers-to-delete.yaml`
- `deploy-multi-vpn.py`

Expected workflow:

1. Create a feature branch.
2. Edit `customers-to-add.yaml` to add/update Python-managed customers, or `customers-to-delete.yaml` to delete Python-managed customer folders.
3. Open a PR into `main`.
4. The Python GitHub Actions workflow validates the YAML on the PR.
5. Merge to `main`.
6. The Python workflow runs automatically and deploys/deletes the Python-managed VPN resources.

## Terraform Workflow

Terraform-owned customers are configured with:

- `customers-terraform.yaml`
- Terraform code under `terraform/`

Expected workflow:

1. Create a feature branch.
2. Edit `customers-terraform.yaml`.
3. Open a PR into `main`.
4. The Terraform GitHub Actions workflow runs `terraform plan` on the PR.
5. Review the plan.
6. Merge to `main`.
7. The Terraform workflow runs `terraform apply -auto-approve` automatically.

Terraform state is stored in HCP Terraform using the workspace configured in `terraform/versions.tf`.

## Required GitHub Secrets

GitHub Actions needs these repository secrets:

```text
PANW_CLIENT_ID
PANW_CLIENT_SECRET
PANW_TSG_ID
TF_TOKEN_APP_TERRAFORM_IO
```

The `PANW_*` secrets are used by both workflows. `TF_TOKEN_APP_TERRAFORM_IO` is used by the Terraform workflow to authenticate to HCP Terraform.

## Required HCP Terraform Variables

The HCP Terraform workspace should use **Local** execution mode. With local execution, GitHub Actions runs `terraform plan/apply`, while HCP Terraform stores the shared state and handles locking.

Set this in HCP Terraform:

```text
Workspace panw-gitops-dev -> Settings -> General -> Execution Mode -> Local
```

If the workspace is left in remote execution mode, HCP Terraform will run provider installation inside its remote runner. That can fail if the remote runner cannot download the PANW provider from GitHub release assets.

The HCP Terraform workspace can still keep these workspace variables for local/manual HCP use:

```text
panw_client_id
panw_client_secret
panw_tsg_id
```

Set them as Terraform variables and mark them sensitive. `panw_tsg_id` should be the raw TSG ID only, not `tsg_id:<id>`.

## Local Testing

For local Python testing, keep credentials in `.env` or your shell:

```text
PANW_CLIENT_ID=...
PANW_CLIENT_SECRET=...
PANW_TSG_ID=...
```

Do not commit `.env`.

For local Terraform testing:

```bash
terraform -chdir=terraform init
terraform -chdir=terraform plan
```

Because Terraform uses the HCP Terraform `cloud` block with local execution mode, local and GitHub Actions `plan/apply` commands use the HCP Terraform workspace for shared state.

## Safety Rules

- Python automation should only touch resources under `PANW Python Global`.
- Terraform automation should only touch resources under `PANW Terraform Global`.
- Use PRs into `main` for both workflows.
- Review Terraform plans before merging.
- Never commit real API credentials, `.env`, state files, or generated secrets.
