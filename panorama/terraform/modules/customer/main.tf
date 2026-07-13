# Customer device group (policy container), nested under the parent device group
resource "panos_device_group" "customer" {
  location = {
    panorama = {}
  }

  name        = var.customer_config.device_group
  description = "Device group for ${var.customer_config.customer_name} VPN configuration"
}

resource "panos_device_group_parent" "customer" {
  location = {
    panorama = {}
  }

  device_group = panos_device_group.customer.name
  parent       = var.global_config.parent_device_group
}

# Tunnel interface (template)
resource "panos_tunnel_interface" "customer_tunnel" {
  location = {
    template = {
      name = var.global_config.template
      vsys = "vsys1"
    }
  }

  name    = "tunnel.${var.customer_config.tunnel_number}"
  comment = "${var.customer_config.customer_name}-Interface"
}

resource "panos_virtual_router_interface" "customer_tunnel" {
  location = {
    template = {
      name = var.global_config.template
    }
  }

  virtual_router = var.global_config.virtual_router
  interface      = panos_tunnel_interface.customer_tunnel.name
}

# Zone (template, vsys1)
resource "panos_zone" "customer_zone" {
  location = {
    template = {
      name = var.global_config.template
      vsys = "vsys1"
    }
  }

  name = var.customer_config.zone_name

  network = {
    layer3 = [panos_tunnel_interface.customer_tunnel.name]
  }
}

# IKE gateway (template)
resource "panos_ike_gateway" "ike_gateway" {
  location = {
    template = {
      name = var.global_config.template
    }
  }

  name = var.customer_config.ike_gateway_name

  authentication = {
    pre_shared_key = {
      key = var.customer_config.psk
    }
  }

  peer_address = {
    ip = var.customer_config.peer_ip
  }

  local_address = {
    interface = var.global_config.local_interface
  }

  protocol = {
    version = "ikev2"
    ikev2 = {
      ike_crypto_profile = var.global_config.ike_profile
      dpd = {
        enable = true
      }
    }
  }

  protocol_common = {
    nat_traversal = {
      enable = true
    }
    fragmentation = {
      enable = false
    }
  }
}

# IPsec tunnel (template)
resource "panos_ipsec_tunnel" "ipsec_tunnel" {
  location = {
    template = {
      name = var.global_config.template
    }
  }

  name             = var.customer_config.ipsec_tunnel_name
  tunnel_interface = panos_tunnel_interface.customer_tunnel.name

  auto_key = {
    ike_gateway = [{
      name = panos_ike_gateway.ike_gateway.name
    }]
    ipsec_crypto_profile = var.global_config.ipsec_profile
  }
}

# Address objects (device group)
resource "panos_address" "customer_net" {
  location = {
    device_group = {
      name = panos_device_group.customer.name
    }
  }

  name       = var.customer_config.customer_network_object
  ip_netmask = var.customer_config.customer_network
}

resource "panos_address" "panw_net" {
  location = {
    device_group = {
      name = panos_device_group.customer.name
    }
  }

  name       = var.global_config.panw_network_object
  ip_netmask = var.global_config.panw_network
}

# Security policy (device group pre-rulebase)
resource "panos_security_policy" "customer_policy" {
  location = {
    device_group = {
      name     = panos_device_group.customer.name
      rulebase = "pre-rulebase"
    }
  }

  rules = [
    {
      name                  = var.customer_config.security_rule_name
      source_zones          = [panos_zone.customer_zone.name]
      destination_zones     = [var.global_config.to_zone]
      source_addresses      = [panos_address.customer_net.name]
      destination_addresses = [panos_address.panw_net.name]
      source_users          = ["any"]
      applications          = ["any"]
      services              = ["any"]
      category              = ["any"]
      action                = "allow"
    }
  ]
}
