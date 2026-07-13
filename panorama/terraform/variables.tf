variable "panorama_hostname" {
  description = "Panorama hostname or IP address (or use PANOS_HOSTNAME env var)"
  type        = string
  default     = ""
}

variable "panorama_api_key" {
  description = "Panorama XML API key (or use PANOS_API_KEY env var)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "customers_file" {
  description = "Path to customers YAML file"
  type        = string
  default     = "customers.yaml"
}
