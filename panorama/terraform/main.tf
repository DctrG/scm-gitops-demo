# Shared Panorama configuration for all Terraform-managed customers:
# one template (network config) and one parent device group (policy config).

resource "panos_template" "template" {
  location = {
    panorama = {}
  }

  name         = local.global_config.template
  description  = "Template for Terraform-managed PANW customer VPNs"
  default_vsys = "vsys1"
}

resource "panos_device_group" "parent" {
  location = {
    panorama = {}
  }

  name        = local.global_config.parent_device_group
  description = "Parent device group for Terraform-managed PANW customer VPNs"
  templates   = [panos_template.template.name]
}

# Physical interface used as the IKE gateway local interface
resource "panos_ethernet_interface" "local_interface" {
  location = {
    template = {
      name = panos_template.template.name
      vsys = "vsys1"
    }
  }

  name   = local.global_config.local_interface
  layer3 = {}
}

resource "panos_virtual_router" "vr" {
  location = {
    template = {
      name = panos_template.template.name
    }
  }

  name = local.global_config.virtual_router

  # Interface membership is owned by panos_virtual_router_interface resources,
  # and the provider computes location.vsys after apply which would otherwise
  # force replacement on every plan.
  lifecycle {
    ignore_changes = [interfaces, location]
  }
}

# Interface memberships are managed with panos_virtual_router_interface
# (here and in the customer module) so customers can attach their tunnel
# interfaces without fighting over the virtual router resource.
resource "panos_virtual_router_interface" "local_interface" {
  location = {
    template = {
      name = panos_template.template.name
    }
  }

  virtual_router = panos_virtual_router.vr.name
  interface      = panos_ethernet_interface.local_interface.name
}

# Shared crypto profiles
resource "panos_ike_crypto_profile" "ike_profile" {
  location = {
    template = {
      name = panos_template.template.name
    }
  }

  name       = local.global_config.ike_profile
  hash       = ["sha256"]
  dh_group   = ["group14"]
  encryption = ["aes-256-cbc"]

  lifetime = {
    hours = 8
  }
}

resource "panos_ipsec_crypto_profile" "ipsec_profile" {
  location = {
    template = {
      name = panos_template.template.name
    }
  }

  name     = local.global_config.ipsec_profile
  dh_group = "group14"

  esp = {
    encryption     = ["aes-256-cbc"]
    authentication = ["sha256"]
  }

  lifetime = {
    hours = 1
  }
}

# Per-customer device group, tunnel, zone, IKE gateway, IPsec tunnel and policy
module "customers" {
  source = "./modules/customer"

  for_each = {
    for idx, customer in local.customers : customer.device_group => customer
  }

  customer_config = each.value
  global_config   = local.global_config

  depends_on = [
    panos_template.template,
    panos_device_group.parent,
    panos_ethernet_interface.local_interface,
    panos_virtual_router.vr,
    panos_ike_crypto_profile.ike_profile,
    panos_ipsec_crypto_profile.ipsec_profile,
  ]
}

# Commit the candidate configuration to Panorama after every change
resource "null_resource" "panorama_commit" {
  triggers = {
    config_hash = sha256(file(var.customers_file))
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      HOST="${var.panorama_hostname}"
      KEY="${var.panorama_api_key}"
      if [ -z "$HOST" ]; then HOST="$PANOS_HOSTNAME"; fi
      if [ -z "$KEY" ]; then KEY="$PANOS_API_KEY"; fi

      if [ -z "$HOST" ] || [ -z "$KEY" ]; then
        echo "Error: Missing Panorama credentials (panorama_hostname/panorama_api_key or PANOS_HOSTNAME/PANOS_API_KEY)"
        exit 1
      fi

      echo "Committing candidate configuration to Panorama..."
      RESPONSE=$(curl -sk -G "https://$HOST/api/" \
        --data-urlencode "type=commit" \
        --data-urlencode "cmd=<commit><description>Terraform GitOps VPN automation</description></commit>" \
        -H "X-PAN-KEY: $KEY")

      JOB_ID=$(echo "$RESPONSE" | sed -n 's:.*<job>\(.*\)</job>.*:\1:p')
      if [ -z "$JOB_ID" ]; then
        if echo "$RESPONSE" | grep -q "no changes"; then
          echo "No changes to commit."
          exit 0
        fi
        echo "Error: Commit did not start a job. Response: $RESPONSE"
        exit 1
      fi

      echo "Commit job $JOB_ID started, waiting for completion..."
      ATTEMPT=0
      while [ $ATTEMPT -lt 90 ]; do
        ATTEMPT=$((ATTEMPT + 1))
        sleep 5
        JOB=$(curl -sk -G "https://$HOST/api/" \
          --data-urlencode "type=op" \
          --data-urlencode "cmd=<show><jobs><id>$JOB_ID</id></jobs></show>" \
          -H "X-PAN-KEY: $KEY")
        STATUS=$(echo "$JOB" | sed -n 's:.*<status>\(.*\)</status>.*:\1:p')
        if [ "$STATUS" = "FIN" ]; then
          RESULT=$(echo "$JOB" | sed -n 's:.*<result>\(.*\)</result>.*:\1:p' | head -1)
          if [ "$RESULT" = "OK" ]; then
            echo "Commit job $JOB_ID completed successfully."
            exit 0
          fi
          echo "Error: Commit job $JOB_ID finished with result $RESULT"
          echo "$JOB"
          exit 1
        fi
        echo "  Commit in progress... (attempt $ATTEMPT/90)"
      done

      echo "Error: Commit job $JOB_ID did not finish in time"
      exit 1
    EOT
  }

  depends_on = [module.customers]
}
