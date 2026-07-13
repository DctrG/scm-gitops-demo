variable "panw_client_id" {
  description = "Palo Alto Networks OAuth2 Client ID (or use SCM_CLIENT_ID env var)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "panw_client_secret" {
  description = "Palo Alto Networks OAuth2 Client Secret (or use SCM_CLIENT_SECRET env var)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "panw_tsg_id" {
  description = "Palo Alto Networks Tenant Service Group ID (or use SCM_TSG_ID env var)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "customers_file" {
  description = "Path to customers YAML file"
  type        = string
  default     = "customers.yaml"
}
