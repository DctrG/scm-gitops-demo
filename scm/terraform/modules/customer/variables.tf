variable "customer_config" {
  description = "Customer configuration"
  type = object({
    customer_name           = string
    folder_name             = string
    customer_network        = string
    customer_network_object = string
    peer_ip                 = string
    psk                     = string
    tunnel_number           = number
    zone_name               = string
    ike_gateway_name        = string
    ipsec_tunnel_name       = string
    security_rule_name      = string
    enabled                 = optional(bool, true)
  })
}

variable "global_config" {
  description = "Global configuration"
  type = object({
    root_folder         = string
    panw_network        = string
    panw_network_object = string
    to_zone             = string
    ike_profile         = string
    ipsec_profile       = string
    local_interface     = string
  })
}

variable "root_folder_id" {
  description = "Root folder ID"
  type        = string
}

variable "scm_client_id" {
  description = "SCM Client ID for API authentication"
  type        = string
  sensitive   = true
}

variable "scm_client_secret" {
  description = "SCM Client Secret for API authentication"
  type        = string
  sensitive   = true
}

variable "scm_tsg_id" {
  description = "SCM Tenant Service Group ID"
  type        = string
  sensitive   = true
}

