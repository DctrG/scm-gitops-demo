provider "panos" {
  # Panorama configuration (PAN-OS XML API)
  #
  # Credentials can be provided via:
  # 1. Environment variables: PANOS_HOSTNAME and PANOS_API_KEY
  # 2. terraform.tfvars file with panorama_hostname and panorama_api_key variables

  hostname = var.panorama_hostname != "" ? var.panorama_hostname : null
  api_key  = var.panorama_api_key != "" ? var.panorama_api_key : null

  # Demo Panorama instances typically use self-signed certificates
  skip_verify_certificate = true
}
