# Terraform Deployment for PANW Customer VPNs

This Terraform configuration deploys IPsec VPN connections for multiple customers to Palo Alto Networks Strata Cloud Manager using the [PaloAltoNetworks/scm](https://registry.terraform.io/providers/PaloAltoNetworks/scm/latest/docs) provider.

## Prerequisites

1. **Terraform** >= 1.0 installed
2. **Palo Alto Networks API credentials**:
   - Client ID
   - Client Secret
   - Tenant Service Group (TSG) ID

## Setup

1. **Install Terraform providers**:
   ```bash
   cd terraform
   terraform init
   ```

2. **Configure credentials** (choose one method):
   
   **Option A: Environment variables** (recommended)
   ```bash
   export SCM_CLIENT_ID="your-client-id"
   export SCM_CLIENT_SECRET="your-client-secret"
   export SCM_SCOPE="tsg_id:your-tsg-id"
   export SCM_TSG_ID="your-tsg-id" # used by the folder propagation poller
   ```
   
   **Option B: terraform.tfvars file** (create this file, don't commit it)
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your credentials
   ```

3. **Configure customers**:
   Edit `customers-terraform.yaml` to add/remove customers. Only customers with `enabled: true` (or not set) will be deployed.

## Usage

### Plan deployment
```bash
terraform plan
```

### Apply deployment
```bash
terraform apply
```

### Destroy resources
```bash
terraform destroy
```

### Remove a customer
Simply remove the customer from `customers-terraform.yaml` and run `terraform apply`. Terraform will automatically destroy the removed customer's resources.

## Customer Management

### Add a customer
1. Add customer entry to `customers-terraform.yaml`
2. Run `terraform plan` to preview changes
3. Run `terraform apply` to deploy

### Remove a customer
1. Remove customer entry from `customers-terraform.yaml`
2. Run `terraform plan` to preview deletion
3. Run `terraform apply` to remove resources

### Disable a customer (without deleting)
1. Set `enabled: false` in customer entry
2. Run `terraform apply` to remove resources but keep config

## File Structure

```
terraform/
├── ../customers-terraform.yaml # Single source of truth for Terraform customers
├── versions.tf            # Terraform and provider versions
├── provider.tf            # Provider configuration
├── variables.tf           # Input variables
├── data.tf                # Data sources (YAML loading)
├── main.tf                # Main resources
├── outputs.tf             # Output values
└── modules/
    └── customer/
        ├── variables.tf   # Customer module variables
        └── main.tf        # Customer resources
```

## Notes

- Uses the official [PaloAltoNetworks/scm](https://registry.terraform.io/providers/PaloAltoNetworks/scm/latest/docs) provider for Strata Cloud Manager
- Terraform state is stored locally by default (consider using remote state for team collaboration)
- The provider supports OAuth2 Client Credentials authentication
- All resources are scoped to folders for proper organization

## Provider Documentation

For detailed resource documentation, see:
- [SCM Provider Documentation](https://registry.terraform.io/providers/PaloAltoNetworks/scm/latest/docs)
- Resource types: `scm_folder`, `scm_zone`, `scm_tunnel_interface`, `scm_ike_crypto_profile`, `scm_ipsec_crypto_profile`, `scm_ike_gateway`, `scm_ipsec_tunnel`, `scm_address_object`, `scm_security_rule`

