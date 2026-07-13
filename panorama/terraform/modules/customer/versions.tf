terraform {
  required_version = ">= 1.8"

  required_providers {
    panos = {
      source  = "PaloAltoNetworks/panos"
      version = "~> 2.0"
    }
  }
}
