# Load customers from YAML file
locals {
  customers_data = yamldecode(file(var.customers_file))
  global_config  = local.customers_data.global
  customers      = [for c in coalesce(try(local.customers_data.customers, []), []) : c if lookup(c, "enabled", true) != false]
}



