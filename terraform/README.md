# Terraform Deployment for PANW Customer VPNs (Panorama)

This Terraform configuration deploys IPsec VPN connections for multiple customers to Palo Alto Networks Panorama using the [PaloAltoNetworks/panos](https://registry.terraform.io/providers/PaloAltoNetworks/panos/latest/docs) provider (v2).

## Layout on Panorama

- One template (`PANW-Terraform-Template`) holds shared network config: the local ethernet interface, virtual router, IKE/IPsec crypto profiles, plus per-customer tunnel interfaces, zones, IKE gateways and IPsec tunnels.
- One parent device group (`PANW-Terraform-Global`) with one nested device group per customer holding address objects and the security rule.
- A commit to Panorama runs automatically at the end of each apply.

## Prerequisites

1. **Terraform** >= 1.8 installed
2. **Panorama credentials**:
   - Hostname or IP address
   - XML API key

## Setup

1. **Install Terraform providers**:
   ```bash
   cd terraform
   terraform init
   ```

2. **Configure credentials** (choose one method):

   **Option A: Environment variables** (recommended)
   ```bash
   export PANOS_HOSTNAME="panorama.example.com"
   export PANOS_API_KEY="your-panorama-api-key"
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
├── versions.tf            # Terraform and provider versions (HCP Terraform cloud block)
├── provider.tf            # Provider configuration
├── variables.tf           # Input variables
├── data.tf                # Data sources (YAML loading)
├── main.tf                # Shared template, device group, profiles, commit
└── modules/
    └── customer/
        ├── variables.tf   # Customer module variables
        └── main.tf        # Customer resources
```

## Notes

- Uses the official [PaloAltoNetworks/panos](https://registry.terraform.io/providers/PaloAltoNetworks/panos/latest/docs) provider (v2, location-based resources)
- Terraform state is stored in HCP Terraform (see `versions.tf`); the workspace must use **Local** execution mode
- Authentication uses the Panorama XML API key
- Resource types: `panos_template`, `panos_device_group`, `panos_device_group_parent`, `panos_tunnel_interface`, `panos_zone`, `panos_ike_crypto_profile`, `panos_ipsec_crypto_profile`, `panos_ike_gateway`, `panos_ipsec_tunnel`, `panos_address`, `panos_security_policy`
