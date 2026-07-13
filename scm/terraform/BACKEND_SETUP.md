# Terraform Remote State Setup

## Problem
Currently, Terraform uses local state files. In GitHub Actions, each workflow run starts fresh with no state, causing Terraform to think all resources need to be created, leading to conflicts with existing resources.

## Solution: Remote State Backend

You need to configure a remote backend to persist Terraform state between runs.

## Option 1: Terraform Cloud (Recommended)

Terraform Cloud offers a free tier and integrates well with GitHub Actions.

### Setup Steps:

1. **Create a Terraform Cloud account** (if you don't have one):
   - Go to https://app.terraform.io
   - Sign up for free

2. **Create an organization**:
   - Create or select an organization

3. **Create a workspace**:
   - Go to your organization
   - Click "New workspace"
   - Choose "API-driven workflow"
   - Name it: `panw-vpn-deployment`

4. **Get your organization name**:
   - It's shown in the URL: `https://app.terraform.io/app/YOUR-ORG-NAME/`

5. **Configure the backend**:
   - Edit `terraform/versions.tf`
   - Uncomment the `backend "remote"` block
   - Replace `your-org-name` with your actual organization name

6. **Add Terraform Cloud token to GitHub Secrets**:
   - In Terraform Cloud: Settings → Tokens → User Tokens → Generate
   - Copy the token
   - In GitHub: Repository → Settings → Secrets → Actions
   - Add secret: `TF_TOKEN_app_terraform_io` with your token value

7. **Update GitHub Actions workflow**:
   - The workflow will automatically use Terraform Cloud if the backend is configured

## Option 2: AWS S3 + DynamoDB

If you prefer AWS:

### Setup Steps:

1. **Create S3 bucket**:
   ```bash
   aws s3 mb s3://your-terraform-state-bucket
   aws s3api put-bucket-versioning \
     --bucket your-terraform-state-bucket \
     --versioning-configuration Status=Enabled
   ```

2. **Create DynamoDB table for locking**:
   ```bash
   aws dynamodb create-table \
     --table-name terraform-state-lock \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
   ```

3. **Configure backend**:
   - Edit `terraform/versions.tf`
   - Uncomment the `backend "s3"` block
   - Update bucket name, region, etc.

4. **Add AWS credentials to GitHub Secrets**:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

## Option 3: GitHub Actions Artifacts (Not Recommended)

This is a workaround but not ideal for production:

- State would be uploaded/downloaded as artifacts
- No state locking
- More complex workflow

## After Setup

Once you've configured a backend:

1. **Initialize Terraform**:
   ```bash
   cd terraform
   terraform init
   ```
   - This will migrate your local state to the remote backend

2. **Verify**:
   ```bash
   terraform state list
   ```
   - Should show your existing resources

3. **Push changes**:
   - Commit the backend configuration
   - Push to trigger GitHub Actions
   - The workflow will now use remote state

## Current State

Right now, Terraform state is stored locally in `terraform/terraform.tfstate`. This file is gitignored and won't be available in GitHub Actions, which is why each run thinks everything needs to be created.



