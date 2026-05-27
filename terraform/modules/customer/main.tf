# Customer folder
resource "scm_folder" "customer_folder" {
  name        = var.customer_config.folder_name
  parent      = var.root_folder_id
  description = "" # Explicitly set to empty string to avoid provider inconsistency
}

# Poll for folder propagation in SCM API
resource "null_resource" "folder_propagation" {
  depends_on = [scm_folder.customer_folder]

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      
      # Get authentication token (prefer Terraform variables, fallback to environment variables)
      CLIENT_ID="${var.scm_client_id}"
      CLIENT_SECRET="${var.scm_client_secret}"
      TSG_ID="${var.scm_tsg_id}"
      
      # Use environment variables if Terraform variables are empty
      if [ -z "$CLIENT_ID" ] || [ "$CLIENT_ID" = "" ]; then
        CLIENT_ID="$SCM_CLIENT_ID"
      fi
      if [ -z "$CLIENT_SECRET" ] || [ "$CLIENT_SECRET" = "" ]; then
        CLIENT_SECRET="$SCM_CLIENT_SECRET"
      fi
      if [ -z "$TSG_ID" ] || [ "$TSG_ID" = "" ]; then
        TSG_ID="$SCM_TSG_ID"
      fi
      
      if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ] || [ -z "$TSG_ID" ]; then
        echo "Error: Missing credentials (CLIENT_ID, CLIENT_SECRET, or TSG_ID)"
        exit 1
      fi
      
      AUTH_URL="https://auth.apps.paloaltonetworks.com/oauth2/access_token"
      
      TOKEN=$(curl -s -X POST "$AUTH_URL" \
        -u "$CLIENT_ID:$CLIENT_SECRET" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-urlencode "grant_type=client_credentials" \
        --data-urlencode "scope=tsg_id:$TSG_ID" | \
        python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")
      
      if [ -z "$TOKEN" ]; then
        echo "Error: Failed to get authentication token"
        exit 1
      fi
      
      # Poll for folder existence
      FOLDER_NAME="${scm_folder.customer_folder.name}"
      PARENT_NAME="${var.root_folder_id}"
      API_URL="https://api.strata.paloaltonetworks.com/config/setup/v1/folders"
      
      MAX_ATTEMPTS=30
      ATTEMPT=0
      SLEEP_INTERVAL=2
      
      echo "Polling for folder '$FOLDER_NAME' to be available..."
      
      while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        ATTEMPT=$((ATTEMPT + 1))
        
        # Get all folders and check if our folder exists
        RESPONSE=$(curl -s -X GET "$API_URL" \
          -H "Authorization: Bearer $TOKEN" \
          -H "Accept: application/json")
        
        # Check if folder exists (by name and parent)
        FOLDER_EXISTS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    folders = data.get('data', [])
    for folder in folders:
        folder_name = folder.get('name', '')
        parent = folder.get('parent', '') or folder.get('parent_id', '')
        if folder_name == '$FOLDER_NAME' and ('$PARENT_NAME' in str(parent) or parent == '$PARENT_NAME'):
            print('true')
            sys.exit(0)
    print('false')
except Exception as e:
    print('false')
")
        
        if [ "$FOLDER_EXISTS" = "true" ]; then
          echo "✓ Folder '$FOLDER_NAME' is now available (attempt $ATTEMPT/$MAX_ATTEMPTS)"
          exit 0
        fi
        
        if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
          echo "  Folder not yet available, waiting $SLEEP_INTERVAL seconds... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
          sleep $SLEEP_INTERVAL
        fi
      done
      
      echo "Error: Folder '$FOLDER_NAME' did not become available after $MAX_ATTEMPTS attempts"
      exit 1
    EOT

  }

  triggers = {
    folder_id = scm_folder.customer_folder.id
  }
}

# Zone
resource "scm_zone" "customer_zone" {
  name   = var.customer_config.zone_name
  folder = scm_folder.customer_folder.name # Use folder name instead of ID to avoid propagation issues

  network = {
    layer3 = []
  }

  depends_on = [null_resource.folder_propagation]
}

# Note: Physical interfaces like ethernet1/1 are device-level resources
# and exist at a higher folder level (e.g., "PANW Global" or device level).
# We reference them by name without creating them.

# Ethernet interface (for IKE gateway local address)
# Created at customer folder level - if it already exists, Terraform will handle it
resource "scm_ethernet_interface" "local_interface" {
  name          = var.global_config.local_interface                   # "$ethernet1-1"
  default_value = replace(var.global_config.local_interface, "$", "") # "ethernet1-1"
  folder        = scm_folder.customer_folder.name

  # Layer3 interface for IKE gateway
  layer3 = {
    # Minimal layer3 config - interface will be used for IKE gateway local address
  }

  depends_on = [null_resource.folder_propagation]

  # If interface already exists, this will fail - user should delete it from UI first
  # or we can import it: terraform import 'module.customers["PANW-Customer-CD"].scm_ethernet_interface.local_interface' '<TFID>'
}

# Tunnel interface
resource "scm_tunnel_interface" "customer_tunnel" {
  name          = "$tunnel-${var.customer_config.tunnel_number}"
  default_value = "tunnel.${var.customer_config.tunnel_number}"
  comment       = "${var.customer_config.customer_name}-Interface"
  folder        = scm_folder.customer_folder.name # Use folder name instead of ID

  depends_on = [null_resource.folder_propagation]
}

# IKE crypto profile
resource "scm_ike_crypto_profile" "ike_profile" {
  name       = var.global_config.ike_profile
  folder     = scm_folder.customer_folder.name # Use folder name instead of ID
  dh_group   = ["group14"]
  encryption = ["aes-256-cbc"]
  hash       = ["sha256"]
  lifetime = {
    seconds = 28800
  }

  depends_on = [null_resource.folder_propagation]
}

# IPsec crypto profile
resource "scm_ipsec_crypto_profile" "ipsec_profile" {
  name     = var.global_config.ipsec_profile
  folder   = scm_folder.customer_folder.name # Use folder name instead of ID
  dh_group = "group14"
  esp = {
    encryption     = ["aes-256-cbc"]
    authentication = ["sha256"]
  }
  lifetime = {
    seconds = 3600
  }

  depends_on = [null_resource.folder_propagation]
}

# IKE gateway
resource "scm_ike_gateway" "ike_gateway" {
  name   = var.customer_config.ike_gateway_name
  folder = scm_folder.customer_folder.name # Use folder name instead of ID
  protocol = {
    version = "ikev2"
    ikev2 = {
      ike_crypto_profile = scm_ike_crypto_profile.ike_profile.name
    }
  }
  peer_address = {
    ip = var.customer_config.peer_ip
  }
  authentication = {
    pre_shared_key = {
      key = var.customer_config.psk
    }
  }
  # Reference the interface created in this customer folder
  local_address = {
    interface = scm_ethernet_interface.local_interface.name
  }
  protocol_common = {
    fragmentation = {
      enable = false
    }
    nat_traversal = {
      enable = true
    }
    passive_mode = false
  }

  depends_on = [
    null_resource.folder_propagation,
    scm_ike_crypto_profile.ike_profile,
    scm_ethernet_interface.local_interface
  ]

}

# IPsec tunnel
resource "scm_ipsec_tunnel" "ipsec_tunnel" {
  name             = var.customer_config.ipsec_tunnel_name
  folder           = scm_folder.customer_folder.name # Use folder name instead of ID
  tunnel_interface = scm_tunnel_interface.customer_tunnel.name
  auto_key = {
    ike_gateway = [{
      name = scm_ike_gateway.ike_gateway.name
    }]
    ipsec_crypto_profile = scm_ipsec_crypto_profile.ipsec_profile.name
  }

  depends_on = [
    null_resource.folder_propagation,
    scm_tunnel_interface.customer_tunnel,
    scm_ike_gateway.ike_gateway,
    scm_ipsec_crypto_profile.ipsec_profile
  ]
}

# Address objects
resource "scm_address" "customer_net" {
  name       = var.customer_config.customer_network_object
  folder     = scm_folder.customer_folder.name # Use folder name instead of ID
  ip_netmask = var.customer_config.customer_network

  depends_on = [null_resource.folder_propagation]
}

resource "scm_address" "panw_net" {
  name       = var.global_config.panw_network_object
  folder     = scm_folder.customer_folder.name # Use folder name instead of ID
  ip_netmask = var.global_config.panw_network

  depends_on = [null_resource.folder_propagation]
}

# Security rule
resource "scm_security_rule" "security_rule" {
  name        = var.customer_config.security_rule_name
  folder      = scm_folder.customer_folder.name # Use folder name instead of ID
  from        = [scm_zone.customer_zone.name]
  to          = [var.global_config.to_zone]
  source      = [scm_address.customer_net.name]
  destination = [scm_address.panw_net.name]
  application = ["any"]
  service     = ["any"]
  category    = ["any"]
  source_user = ["any"]
  action      = "allow"

  depends_on = [
    scm_folder.customer_folder,
    scm_zone.customer_zone,
    scm_address.customer_net,
    scm_address.panw_net
  ]
}

