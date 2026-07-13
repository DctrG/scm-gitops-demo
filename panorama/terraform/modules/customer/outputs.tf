output "customer_name" {
  description = "Customer name"
  value       = var.customer_config.customer_name
}

output "device_group" {
  description = "Device group name"
  value       = var.customer_config.device_group
}

output "zone_name" {
  description = "Zone name"
  value       = var.customer_config.zone_name
}

output "tunnel_name" {
  description = "IPsec tunnel name"
  value       = var.customer_config.ipsec_tunnel_name
}
