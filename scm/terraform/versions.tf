terraform {
  required_version = ">= 1.0"

  cloud {
    organization = "panw-gitops"

    workspaces {
      name = "panw-gitops-dev"
    }
  }

  required_providers {
    scm = {
      source  = "PaloAltoNetworks/scm"
      version = "= 1.0.6"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
    # Required while existing state still contains the previous time_sleep propagation waiter.
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
  }
}

