# Testing Guide

This guide explains how to test the Terraform deployment locally and via GitHub Actions.

## Local Testing

### Prerequisites
1. Terraform >= 1.8 installed
2. Python 3 (for YAML validation)
3. Panorama credentials set up (via `.env` file or environment variables)

### Step-by-Step Testing

#### 1. Validate YAML Configuration
```bash
cd terraform
python3 -c "import yaml; yaml.safe_load(open('../customers-terraform.yaml')); print('✓ customers-terraform.yaml is valid')"
```

#### 2. Set Up Credentials
```bash
export PANOS_HOSTNAME="panorama.example.com"
export PANOS_API_KEY="your-panorama-api-key"
```

#### 3. Copy the customer file
The Terraform config reads `terraform/customers.yaml`:
```bash
cp ../customers-terraform.yaml customers.yaml
```

#### 4. Initialize Terraform
```bash
terraform init
```
Expected: "Terraform has been successfully initialized!"

#### 5. Validate Terraform Configuration
```bash
terraform validate
```
Expected: "Success! The configuration is valid."

#### 6. Plan Deployment (Dry-Run)
```bash
terraform plan
```
This shows what resources would be created without actually creating them.

#### 7. Apply Deployment (Optional - Creates Real Resources)
⚠️ **Warning**: This will create actual resources in Panorama and commit them!
```bash
terraform apply
```

#### 8. Verify Resources Were Created
Check the Panorama UI or use Terraform state:
```bash
terraform show
```

#### 9. Destroy Resources (Cleanup)
⚠️ **Warning**: This will delete all resources!
```bash
terraform destroy
```

## GitHub Actions Testing

### Prerequisites
1. GitHub repository with secrets configured:
   - `PANORAMA_HOST`
   - `PANORAMA_API_KEY`
   - `TF_TOKEN_APP_TERRAFORM_IO`

### Testing Methods

#### Method 1: Manual Workflow Trigger (Recommended for Testing)
1. Go to your GitHub repository
2. Navigate to **Actions** tab
3. Select **"Deploy VPN (Terraform)"** workflow
4. Click **"Run workflow"**
5. Choose action:
   - **`plan`** - Only shows what would change (safest)
   - **`apply`** - Actually deploys resources
   - **`destroy`** - Removes all resources
6. Click **"Run workflow"**

#### Method 2: Push to Trigger Workflow
1. Make a change to any file in `terraform/` directory or `customers-terraform.yaml`
2. Commit and push to `main`
3. Workflow will automatically run `terraform apply`
4. Check the **Actions** tab to see progress

### Verifying Workflow Success

1. **Check workflow run status**:
   - Green checkmark = Success
   - Red X = Failure (check logs)

2. **Review workflow logs**:
   - Click on the workflow run
   - Expand each step to see detailed output
   - Check for any errors or warnings

3. **Verify in Panorama**:
   - Log into the Panorama UI
   - Check that the template, device groups and VPN objects were created
   - Check **Tasks** for the commit job

## Troubleshooting

**Error: "Failed to authenticate" / 403 from Panorama**
- Verify `PANOS_HOSTNAME` and `PANOS_API_KEY` are correctly set
- Regenerate the API key: `curl -sk "https://<host>/api/?type=keygen&user=<user>&password=<pass>"`

**Error: "YAML validation failed"**
- Check `customers-terraform.yaml` syntax
- Use a YAML validator or Python: `python3 -c "import yaml; yaml.safe_load(open('../customers-terraform.yaml'))"`

**Workflow fails at "Terraform init"**
- Check `TF_TOKEN_APP_TERRAFORM_IO` is configured in GitHub Secrets
- Verify the HCP Terraform workspace in `versions.tf` exists and uses **Local** execution mode

**Commit step fails**
- Check the Panorama **Tasks** list for the failing commit job details
- Ensure no other administrator holds a config lock

## Quick Test Checklist

- [ ] YAML file validates successfully
- [ ] Terraform init completes without errors
- [ ] Terraform validate passes
- [ ] Terraform plan shows expected resources
- [ ] GitHub Actions workflow runs successfully (at least `plan` action)
- [ ] Resources appear in Panorama UI (if `apply` was run)

## Safe Testing Workflow

For testing without creating real resources:

1. **Local**: Use `terraform plan` only (never run `apply`)
2. **GitHub Actions**: Use manual trigger with `plan` action only
3. **Verify**: Check plan output matches expectations
4. **When ready**: Use `apply` to create resources
