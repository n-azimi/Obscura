#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 Navid Azimi

"""
Obscura Inspector: Transaction Analyzer

This script fetches, classifies, and normalizes transactions for the Obscura smart contract.
It uses the Algorand Indexer API to retrieve all transactions associated with the contract,
including both direct payments and application calls.

Key Features:
- Automatically loads the contract address from `frontend/.env` or accepts it via CLI.
- Fetches full transaction history (including inner transactions) with pagination.
- Classifies transactions into:
  - Deposits (grouped payment + application call)
  - Withdrawals (application calls with 'withdraw' argument)
  - Fund Contract (direct ALGO payments to the contract)
  - Other (e.g., contract creation)
- Recursively extracts and normalizes all relevant fields (Base64, Hex, ASCII).
- Outputs a structured JSON file (`transactions.json`) for detailed inspection.

Usage:
  python obscura_inspector.py [contract_address]
"""

import json
import base64
import argparse
import os
import requests

INDEXER_URL = "https://testnet-idx.algonode.cloud"

def fetch_transactions(address):
    """Fetch all transactions for the given address using the Algorand Indexer API with pagination."""
    print(f"● Fetching transactions...")
    txns = []
    next_token = None
    url = f"{INDEXER_URL}/v2/accounts/{address}/transactions"
    
    while True:
        params = {"limit": 1000}
        if next_token:
            params["next"] = next_token
            
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"Error fetching data: {response.text}")
            break
            
        data = response.json()
        txns.extend(data.get("transactions", []))
        
        next_token = data.get("next-token")
        if not next_token:
            break
            
    # Also fetch by application ID if we can determine it from the transactions
    app_ids = set()
    for txn in txns:
        if "application-transaction" in txn:
            app_id = txn["application-transaction"].get("application-id")
            if app_id:
                app_ids.add(app_id)
        elif "inner-txns" in txn:
            for inner in txn["inner-txns"]:
                if "application-transaction" in inner:
                    app_id = inner["application-transaction"].get("application-id")
                    if app_id:
                        app_ids.add(app_id)
                        
    for app_id in app_ids:
        print(f"● Fetching application calls for App ID {app_id}...")
        app_url = f"{INDEXER_URL}/v2/transactions"
        next_token = None
        while True:
            params = {"limit": 1000, "application-id": app_id}
            if next_token:
                params["next"] = next_token
                
            response = requests.get(app_url, params=params)
            if response.status_code != 200:
                print(f"Error fetching app calls: {response.text}")
                break
                
            data = response.json()
            new_txns = data.get("transactions", [])
            
            # Avoid duplicates
            existing_ids = {t.get("id") for t in txns}
            for t in new_txns:
                if t.get("id") not in existing_ids:
                    txns.append(t)
            
            next_token = data.get("next-token")
            if not next_token:
                break

    print(f"● Fetched {len(txns)} total transactions.")
    return txns

def decode_b64(b64_str):
    """Decode a base64 string to bytes."""
    try:
        return base64.b64decode(b64_str)
    except:
        return None

def normalize_b64_field(b64_str):
    """Return a dictionary with raw base64, hex, and ascii (if printable)."""
    decoded_bytes = decode_b64(b64_str)
    if decoded_bytes is not None:
        hex_val = decoded_bytes.hex()
        try:
            ascii_val = decoded_bytes.decode('ascii')
            # Only keep ascii if it's mostly printable characters
            if not all(32 <= ord(c) < 127 for c in ascii_val):
                ascii_val = None
        except:
            ascii_val = None
            
        return {
            "raw_b64": b64_str,
            "hex": hex_val,
            "ascii": ascii_val
        }
    return {"raw_b64": b64_str, "hex": None, "ascii": None}

def extract_and_normalize(txn):
    """Extract relevant fields from a transaction and normalize base64 data."""
    extracted = {
        "id": txn.get("id"),
        "sender": txn.get("sender"),
        "timestamp": txn.get("round-time"),
        "tx-type": txn.get("tx-type"),
        "fee": txn.get("fee"),
        "confirmed-round": txn.get("confirmed-round"),
        "group": txn.get("group"),
        "first-valid": txn.get("first-valid"),
        "last-valid": txn.get("last-valid"),
        "genesis-id": txn.get("genesis-id"),
        "genesis-hash": normalize_b64_field(txn.get("genesis-hash")) if txn.get("genesis-hash") else None,
        "signature": normalize_b64_field(txn.get("signature", {}).get("sig")) if txn.get("signature", {}).get("sig") else None
    }
    
    # Extract Payment info
    if "payment-transaction" in txn:
        pay_txn = txn["payment-transaction"]
        extracted["amount"] = pay_txn.get("amount")
        extracted["receiver"] = pay_txn.get("receiver")
        
    # Extract Application info
    if "application-transaction" in txn:
        app_txn = txn["application-transaction"]
        extracted["application-id"] = app_txn.get("application-id")
        
        # App args
        if "application-args" in app_txn:
            extracted["app_args"] = [normalize_b64_field(arg) for arg in app_txn["application-args"]]
            
        # Box refs
        if "box-references" in app_txn:
            extracted["box_refs"] = []
            for box in app_txn["box-references"]:
                if "name" in box:
                    extracted["box_refs"].append(normalize_b64_field(box["name"]))
                    
        # Foreign Apps
        if "foreign-apps" in app_txn:
            extracted["foreign_apps"] = app_txn["foreign-apps"]
            
        # Accounts
        if "accounts" in app_txn:
            extracted["accounts"] = app_txn["accounts"]
            
        # Global State Delta
        if "global-state-delta" in txn:
            extracted["global_state_delta"] = []
            for delta in txn["global-state-delta"]:
                key = normalize_b64_field(delta.get("key"))
                val = delta.get("value", {})
                extracted["global_state_delta"].append({"key": key, "value": val})
                
    # Logs
    if "logs" in txn:
        extracted["logs"] = [normalize_b64_field(log) for log in txn["logs"]]
        
    # Note
    if "note" in txn:
        extracted["note"] = normalize_b64_field(txn["note"])
        
    # Inner txns (recursive extraction)
    if "inner-txns" in txn:
        extracted["inner_txns"] = [extract_and_normalize(inner) for inner in txn["inner-txns"]]
        
    return extracted

def classify_transactions(txns, contract_address):
    """Classify transactions into deposit, withdraw, fund_contract, and other."""
    classified = {
        "deposit": [],
        "withdraw": [],
        "fund_contract": [],
        "other": []
    }
    
    # First pass: identify group IDs that contain a deposit app call
    # Since deposits consist of a payment txn and an app call txn grouped together,
    # we need to find the group IDs where the app call has 'deposit' as the first arg.
    # However, the Indexer might not return the app call if we query by the contract address
    # and the app call doesn't explicitly reference the contract address in a way the indexer catches.
    # So we also need a robust way to identify the payment part of a deposit if the app call is missing.
    deposit_groups = set()
    for txn in txns:
        app_txn = txn.get("application-transaction", {})
        app_args = app_txn.get("application-args", [])
        if app_args:
            first_arg = decode_b64(app_args[0])
            if first_arg == b'deposit':
                group_id = txn.get("group")
                if group_id:
                    deposit_groups.add(group_id)
                    
    # Second pass: classify and extract
    for txn in txns:
        extracted = extract_and_normalize(txn)
        
        app_txn = txn.get("application-transaction", {})
        app_args = app_txn.get("application-args", [])
        
        is_deposit = False
        is_withdraw = False
        
        # Check app args for explicit classification
        if app_args:
            first_arg = decode_b64(app_args[0])
            if first_arg == b'deposit':
                is_deposit = True
            elif first_arg == b'withdraw':
                is_withdraw = True
                
        # If it's a payment or other txn, check if it's part of a deposit group
        if not is_deposit and not is_withdraw:
            group_id = txn.get("group")
            if group_id:
                # If we know this group contains a deposit app call, it's a deposit
                if group_id in deposit_groups:
                    is_deposit = True
                # If we don't have the app call in our results, but it's a grouped payment of exactly 1 ALGO to the contract,
                # it is the payment half of a deposit group.
                elif txn.get("tx-type") == "pay":
                    pay_txn = txn.get("payment-transaction", {})
                    if pay_txn.get("amount") == 1000000 and pay_txn.get("receiver") == contract_address:
                        is_deposit = True
                        deposit_groups.add(group_id) # Add it so other txns in this group are also caught if they exist
                        
        # Classify
        if is_deposit:
            classified["deposit"].append(extracted)
        elif is_withdraw:
            classified["withdraw"].append(extracted)
        elif txn.get("tx-type") == "pay":
            # If it's a payment to the contract that IS NOT part of a deposit group, it's funding
            pay_txn = txn.get("payment-transaction", {})
            if pay_txn.get("receiver") == contract_address:
                classified["fund_contract"].append(extracted)
            else:
                classified["other"].append(extracted)
        else:
            classified["other"].append(extracted)
            
    # Group deposits by their group ID
    grouped_deposits = {}
    for dep in classified["deposit"]:
        group_id = dep.get("group")
        if group_id:
            if group_id not in grouped_deposits:
                grouped_deposits[group_id] = []
            grouped_deposits[group_id].append(dep)
        else:
            # If a deposit somehow has no group, just keep it as a single-element list
            grouped_deposits[dep.get("id")] = [dep]
            
    # Replace the flat list with a list of grouped transactions
    classified["deposit"] = list(grouped_deposits.values())
            
    return classified

def save_results(classified_data, output_file):
    """Save the classified and extracted data to a JSON file."""
    with open(output_file, 'w') as f:
        json.dump(classified_data, f, indent=4)
    print(f"● Results saved to {output_file}.")

def get_contract_address_from_env():
    """Attempt to load the contract address from the frontend .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("REACT_APP_CONTRACT_ADDRESS="):
                        return line.split("=")[1].strip().strip('"').strip("'")
        except Exception as e:
            print(f"Error reading .env file: {e}")
    return None

def main():
    parser = argparse.ArgumentParser(description="Obscura Inspector: Transaction Analyzer")
    parser.add_argument("address", type=str, nargs="?", help="Contract address to analyze (optional, defaults to frontend/.env)")
    parser.add_argument("--output", type=str, default="transactions.json", help="Output JSON file")
    
    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    contract_address = args.address
    if not contract_address:
        contract_address = get_contract_address_from_env()
        
    if not contract_address:
        print("Error: No contract address. Pass the optional positional [address] or set REACT_APP_CONTRACT_ADDRESS in frontend/.env.")
        print("usage: obscura_inspector.py [-h] [--output OUTPUT] [address]")
        return
        
    print(f"● Contract Address: {contract_address}")
    
    # 1. Fetch (Indexer only)
    txns = fetch_transactions(contract_address)
        
    if not txns:
        print("● No transactions found.")
        return
        
    # 2. Classify & Extract & Normalize
    classified_data = classify_transactions(txns, contract_address)
    
    print(f"● Classification Results:")
    print(f"  Deposits: {len(classified_data['deposit'])}")
    print(f"  Withdrawals: {len(classified_data['withdraw'])}")
    print(f"  Fund Contract: {len(classified_data['fund_contract'])}")
    print(f"  Other: {len(classified_data['other'])}")
    
    # 3. Save
    out_path = os.path.join(script_dir, args.output)
    save_results(classified_data, out_path)

if __name__ == "__main__":
    main()
