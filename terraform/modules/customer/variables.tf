variable "customer_config" {
  description = "Customer configuration"
  type = object({
    customer_name           = string
    device_group            = string
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
    template            = string
    parent_device_group = string
    panw_network        = string
    panw_network_object = string
    to_zone             = string
    ike_profile         = string
    ipsec_profile       = string
    local_interface     = string
    virtual_router      = string
  })
}
