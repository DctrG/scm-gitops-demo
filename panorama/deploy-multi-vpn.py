#!/usr/bin/env python3
"""
Panorama (PAN-OS XML API) - Multi-Customer VPN Deployment Script

Reads customer configurations from customers-to-add.yaml and creates IPsec VPN
connections for each customer:

  - Shared config (template, ethernet interface, IKE/IPsec crypto profiles)
    lives in one Panorama template.
  - Per-customer config: tunnel interface, zone, IKE gateway and IPsec tunnel
    in the template; address objects and a security rule in a per-customer
    device group nested under a parent device group.

Requirements:
  pip install requests pyyaml python-dotenv

Usage:
  python deploy-multi-vpn.py
"""

from __future__ import annotations

import os
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3
import yaml

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Panorama demo instances typically use self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Disable proxy inheritance from environment
for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(proxy_var, None)

_session = requests.Session()
_session.trust_env = False
_session.proxies = {}
_session.verify = False


# -----------------------------
# Configuration
# -----------------------------
PANORAMA_HOST = os.environ.get("PANORAMA_HOST")
PANORAMA_API_KEY = os.environ.get("PANORAMA_API_KEY")

LOCALHOST = "/config/devices/entry[@name='localhost.localdomain']"


# -----------------------------
# XML API helpers
# -----------------------------
class ApiError(RuntimeError):
    pass


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def api_request(params: Dict[str, str], ignore_errors: bool = False) -> Optional[ET.Element]:
    """Send a request to the Panorama XML API and return the parsed response root."""
    url = f"https://{PANORAMA_HOST}/api/"
    r = _session.get(url, params=params, headers={"X-PAN-KEY": PANORAMA_API_KEY}, timeout=120)
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        raise ApiError(f"Invalid XML response from Panorama: {e}: {r.text[:500]}")

    if root.get("status") != "success":
        if ignore_errors:
            return None
        msg = root.findtext(".//msg") or ET.tostring(root, encoding="unicode")
        # <msg><line>...</line></msg> style errors
        lines = [el.text for el in root.findall(".//msg/line") if el.text]
        if lines:
            msg = "; ".join(lines)
        raise ApiError(f"Panorama API error (code={root.get('code')}): {msg}")
    return root


def config_get(xpath: str) -> Optional[ET.Element]:
    """Get a config node. Returns the <result> element, or None if empty."""
    root = api_request({"type": "config", "action": "get", "xpath": xpath})
    result = root.find("result")
    if result is None:
        return None
    if result.get("total-count") == "0":
        return None
    if len(list(result)) == 0 and not (result.text or "").strip():
        return None
    return result


def config_set(xpath: str, element: str) -> None:
    api_request({"type": "config", "action": "set", "xpath": xpath, "element": element})


def config_delete(xpath: str) -> bool:
    """Delete a config node. Returns False if it did not exist."""
    root = api_request({"type": "config", "action": "delete", "xpath": xpath}, ignore_errors=True)
    return root is not None


def ensure(xpath: str, element: str, resource_type: str, name: str) -> None:
    """Create a config node if it does not already exist (idempotent)."""
    if config_get(xpath) is not None:
        print(f"  → {resource_type} '{name}' already exists")
        return
    config_set(xpath, element)
    print(f"  ✓ Created {resource_type.lower()} '{name}' successfully")


def commit(description: str) -> None:
    """Commit candidate configuration to Panorama and wait for the job to finish."""
    print(f"\n{'='*70}")
    print("Committing configuration to Panorama...")
    print(f"{'='*70}")
    root = api_request({
        "type": "commit",
        "cmd": f"<commit><description>{description}</description></commit>",
    })
    job_id = root.findtext(".//job")
    if not job_id:
        msg = root.findtext(".//msg") or ""
        print(f"  → No commit job started ({msg or 'no changes to commit'})")
        return

    print(f"  → Commit job {job_id} started, waiting for completion...")
    for _ in range(90):
        time.sleep(5)
        jr = api_request({"type": "op", "cmd": f"<show><jobs><id>{job_id}</id></jobs></show>"})
        status = jr.findtext(".//job/status")
        progress = jr.findtext(".//job/progress")
        if status == "FIN":
            result = jr.findtext(".//job/result")
            if result == "OK":
                print(f"  ✓ Commit job {job_id} completed successfully")
                return
            details = "; ".join(el.text for el in jr.findall(".//details/line") if el.text)
            raise ApiError(f"Commit job {job_id} finished with result {result}: {details}")
        print(f"    Commit in progress... ({progress}%)")
    raise ApiError(f"Commit job {job_id} did not finish in time")


# -----------------------------
# XPath builders
# -----------------------------
def dg_xpath(device_group: str) -> str:
    return f"{LOCALHOST}/device-group/entry[@name='{device_group}']"


def template_xpath(template: str) -> str:
    return f"{LOCALHOST}/template/entry[@name='{template}']"


def tpl_vsys_xpath(template: str) -> str:
    return f"{template_xpath(template)}{LOCALHOST}/vsys/entry[@name='vsys1']"


def tpl_network_xpath(template: str) -> str:
    return f"{template_xpath(template)}{LOCALHOST}/network"


# -----------------------------
# YAML loading
# -----------------------------
def load_customers(yaml_file: str = "customers-to-add.yaml") -> Tuple[Dict[str, Any], list]:
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f) or {}
        global_config = data.get("global", {}) or {}
        customers = data.get("customers") or []
        if not isinstance(customers, list):
            customers = []
        return global_config, customers
    except FileNotFoundError:
        die(f"Configuration file '{yaml_file}' not found")
    except yaml.YAMLError as e:
        die(f"Error parsing YAML file: {e}")


def load_device_groups_to_delete(yaml_file: str = "customers-to-delete.yaml") -> list:
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f) or {}
        device_groups = data.get("device_groups_to_delete", [])
        return device_groups if isinstance(device_groups, list) else []
    except FileNotFoundError:
        return []
    except yaml.YAMLError as e:
        print(f"  ⚠ Warning: Error parsing '{yaml_file}': {e}", file=sys.stderr)
        return []


# -----------------------------
# Device group hierarchy
# -----------------------------
def get_dg_parent(device_group: str) -> Optional[str]:
    """Return the parent device group name from the dg-hierarchy, or None."""
    root = api_request({"type": "op", "cmd": "<show><dg-hierarchy/></show>"})

    def walk(element: ET.Element, parent_name: Optional[str]) -> Optional[str]:
        for child in element.findall("dg"):
            if child.get("name") == device_group:
                return parent_name
            found = walk(child, child.get("name"))
            if found is not None:
                return found
        return None

    hierarchy = root.find(".//dg-hierarchy")
    if hierarchy is None:
        return None
    return walk(hierarchy, None)


def ensure_dg_parent(device_group: str, parent: str) -> None:
    current = get_dg_parent(device_group)
    if current == parent:
        print(f"  → Device group '{device_group}' already nested under '{parent}'")
        return
    api_request({
        "type": "op",
        "cmd": f"<request><move-dg><entry name='{device_group}'><new-parent-dg>{parent}</new-parent-dg></entry></move-dg></request>",
    })
    print(f"  ✓ Moved device group '{device_group}' under '{parent}'")


def list_customer_device_groups(prefix: str) -> List[str]:
    """List all device groups whose name starts with the given prefix."""
    result = config_get(f"{LOCALHOST}/device-group")
    if result is None:
        return []
    names = []
    for entry in result.findall(".//device-group/entry"):
        name = entry.get("name")
        if name and name.startswith(prefix):
            names.append(name)
    return names


# -----------------------------
# Shared (global) configuration
# -----------------------------
def deploy_shared_config(global_config: Dict[str, Any]) -> None:
    template = global_config["template"]
    parent_dg = global_config["parent_device_group"]
    local_interface = global_config.get("local_interface", "ethernet1/1")
    virtual_router = global_config.get("virtual_router", "default")
    ike_profile = global_config.get("ike_profile", "PANW-Python-IKEv2-Standard")
    ipsec_profile = global_config.get("ipsec_profile", "PANW-Python-IPsec-Standard")

    print(f"\n[Step 0] Creating shared Panorama configuration...")

    # Template with a default vsys
    ensure(
        template_xpath(template),
        "<settings><default-vsys>vsys1</default-vsys></settings>"
        "<config><devices><entry name='localhost.localdomain'>"
        "<vsys><entry name='vsys1'/></vsys></entry></devices></config>",
        "Template", template,
    )

    # Parent device group for all Python-managed customers
    ensure(
        dg_xpath(parent_dg),
        "<description>Parent device group for Python-managed PANW customer VPNs</description>",
        "Device group", parent_dg,
    )

    # Ethernet interface used as the IKE gateway local interface
    ensure(
        f"{tpl_network_xpath(template)}/interface/ethernet/entry[@name='{local_interface}']",
        "<layer3/>",
        "Ethernet interface", local_interface,
    )
    config_set(
        f"{tpl_vsys_xpath(template)}/import/network/interface",
        f"<member>{local_interface}</member>",
    )

    # Virtual router
    ensure(
        f"{tpl_network_xpath(template)}/virtual-router/entry[@name='{virtual_router}']",
        f"<interface><member>{local_interface}</member></interface>",
        "Virtual router", virtual_router,
    )

    # IKE crypto profile
    ensure(
        f"{tpl_network_xpath(template)}/ike/crypto-profiles/ike-crypto-profiles/entry[@name='{ike_profile}']",
        "<hash><member>sha256</member></hash>"
        "<dh-group><member>group14</member></dh-group>"
        "<encryption><member>aes-256-cbc</member></encryption>"
        "<lifetime><hours>8</hours></lifetime>",
        "IKE crypto profile", ike_profile,
    )

    # IPsec crypto profile
    ensure(
        f"{tpl_network_xpath(template)}/ike/crypto-profiles/ipsec-crypto-profiles/entry[@name='{ipsec_profile}']",
        "<esp><encryption><member>aes-256-cbc</member></encryption>"
        "<authentication><member>sha256</member></authentication></esp>"
        "<dh-group>group14</dh-group>"
        "<lifetime><hours>1</hours></lifetime>",
        "IPsec crypto profile", ipsec_profile,
    )


# -----------------------------
# Per-customer deployment
# -----------------------------
def deploy_customer_vpn(customer: Dict[str, Any], global_config: Dict[str, Any]) -> None:
    customer_name = customer["customer_name"]
    device_group = customer["device_group"]
    template = global_config["template"]
    parent_dg = global_config["parent_device_group"]
    local_interface = global_config.get("local_interface", "ethernet1/1")
    virtual_router = global_config.get("virtual_router", "default")
    ike_profile = global_config.get("ike_profile", "PANW-Python-IKEv2-Standard")
    ipsec_profile = global_config.get("ipsec_profile", "PANW-Python-IPsec-Standard")

    tunnel_if_name = f"tunnel.{customer['tunnel_number']}"

    print(f"\n{'='*70}")
    print(f"Deploying VPN for: {customer_name}")
    print(f"{'='*70}")

    # Step 1: Device group nested under the parent device group
    print(f"\n[Step 1] Creating device group '{device_group}'...")
    ensure(
        dg_xpath(device_group),
        f"<description>Device group for {customer_name} VPN configuration</description>",
        "Device group", device_group,
    )
    ensure_dg_parent(device_group, parent_dg)

    # Step 2: Tunnel interface (template)
    print(f"\n[Step 2] Creating tunnel interface '{tunnel_if_name}'...")
    ensure(
        f"{tpl_network_xpath(template)}/interface/tunnel/units/entry[@name='{tunnel_if_name}']",
        f"<comment>{customer_name}-Interface</comment>",
        "Tunnel interface", tunnel_if_name,
    )
    config_set(
        f"{tpl_vsys_xpath(template)}/import/network/interface",
        f"<member>{tunnel_if_name}</member>",
    )
    config_set(
        f"{tpl_network_xpath(template)}/virtual-router/entry[@name='{virtual_router}']/interface",
        f"<member>{tunnel_if_name}</member>",
    )

    # Step 3: Zone (template, vsys1)
    print(f"\n[Step 3] Creating zone '{customer['zone_name']}'...")
    ensure(
        f"{tpl_vsys_xpath(template)}/zone/entry[@name='{customer['zone_name']}']",
        f"<network><layer3><member>{tunnel_if_name}</member></layer3></network>",
        "Zone", customer["zone_name"],
    )

    # Step 4: IKE gateway (template)
    print(f"\n[Step 4] Creating IKE gateway '{customer['ike_gateway_name']}'...")
    ensure(
        f"{tpl_network_xpath(template)}/ike/gateway/entry[@name='{customer['ike_gateway_name']}']",
        f"<authentication><pre-shared-key><key>{customer['psk']}</key></pre-shared-key></authentication>"
        f"<protocol><ikev2><ike-crypto-profile>{ike_profile}</ike-crypto-profile>"
        "<dpd><enable>yes</enable></dpd></ikev2>"
        "<version>ikev2</version></protocol>"
        "<protocol-common><nat-traversal><enable>yes</enable></nat-traversal>"
        "<fragmentation><enable>no</enable></fragmentation></protocol-common>"
        f"<local-address><interface>{local_interface}</interface></local-address>"
        f"<peer-address><ip>{customer['peer_ip']}</ip></peer-address>",
        "IKE gateway", customer["ike_gateway_name"],
    )

    # Step 5: IPsec tunnel (template)
    print(f"\n[Step 5] Creating IPsec tunnel '{customer['ipsec_tunnel_name']}'...")
    ensure(
        f"{tpl_network_xpath(template)}/tunnel/ipsec/entry[@name='{customer['ipsec_tunnel_name']}']",
        f"<tunnel-interface>{tunnel_if_name}</tunnel-interface>"
        f"<auto-key><ike-gateway><entry name='{customer['ike_gateway_name']}'/></ike-gateway>"
        f"<ipsec-crypto-profile>{ipsec_profile}</ipsec-crypto-profile></auto-key>",
        "IPsec tunnel", customer["ipsec_tunnel_name"],
    )

    # Step 6: Address objects (device group)
    print(f"\n[Step 6] Creating address objects...")
    ensure(
        f"{dg_xpath(device_group)}/address/entry[@name='{customer['customer_network_object']}']",
        f"<ip-netmask>{customer['customer_network']}</ip-netmask>",
        "Address object", customer["customer_network_object"],
    )
    panw_network_object = global_config.get("panw_network_object", "PANW-Python-net")
    panw_network = global_config.get("panw_network", "10.10.0.0/16")
    ensure(
        f"{dg_xpath(device_group)}/address/entry[@name='{panw_network_object}']",
        f"<ip-netmask>{panw_network}</ip-netmask>",
        "Address object", panw_network_object,
    )

    # Step 7: Security rule (device group pre-rulebase)
    print(f"\n[Step 7] Creating security rule '{customer['security_rule_name']}'...")
    ensure(
        f"{dg_xpath(device_group)}/pre-rulebase/security/rules/entry[@name='{customer['security_rule_name']}']",
        f"<from><member>{customer['zone_name']}</member></from>"
        f"<to><member>{global_config.get('to_zone', 'trust')}</member></to>"
        f"<source><member>{customer['customer_network_object']}</member></source>"
        f"<destination><member>{panw_network_object}</member></destination>"
        "<source-user><member>any</member></source-user>"
        "<category><member>any</member></category>"
        "<application><member>any</member></application>"
        "<service><member>any</member></service>"
        "<action>allow</action>",
        "Security rule", customer["security_rule_name"],
    )

    print(f"\n✓ VPN deployment completed for {customer_name}")
    print(f"  Device group: {device_group}")
    print(f"  Zone: {customer['zone_name']}")
    print(f"  Tunnel: {customer['ipsec_tunnel_name']}")
    print(f"  Peer IP: {customer['peer_ip']}")


# -----------------------------
# Deletion
# -----------------------------
def delete_customer(device_group: str, global_config: Dict[str, Any]) -> bool:
    """Delete a customer device group and its template artifacts.

    Template object names are derived from the device group name using the
    repository naming convention:
      PANW-Python-Customer-AB -> Customer-AB-Zone / Customer-AB-IKE-GW / Customer-AB-Tunnel
    """
    template = global_config["template"]
    virtual_router = global_config.get("virtual_router", "default")
    prefix = global_config.get("customer_prefix", "PANW-Python-")

    base = device_group[len(prefix):] if device_group.startswith(prefix) else device_group
    zone_name = f"{base}-Zone"
    ike_gateway_name = f"{base}-IKE-GW"
    ipsec_tunnel_name = f"{base}-Tunnel"

    found_anything = config_get(dg_xpath(device_group)) is not None

    # Find the tunnel interface used by this customer's IPsec tunnel
    tunnel_if_name = None
    tunnel_node = config_get(f"{tpl_network_xpath(template)}/tunnel/ipsec/entry[@name='{ipsec_tunnel_name}']")
    if tunnel_node is not None:
        tunnel_if_name = tunnel_node.findtext(".//tunnel-interface")

    # Delete in reverse dependency order
    if config_delete(f"{tpl_network_xpath(template)}/tunnel/ipsec/entry[@name='{ipsec_tunnel_name}']"):
        print(f"    ✓ Deleted IPsec tunnel '{ipsec_tunnel_name}'")
        found_anything = True
    if config_delete(f"{tpl_network_xpath(template)}/ike/gateway/entry[@name='{ike_gateway_name}']"):
        print(f"    ✓ Deleted IKE gateway '{ike_gateway_name}'")
        found_anything = True
    if config_delete(f"{tpl_vsys_xpath(template)}/zone/entry[@name='{zone_name}']"):
        print(f"    ✓ Deleted zone '{zone_name}'")
        found_anything = True
    if tunnel_if_name:
        config_delete(
            f"{tpl_network_xpath(template)}/virtual-router/entry[@name='{virtual_router}']"
            f"/interface/member[text()='{tunnel_if_name}']"
        )
        config_delete(f"{tpl_vsys_xpath(template)}/import/network/interface/member[text()='{tunnel_if_name}']")
        if config_delete(f"{tpl_network_xpath(template)}/interface/tunnel/units/entry[@name='{tunnel_if_name}']"):
            print(f"    ✓ Deleted tunnel interface '{tunnel_if_name}'")
    if config_delete(dg_xpath(device_group)):
        print(f"    ✓ Deleted device group '{device_group}'")
        found_anything = True

    return found_anything


def delete_customers_from_list(device_groups_to_delete: list, global_config: Dict[str, Any]) -> None:
    if not device_groups_to_delete:
        return

    print(f"\n{'='*70}")
    print("Deleting customers from delete list...")
    print(f"{'='*70}")
    print(f"\n  Found {len(device_groups_to_delete)} device group(s) to delete:")
    for name in sorted(device_groups_to_delete):
        print(f"    • {name}")

    deleted, missing = [], []
    for name in sorted(device_groups_to_delete):
        print(f"\n  → Deleting customer '{name}'...")
        if delete_customer(name, global_config):
            deleted.append(name)
        else:
            print(f"    → Nothing found for '{name}' (already deleted?)")
            missing.append(name)

    print(f"\n  Deletion summary:")
    print(f"    Deleted: {len(deleted)}")
    print(f"    Not found: {len(missing)}")


def cleanup_orphaned_customers(
    global_config: Dict[str, Any],
    expected_device_groups: list,
    device_groups_to_delete: list,
) -> None:
    """Delete customer device groups that are not in the add list or delete list."""
    print(f"\n{'='*70}")
    print("Cleaning up orphaned customers...")
    print(f"{'='*70}")

    prefix = global_config.get("customer_prefix", "PANW-Python-") + "Customer-"
    existing = set(list_customer_device_groups(prefix))
    orphaned = existing - set(expected_device_groups) - set(device_groups_to_delete)

    if not orphaned:
        print("  ✓ No orphaned customers found - all device groups match YAML configuration")
        return

    print(f"\n  Found {len(orphaned)} orphaned customer(s) to delete:")
    for name in sorted(orphaned):
        print(f"    • {name}")

    for name in sorted(orphaned):
        print(f"\n  → Deleting orphaned customer '{name}'...")
        delete_customer(name, global_config)


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    print("=" * 70)
    print("Panorama - Multi-Customer VPN Deployment")
    print("=" * 70)
    print("\nThis script will:")
    print("  • Read customer configurations from customers-to-add.yaml")
    print("  • Delete customers listed in customers-to-delete.yaml")
    print("  • Create shared template and device group hierarchy")
    print("  • Deploy IPsec VPN connections for all customers")
    print("  • Delete orphaned customers (not in add or delete lists)")
    print("  • Commit the candidate configuration to Panorama")
    print("\n" + "-" * 70)

    if not PANORAMA_HOST or not PANORAMA_API_KEY:
        die("Please set PANORAMA_HOST and PANORAMA_API_KEY in .env or your shell.")

    print("\n[Step 0] Loading customer configurations...")
    global_config, customers = load_customers()
    print(f"  ✓ Loaded {len(customers)} customer(s) from customers-to-add.yaml")

    if "template" not in global_config or "parent_device_group" not in global_config:
        die("customers-to-add.yaml must define global.template and global.parent_device_group")

    print("\n[Step 0] Loading customers to delete...")
    device_groups_to_delete = load_device_groups_to_delete()
    if device_groups_to_delete:
        print(f"  ✓ Loaded {len(device_groups_to_delete)} device group(s) from customers-to-delete.yaml")
    else:
        print("  ✓ No customers to delete (customers-to-delete.yaml is empty or doesn't exist)")

    print("\n[Step 0] Verifying Panorama connectivity...")
    info = api_request({"type": "op", "cmd": "<show><system><info></info></system></show>"})
    hostname = info.findtext(".//hostname")
    sw_version = info.findtext(".//sw-version")
    print(f"  ✓ Connected to Panorama '{hostname}' (PAN-OS {sw_version})")

    # Shared config (template, parent device group, profiles)
    deploy_shared_config(global_config)

    # Step 1: Delete customers from delete list first
    if device_groups_to_delete:
        delete_customers_from_list(device_groups_to_delete, global_config)

    # Step 2: Deploy VPN for each customer
    successful, failed = [], []
    if customers:
        print(f"\n{'='*70}")
        print(f"Starting deployment for {len(customers)} customer(s)...")
        print(f"{'='*70}")

        for idx, customer in enumerate(customers, 1):
            try:
                print(f"\n[{idx}/{len(customers)}] Processing {customer['customer_name']}...")
                deploy_customer_vpn(customer, global_config)
                successful.append(customer["customer_name"])
            except Exception as e:
                print(f"\n✗ Failed to deploy VPN for {customer['customer_name']}: {e}")
                failed.append(customer["customer_name"])
                continue
    else:
        print("\n⚠ No customers to deploy (customers-to-add.yaml is empty)")

    # Step 3: Cleanup orphaned customers
    expected_device_groups = [customer["device_group"] for customer in customers]
    cleanup_orphaned_customers(global_config, expected_device_groups, device_groups_to_delete)

    # Step 4: Commit
    commit("GitOps Python VPN automation")

    # Summary
    if customers:
        print(f"\n{'='*70}")
        print("DEPLOYMENT SUMMARY")
        print(f"{'='*70}")
        print(f"Total customers: {len(customers)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")

        if successful:
            print(f"\n✓ Successfully deployed VPNs for:")
            for name in successful:
                print(f"  • {name}")

        if failed:
            print(f"\n✗ Failed deployments:")
            for name in failed:
                print(f"  • {name}")
            sys.exit(1)

        print(f"\n✓ All VPN deployments completed successfully!")

    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        die(str(e))
    except KeyboardInterrupt:
        print("\n\nDeployment interrupted by user.")
        sys.exit(1)
