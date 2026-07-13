provider "scm" {
  # Strata Cloud Manager configuration
  # Authentication via OAuth2 Client Credentials
  #
  # Credentials can be provided via:
  # 1. Environment variables: SCM_CLIENT_ID, SCM_CLIENT_SECRET, and SCM_SCOPE="tsg_id:<TSG_ID>"
  # 2. terraform.tfvars file with panw_client_id, panw_client_secret, and panw_tsg_id variables
  #
  # SCM_TSG_ID is used by the folder propagation poller when credentials are supplied
  # through environment variables instead of terraform.tfvars.
  #
  # Scope is required and should be set to tsg_id:<TSG_ID>
  # Scope format: "tsg_id:<TSG_ID>"

  client_id     = var.panw_client_id != "" ? var.panw_client_id : null
  client_secret = var.panw_client_secret != "" ? var.panw_client_secret : null
  scope         = var.panw_tsg_id != "" ? "tsg_id:${var.panw_tsg_id}" : null
}

