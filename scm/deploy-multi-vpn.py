#!/usr/bin/env python3
"""
Strata Cloud Manager (PANW) - Multi-Customer VPN Deployment Script

Reads customer configurations from customers-to-add.yaml and creates IPsec VPN connections
for each customer with their own folder structure.

Requirements:
  pip install requests pyyaml python-dotenv

Usage:
  python deploy-multi-vpn.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests
import yaml

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, skip loading .env file
    pass

# Disable proxy inheritance from environment
for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(proxy_var, None)

# Create a session that doesn't trust environment variables
_session = requests.Session()
_session.trust_env = False
_session.proxies = {}  # Explicitly disable proxies


# -----------------------------
# Configuration
# -----------------------------
@dataclass(frozen=True)
class AuthConfig:
    """OAuth2 credentials (service account)"""
    client_id: str = os.environ.get("PANW_CLIENT_ID")
    client_secret: str = os.environ.get("PANW_CLIENT_SECRET")
    tsg_id: str = os.environ.get("PANW_TSG_ID")  # Tenant Service Group ID


AUTH = AuthConfig()


# -----------------------------
# Endpoints
# -----------------------------
BASE = "https://api.strata.paloaltonetworks.com"
TOKEN_URL = "https://auth.apps.paloaltonetworks.com/oauth2/access_token"

# Setup
FOLDERS = f"{BASE}/config/setup/v1/folders"

# Network
ZONES = f"{BASE}/config/network/v1/zones"
TUNNEL_INTERFACES = f"{BASE}/config/network/v1/tunnel-interfaces"
IKE_CRYPTO_PROFILES = f"{BASE}/config/network/v1/ike-crypto-profiles"
IPSEC_CRYPTO_PROFILES = f"{BASE}/config/network/v1/ipsec-crypto-profiles"
IKE_GATEWAYS = f"{BASE}/config/network/v1/ike-gateways"
IPSEC_TUNNELS = f"{BASE}/config/network/v1/ipsec-tunnels"

# Objects
ADDRESSES = f"{BASE}/config/objects/v1/addresses"

# Security
SECURITY_RULES = f"{BASE}/config/security/v1/security-rules"


# -----------------------------
# Helpers
# -----------------------------
class ApiError(RuntimeError):
    pass


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def get_token(client_id: str, client_secret: str, tsg_id: str) -> str:
    r = _session.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": f"tsg_id:{tsg_id}"},
        timeout=60,
    )
    if not r.ok:
        raise ApiError(f"Token request failed: {r.status_code} {r.text}")
    j = r.json()
    token = j.get("access_token")
    if not token:
        raise ApiError(f"Token response missing access_token: {j}")
    return token


def request_json(
    method: str,
    url: str,
    token: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    ok_status: Tuple[int, ...] = (200, 201, 202),
) -> Tuple[int, Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    r = _session.request(
        method,
        url,
        headers=headers,
        params=params,
        data=json.dumps(body) if body is not None else None,
        timeout=60,
    )

    if r.status_code in ok_status:
        return r.status_code, (r.json() if r.text else {})
    if r.status_code == 409:
        return r.status_code, (r.json() if r.text else {})

    raise ApiError(f"{method} {url} failed: {r.status_code} {r.text}")


def extract_id(payload: Dict[str, Any]) -> Optional[str]:
    """Extract ID from various SCM response formats."""
    if "id" in payload and isinstance(payload["id"], str):
        return payload["id"]
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("id"), str):
        return data["id"]
    return None


def list_by_name(url: str, token: str, name: str, folder_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """List and filter by name, optionally by folder."""
    params: Dict[str, Any] = {"name": name}
    if folder_id:
        params["folder"] = folder_id
    
    try:
        _, j = request_json("GET", url, token, params=params, ok_status=(200,))
    except ApiError:
        try:
            _, j = request_json("GET", url, token, params=None, ok_status=(200,))
        except ApiError:
            return None

    items = j.get("data")
    if not isinstance(items, list):
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("name") != name:
            continue
        if folder_id:
            item_folder = item.get("folder") or item.get("folder_id")
            if item_folder and item_folder != folder_id:
                continue
        return item

    return None


def create_or_get(
    *,
    create_url: str,
    list_url: str,
    token: str,
    name: str,
    body: Dict[str, Any],
    folder_id: Optional[str] = None,
    resource_type: str = "Resource",
) -> str:
    """Create a resource or get existing one. Returns the resource ID."""
    existing = list_by_name(list_url, token, name, folder_id=folder_id)
    if existing:
        eid = existing.get("id")
        if isinstance(eid, str):
            folder_info = f" in folder '{folder_id}'" if folder_id else ""
            print(f"  → {resource_type} '{name}' already exists{folder_info}")
            return eid

    try:
        status, j = request_json("POST", create_url, token, body=body, ok_status=(200, 201, 202, 400, 409))
    except ApiError as e:
        error_str = str(e)
        if "400" in error_str and ("already exists" in error_str.lower() or "OBJECT_ALREADY_EXISTS" in error_str):
            existing = list_by_name(list_url, token, name, folder_id=folder_id)
            if existing and isinstance(existing.get("id"), str):
                eid = existing["id"]
                print(f"  ✓ {resource_type} '{name}' already exists")
                return eid
            print(f"  ✓ {resource_type} '{name}' already exists")
            return name
        raise
    
    if status == 409:
        existing = list_by_name(list_url, token, name, folder_id=folder_id)
        if existing and isinstance(existing.get("id"), str):
            eid = existing["id"]
            print(f"  ✓ {resource_type} '{name}' already exists")
            return eid
        raise ApiError(f"Conflict creating {name} but could not find it via list endpoint. Response: {j}")
    
    if status == 400:
        error_msg = str(j)
        if "already exists" in error_msg.lower() or "OBJECT_ALREADY_EXISTS" in error_msg:
            existing = list_by_name(list_url, token, name, folder_id=folder_id)
            if existing and isinstance(existing.get("id"), str):
                eid = existing["id"]
                print(f"  ✓ {resource_type} '{name}' already exists")
                return eid
            print(f"  ✓ {resource_type} '{name}' already exists")
            return name

    new_id = extract_id(j)
    if not new_id:
        if isinstance(j.get("id"), str):
            new_id = j["id"]
    if not new_id:
        raise ApiError(f"Create succeeded but could not extract id for {name}. Response: {j}")

    print(f"  ✓ Created {resource_type.lower()} '{name}' successfully")
    return new_id


def load_customers(yaml_file: str = "customers-to-add.yaml") -> Tuple[Dict[str, Any], list]:
    """Load customer configurations from YAML file."""
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)
        if data is None:
            data = {}
        global_config = data.get("global", {}) or {}
        customers = data.get("customers", [])
        # Ensure customers is always a list, even if None
        if customers is None:
            customers = []
        if not isinstance(customers, list):
            customers = []
        return global_config, customers
    except FileNotFoundError:
        die(f"Configuration file '{yaml_file}' not found")
    except yaml.YAMLError as e:
        die(f"Error parsing YAML file: {e}")


def load_folders_to_delete(yaml_file: str = "customers-to-delete.yaml") -> list:
    """Load list of folder names to delete from YAML file."""
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)
        folders = data.get("folders_to_delete", [])
        return folders if isinstance(folders, list) else []
    except FileNotFoundError:
        # File doesn't exist - return empty list (not an error)
        return []
    except yaml.YAMLError as e:
        print(f"  ⚠ Warning: Error parsing '{yaml_file}': {e}", file=sys.stderr)
        return []


def deploy_customer_vpn(
    token: str,
    customer: Dict[str, Any],
    global_config: Dict[str, Any],
    root_folder_name: str,
) -> None:
    """Deploy VPN configuration for a single customer."""
    customer_name = customer["customer_name"]
    folder_name = customer["folder_name"]
    
    print(f"\n{'='*70}")
    print(f"Deploying VPN for: {customer_name}")
    print(f"{'='*70}")
    
    # Step 1: Create customer folder
    print(f"\n[Step 1] Creating folder '{folder_name}'...")
    child_folder_id = create_or_get(
        create_url=FOLDERS,
        list_url=FOLDERS,
        token=token,
        name=folder_name,
        body={
            "name": folder_name,
            "parent": root_folder_name,
            "description": f"Folder for {customer_name} VPN configuration",
        },
        folder_id=None,
        resource_type="Folder",
    )
    
    # Step 2: Create zone
    print(f"\n[Step 2] Creating zone '{customer['zone_name']}'...")
    zone_id = create_or_get(
        create_url=ZONES,
        list_url=ZONES,
        token=token,
        name=customer["zone_name"],
        body={
            "name": customer["zone_name"],
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="Zone",
    )
    
    # Step 3: Create tunnel interface
    tunnel_if_name = f"$tunnel-{customer['tunnel_number']}"
    tunnel_if_default = f"tunnel.{customer['tunnel_number']}"
    print(f"\n[Step 3] Creating tunnel interface '{tunnel_if_name}' ({tunnel_if_default})...")
    tunnel_if_id = create_or_get(
        create_url=TUNNEL_INTERFACES,
        list_url=TUNNEL_INTERFACES,
        token=token,
        name=tunnel_if_name,
        body={
            "name": tunnel_if_name,
            "default_value": tunnel_if_default,
            "comment": f"{customer_name}-Interface",
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="Tunnel interface",
    )
    
    # Step 4: Create IKE crypto profile (shared, but create per customer folder)
    ike_profile_name = global_config.get("ike_profile", "PANW-Python-IKEv2-Standard")
    print(f"\n[Step 4] Creating IKE crypto profile '{ike_profile_name}'...")
    ike_crypto_id = create_or_get(
        create_url=IKE_CRYPTO_PROFILES,
        list_url=IKE_CRYPTO_PROFILES,
        token=token,
        name=ike_profile_name,
        body={
            "name": ike_profile_name,
            "hash": ["sha256"],
            "encryption": ["aes-256-cbc"],
            "dh_group": ["group14"],
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="IKE crypto profile",
    )
    
    # Step 5: Create IPsec crypto profile (shared, but create per customer folder)
    ipsec_profile_name = global_config.get("ipsec_profile", "PANW-Python-IPsec-Standard")
    print(f"\n[Step 5] Creating IPsec crypto profile '{ipsec_profile_name}'...")
    ipsec_crypto_id = create_or_get(
        create_url=IPSEC_CRYPTO_PROFILES,
        list_url=IPSEC_CRYPTO_PROFILES,
        token=token,
        name=ipsec_profile_name,
        body={
            "name": ipsec_profile_name,
            "esp": {
                "encryption": ["aes-256-cbc"],
                "authentication": ["sha256"],
            },
            "lifetime": {"seconds": 3600},
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="IPsec crypto profile",
    )
    
    # Step 6: Create IKE gateway
    print(f"\n[Step 6] Creating IKE gateway '{customer['ike_gateway_name']}'...")
    ike_gw_id = create_or_get(
        create_url=IKE_GATEWAYS,
        list_url=IKE_GATEWAYS,
        token=token,
        name=customer["ike_gateway_name"],
        body={
            "name": customer["ike_gateway_name"],
            "protocol": {"version": "ikev2"},
            "peer_address": {"ip": customer["peer_ip"]},
            "authentication": {
                "pre_shared_key": {"key": customer["psk"]},
            },
            "local_address": {"ip": global_config.get("local_public_ip")} if global_config.get("local_public_ip") else {},
            "local_interface": [global_config.get("local_interface", "ethernet1/1")],
            "ike_crypto_profile_id": ike_crypto_id,
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="IKE gateway",
    )
    
    # Step 7: Create IPsec tunnel
    print(f"\n[Step 7] Creating IPsec tunnel '{customer['ipsec_tunnel_name']}'...")
    ipsec_tunnel_id = create_or_get(
        create_url=IPSEC_TUNNELS,
        list_url=IPSEC_TUNNELS,
        token=token,
        name=customer["ipsec_tunnel_name"],
        body={
            "name": customer["ipsec_tunnel_name"],
            "tunnel_interface": tunnel_if_name,
            "auto_key": {
                "ike_gateway": [{"name": customer["ike_gateway_name"]}],
                "ipsec_crypto_profile": ipsec_profile_name,
            },
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="IPsec tunnel",
    )
    
    # Step 8: Create address objects
    print(f"\n[Step 8] Creating address objects...")
    print(f"  → Creating customer network object '{customer['customer_network_object']}' ({customer['customer_network']})...")
    cust_addr_id = create_or_get(
        create_url=ADDRESSES,
        list_url=ADDRESSES,
        token=token,
        name=customer["customer_network_object"],
        body={
            "name": customer["customer_network_object"],
            "ip_netmask": customer["customer_network"],
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="Address object",
    )
    
    panw_network_object = global_config.get("panw_network_object", "PANW-Python-net")
    panw_network = global_config.get("panw_network", "10.10.0.0/16")
    print(f"  → Creating PANW network object '{panw_network_object}' ({panw_network})...")
    panw_addr_id = create_or_get(
        create_url=ADDRESSES,
        list_url=ADDRESSES,
        token=token,
        name=panw_network_object,
        body={
            "name": panw_network_object,
            "ip_netmask": panw_network,
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="Address object",
    )
    
    # Step 9: Create security rule
    print(f"\n[Step 9] Creating security rule '{customer['security_rule_name']}'...")
    sec_rule_id = create_or_get(
        create_url=SECURITY_RULES,
        list_url=SECURITY_RULES,
        token=token,
        name=customer["security_rule_name"],
        body={
            "name": customer["security_rule_name"],
            "from": [customer["zone_name"]],
            "to": [global_config.get("to_zone", "trust")],
            "source": [customer["customer_network_object"]],
            "destination": [panw_network_object],
            "application": ["any"],
            "service": ["any"],
            "category": ["any"],
            "source_user": ["any"],
            "action": "allow",
            "folder": folder_name,
        },
        folder_id=folder_name,
        resource_type="Security rule",
    )
    
    print(f"\n✓ VPN deployment completed for {customer_name}")
    print(f"  Folder: {folder_name}")
    print(f"  Zone: {customer['zone_name']}")
    print(f"  Tunnel: {customer['ipsec_tunnel_name']}")
    print(f"  Peer IP: {customer['peer_ip']}")


def list_folders_under_parent(token: str, parent_folder_name: str) -> list:
    """List all folders under a parent folder."""
    try:
        # First get the parent folder to get its ID
        parent_folder = list_by_name(FOLDERS, token, parent_folder_name, folder_id=None)
        parent_folder_id = None
        if parent_folder:
            parent_folder_id = parent_folder.get("id")
        
        # List all folders
        _, j = request_json("GET", FOLDERS, token, params=None, ok_status=(200,))
        items = j.get("data", [])
        if not isinstance(items, list):
            return []
        
        folders = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # Check if this folder's parent matches the parent_folder_name or parent_folder_id
            parent = item.get("parent") or item.get("parent_id")
            if parent == parent_folder_name or (parent_folder_id and parent == parent_folder_id):
                folders.append({
                    "name": item.get("name"),
                    "id": item.get("id"),
                })
        return folders
    except ApiError:
        return []


def delete_folder(token: str, folder_name: str) -> bool:
    """Delete a folder by name. Returns True if deleted, False if not found."""
    # First find the folder
    folder = list_by_name(FOLDERS, token, folder_name, folder_id=None)
    if not folder:
        return False
    
    folder_id = folder.get("id")
    if not folder_id:
        return False
    
    try:
        delete_url = f"{FOLDERS}/{folder_id}"
        status, _ = request_json("DELETE", delete_url, token, ok_status=(200, 204, 404))
        if status == 404:
            return False  # Already deleted
        return True
    except ApiError as e:
        # Check if it's a dependency error
        error_msg = str(e)
        if "409" in error_msg and "referencing" in error_msg.lower():
            print(f"  ⚠ Cannot delete folder '{folder_name}': folder contains resources")
            return False
        print(f"  ✗ Failed to delete folder '{folder_name}': {e}")
        return False


def delete_customers_from_list(
    token: str,
    folders_to_delete: list,
) -> None:
    """Delete folders specified in the delete list."""
    if not folders_to_delete:
        return
    
    print(f"\n{'='*70}")
    print("Deleting customers from delete list...")
    print(f"{'='*70}")
    print(f"\n  Found {len(folders_to_delete)} folder(s) to delete:")
    for folder_name in sorted(folders_to_delete):
        print(f"    • {folder_name}")
    
    deleted = []
    failed = []
    
    for folder_name in sorted(folders_to_delete):
        print(f"\n  → Deleting folder '{folder_name}'...")
        if delete_folder(token, folder_name):
            print(f"  ✓ Successfully deleted folder '{folder_name}'")
            deleted.append(folder_name)
        else:
            failed.append(folder_name)
    
    print(f"\n  Deletion summary:")
    print(f"    Deleted: {len(deleted)}")
    print(f"    Failed: {len(failed)}")
    
    if failed:
        print(f"\n  ⚠ Could not delete {len(failed)} folder(s) (may contain resources):")
        for folder_name in failed:
            print(f"    • {folder_name}")


def cleanup_orphaned_folders(
    token: str,
    root_folder_name: str,
    expected_folder_names: list,
    folders_to_delete: list,
) -> None:
    """Delete folders under root_folder_name that are not in expected_folder_names or delete list."""
    print(f"\n{'='*70}")
    print("Cleaning up orphaned folders...")
    print(f"{'='*70}")
    
    # Get all folders under the root folder
    existing_folders = list_folders_under_parent(token, root_folder_name)
    existing_folder_names = {f["name"] for f in existing_folders if f.get("name")}
    expected_folder_set = set(expected_folder_names)
    delete_list_set = set(folders_to_delete)
    
    # Find folders that exist but are not in add list and not in delete list
    # (folders in delete list are handled separately, so exclude them from orphaned)
    orphaned_folders = existing_folder_names - expected_folder_set - delete_list_set
    
    if not orphaned_folders:
        print("  ✓ No orphaned folders found - all folders match YAML configuration")
        return
    
    print(f"\n  Found {len(orphaned_folders)} orphaned folder(s) to delete:")
    for folder_name in sorted(orphaned_folders):
        print(f"    • {folder_name}")
    
    deleted = []
    failed = []
    
    for folder_name in sorted(orphaned_folders):
        print(f"\n  → Deleting orphaned folder '{folder_name}'...")
        if delete_folder(token, folder_name):
            print(f"  ✓ Successfully deleted folder '{folder_name}'")
            deleted.append(folder_name)
        else:
            failed.append(folder_name)
    
    print(f"\n  Cleanup summary:")
    print(f"    Deleted: {len(deleted)}")
    print(f"    Failed: {len(failed)}")
    
    if failed:
        print(f"\n  ⚠ Could not delete {len(failed)} folder(s) (may contain resources):")
        for folder_name in failed:
            print(f"    • {folder_name}")


def main() -> None:
    print("=" * 70)
    print("Strata Cloud Manager - Multi-Customer VPN Deployment")
    print("=" * 70)
    print("\nThis script will:")
    print("  • Read customer configurations from customers-to-add.yaml")
    print("  • Delete folders listed in customers-to-delete.yaml")
    print("  • Create folder hierarchy for each customer")
    print("  • Deploy IPsec VPN connections for all customers")
    print("  • Delete orphaned folders (not in add or delete lists)")
    print("\n" + "-" * 70)
    
    # Load customer configurations
    print("\n[Step 0] Loading customer configurations...")
    global_config, customers = load_customers()
    print(f"  ✓ Loaded {len(customers)} customer(s) from customers-to-add.yaml")
    
    # Load folders to delete
    print("\n[Step 0] Loading folders to delete...")
    folders_to_delete = load_folders_to_delete()
    if folders_to_delete:
        print(f"  ✓ Loaded {len(folders_to_delete)} folder(s) from customers-to-delete.yaml")
    else:
        print(f"  ✓ No folders to delete (customers-to-delete.yaml is empty or doesn't exist)")
    
    # Authenticate
    print("\n[Step 0] Authenticating with Strata Cloud Manager API...")
    if not AUTH.client_id or not AUTH.client_secret or not AUTH.tsg_id:
        die("Please set PANW_CLIENT_ID, PANW_CLIENT_SECRET, and PANW_TSG_ID in .env or your shell.")
    token = get_token(AUTH.client_id, AUTH.client_secret, AUTH.tsg_id)
    print("  ✓ Authentication successful")
    
    # Create root folder
    root_folder_name = global_config.get("root_folder", "PANW Python Global")
    print(f"\n[Step 0] Creating/verifying root folder '{root_folder_name}'...")
    root_folder_id = create_or_get(
        create_url=FOLDERS,
        list_url=FOLDERS,
        token=token,
        name=root_folder_name,
        body={
            "name": root_folder_name,
            "parent": "ngfw-shared",
            "description": "Root folder for Python-managed PANW customer VPNs",
        },
        folder_id=None,
        resource_type="Folder",
    )
    
    # Step 1: Delete folders from delete list first
    if folders_to_delete:
        delete_customers_from_list(token, folders_to_delete)
    
    # Step 2: Deploy VPN for each customer
    if customers:
        print(f"\n{'='*70}")
        print(f"Starting deployment for {len(customers)} customer(s)...")
        print(f"{'='*70}")
        
        successful = []
        failed = []
        
        for idx, customer in enumerate(customers, 1):
            try:
                print(f"\n[{idx}/{len(customers)}] Processing {customer['customer_name']}...")
                deploy_customer_vpn(token, customer, global_config, root_folder_name)
                successful.append(customer['customer_name'])
            except Exception as e:
                print(f"\n✗ Failed to deploy VPN for {customer['customer_name']}: {e}")
                failed.append(customer['customer_name'])
                continue
        
        # Step 3: Cleanup orphaned folders (folders not in add list and not in delete list)
        expected_folder_names = [customer["folder_name"] for customer in customers]
        cleanup_orphaned_folders(token, root_folder_name, expected_folder_names, folders_to_delete)
        
        # Summary
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
    else:
        print("\n⚠ No customers to deploy (customers-to-add.yaml is empty)")
        # Still cleanup orphaned folders even if no customers to deploy
        cleanup_orphaned_folders(token, root_folder_name, [], folders_to_delete)
    
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        die(str(e))
    except KeyboardInterrupt:
        print("\n\nDeployment interrupted by user.")
        sys.exit(1)

