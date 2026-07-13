# Root folder
resource "scm_folder" "root_folder" {
  name        = local.global_config.root_folder
  parent      = "ngfw-shared"
  description = "Root folder for Terraform-managed PANW customer VPNs"

  # The provider reports labels inconsistently ([] vs null), causing
  # spurious updates that fail with "inconsistent result after apply".
  lifecycle {
    ignore_changes = [labels]
  }
}

resource "null_resource" "root_folder_propagation" {
  depends_on = [scm_folder.root_folder]

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      CLIENT_ID="${var.panw_client_id}"
      CLIENT_SECRET="${var.panw_client_secret}"
      TSG_ID="${var.panw_tsg_id}"

      if [ -z "$CLIENT_ID" ]; then
        CLIENT_ID="$SCM_CLIENT_ID"
      fi
      if [ -z "$CLIENT_SECRET" ]; then
        CLIENT_SECRET="$SCM_CLIENT_SECRET"
      fi
      if [ -z "$TSG_ID" ]; then
        TSG_ID="$SCM_TSG_ID"
      fi

      if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ] || [ -z "$TSG_ID" ]; then
        echo "Error: Missing credentials (panw_client_id, panw_client_secret, or panw_tsg_id)"
        exit 1
      fi

      TOKEN=$(curl -s -X POST "https://auth.apps.paloaltonetworks.com/oauth2/access_token" \
        -u "$CLIENT_ID:$CLIENT_SECRET" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-urlencode "grant_type=client_credentials" \
        --data-urlencode "scope=tsg_id:$TSG_ID" | \
        python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")

      if [ -z "$TOKEN" ]; then
        echo "Error: Failed to get authentication token"
        exit 1
      fi

      FOLDER_NAME="${scm_folder.root_folder.name}"
      API_URL="https://api.strata.paloaltonetworks.com/config/setup/v1/folders"
      MAX_ATTEMPTS=30
      ATTEMPT=0
      SLEEP_INTERVAL=2

      echo "Polling for root folder '$FOLDER_NAME' to be available..."

      while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        ATTEMPT=$((ATTEMPT + 1))
        RESPONSE=$(curl -s -X GET "$API_URL" \
          -H "Authorization: Bearer $TOKEN" \
          -H "Accept: application/json")

        FOLDER_EXISTS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for folder in data.get('data', []):
        if folder.get('name') == '$FOLDER_NAME':
            print('true')
            sys.exit(0)
    print('false')
except Exception:
    print('false')
")

        if [ "$FOLDER_EXISTS" = "true" ]; then
          echo "✓ Root folder '$FOLDER_NAME' is now available (attempt $ATTEMPT/$MAX_ATTEMPTS)"
          exit 0
        fi

        if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
          echo "  Root folder not yet available, waiting $SLEEP_INTERVAL seconds... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
          sleep $SLEEP_INTERVAL
        fi
      done

      echo "Error: Root folder '$FOLDER_NAME' did not become available after $MAX_ATTEMPTS attempts"
      exit 1
    EOT
  }

  triggers = {
    folder_id = scm_folder.root_folder.id
  }
}

# Note: Physical interfaces like ethernet1/1 are device-level hardware interfaces
# that already exist on the firewall. They cannot be created via Terraform.
# We reference them by name - they must exist at the device/parent folder level.
# The interface name format should be "$ethernet1/1" (with $ prefix) for SCM API.

# Customer folders and resources
module "customers" {
  source = "./modules/customer"

  for_each = {
    for idx, customer in local.customers : customer.folder_name => customer
  }

  customer_config = each.value
  global_config   = local.global_config
  root_folder_id  = scm_folder.root_folder.name # Use folder name instead of ID
  # Credentials: prefer environment variables, fallback to variables
  scm_client_id     = var.panw_client_id != "" ? var.panw_client_id : ""
  scm_client_secret = var.panw_client_secret != "" ? var.panw_client_secret : ""
  scm_tsg_id        = var.panw_tsg_id != "" ? var.panw_tsg_id : ""

  depends_on = [null_resource.root_folder_propagation]
}

