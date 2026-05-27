# Testing Guide

This guide explains how to test the Terraform deployment locally and via GitHub Actions.

## Local Testing

### Prerequisites
1. Terraform >= 1.0 installed
2. Python 3 (for YAML validation)
3. API credentials set up (via `.env` file or environment variables)

### Step-by-Step Testing

#### 1. Validate YAML Configuration
```bash
cd terraform
python3 -c "import yaml; yaml.safe_load(open('../customers-terraform.yaml')); print('✓ customers-terraform.yaml is valid')"
```

#### 2. Set Up Credentials
**Option A: Load from .env file** (recommended for local testing)
```bash
cd ..  # Go to project root
source .env
export SCM_CLIENT_ID="$PANW_CLIENT_ID"
export SCM_CLIENT_SECRET="$PANW_CLIENT_SECRET"
export SCM_SCOPE="tsg_id:$PANW_TSG_ID"
export SCM_TSG_ID="$PANW_TSG_ID"
cd terraform
```

**Option B: Set environment variables directly**
```bash
export SCM_CLIENT_ID="your-client-id"
export SCM_CLIENT_SECRET="your-client-secret"
export SCM_SCOPE="tsg_id:your-tsg-id"
export SCM_TSG_ID="your-tsg-id"
```

#### 3. Initialize Terraform
```bash
terraform init
```
Expected: "Terraform has been successfully initialized!"

#### 4. Validate Terraform Configuration
```bash
terraform validate
```
Expected: "Success! The configuration is valid."

#### 5. Plan Deployment (Dry-Run)
```bash
terraform plan -var="panw_tsg_id=$SCM_TSG_ID"
```
This shows what resources would be created without actually creating them.

#### 6. Apply Deployment (Optional - Creates Real Resources)
⚠️ **Warning**: This will create actual resources in Strata Cloud Manager!
```bash
terraform apply -var="panw_tsg_id=$SCM_TSG_ID"
```

#### 7. Verify Resources Were Created
Check the Strata Cloud Manager UI or use Terraform state:
```bash
terraform show
```

#### 8. Destroy Resources (Cleanup)
⚠️ **Warning**: This will delete all resources!
```bash
terraform destroy -var="panw_tsg_id=$SCM_TSG_ID"
```

## GitHub Actions Testing

### Prerequisites
1. GitHub repository with secrets configured:
   - `PANW_CLIENT_ID`
   - `PANW_CLIENT_SECRET`
   - `PANW_TSG_ID`

### Testing Methods

#### Method 1: Manual Workflow Trigger (Recommended for Testing)
1. Go to your GitHub repository
2. Navigate to **Actions** tab
3. Select **"Deploy Multi-Customer VPN (Terraform)"** workflow
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

3. **Download artifacts** (if workflow completed):
   - `terraform-plan` - Terraform plan output
   - `terraform-logs` - Any log files

4. **Verify in Strata Cloud Manager**:
   - Log into Strata Cloud Manager UI
   - Check that resources were created as expected

## Troubleshooting

### Local Testing Issues

**Error: "Provider parameter value error: Scope must be specified"**
- Solution: Ensure `SCM_SCOPE` is set to `tsg_id:<your-tsg-id>`
- Or pass `-var="panw_tsg_id=your-tsg-id"` to terraform commands

**Error: "Refresh JWT Authentication error"**
- Solution: Check that `SCM_CLIENT_ID`, `SCM_CLIENT_SECRET`, and `SCM_TSG_ID` are correctly set
- Verify credentials are valid in Strata Cloud Manager

**Error: "YAML validation failed"**
- Solution: Check `customers-terraform.yaml` syntax
- Use a YAML validator or Python: `python3 -c "import yaml; yaml.safe_load(open('../customers-terraform.yaml'))"`

### GitHub Actions Issues

**Workflow fails at "Terraform Init"**
- Check that GitHub Secrets are correctly configured
- Verify secret names match: `PANW_CLIENT_ID`, `PANW_CLIENT_SECRET`, `PANW_TSG_ID`

**Workflow fails at "Terraform Plan"**
- Check workflow logs for specific error messages
- Verify `customers-terraform.yaml` is valid
- Ensure credentials have proper permissions

**Workflow succeeds but resources not created**
- Check if `terraform apply` step actually ran (only runs on manual "apply")
- Verify resources in Strata Cloud Manager UI
- Check Terraform state file (if using remote state)

## Quick Test Checklist

- [ ] YAML file validates successfully
- [ ] Terraform init completes without errors
- [ ] Terraform validate passes
- [ ] Terraform plan shows expected resources
- [ ] GitHub Actions workflow runs successfully (at least `plan` action)
- [ ] Resources appear in Strata Cloud Manager UI (if `apply` was run)

## Safe Testing Workflow

For testing without creating real resources:

1. **Local**: Use `terraform plan` only (never run `apply`)
2. **GitHub Actions**: Use manual trigger with `plan` action only
3. **Verify**: Check plan output matches expectations
4. **When ready**: Use `apply` to create resources
