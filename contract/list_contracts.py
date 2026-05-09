#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 Navid Azimi

"""
Obscura Deployed Contracts Lister

This utility script queries the Algorand TestNet to list all smart contracts
(applications) created by a specific deployer address. It automatically fetches
the deployer address from the frontend's .env file (REACT_APP_DEPLOYER_ADDRESS)
if no address is provided as a command-line argument.
"""

import sys
import os
from datetime import datetime, timezone
from algosdk.v2client import algod, indexer

def get_deployer_address_from_env():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        env_path = os.path.join(project_root, 'frontend', '.env')
        
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_DEPLOYER_ADDRESS='):
                    return line.split('=')[1].strip()
    except Exception:
        pass
    return None

algod_client = algod.AlgodClient("", "https://testnet-api.algonode.cloud")
indexer_client = indexer.IndexerClient("", "https://testnet-idx.algonode.cloud")

# --------------------------------------------------
# Find apps created by account
# --------------------------------------------------
def find_my_apps(deployer_address):

    account_info = algod_client.account_info(deployer_address)

    print(f"\n● Applications (contracts) created by:")
    print(deployer_address)
    print("-" * 60)

    apps = account_info.get("created-apps", [])

    if not apps:
        print("No created applications found.")
        return

    print(f"{'App ID':<15} {'Created Time'}")
    print("-" * 60)

    for app in apps:

        app_id = app["id"]

        try:
            txns = indexer_client.search_transactions(
                application_id=app_id,
                txn_type="appl",
                limit=1
            )

            tx_list = txns.get("transactions", [])

            if tx_list:
                ts = tx_list[0].get("round-time")

                created_time = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC")

            else:
                created_time = "unknown"

            print(f"{app_id:<15} {created_time}")

        except Exception as e:
            print(f"{app_id:<15} error: {e}")

# --------------------------------------------------
# Entry
# --------------------------------------------------
if __name__ == "__main__":

    addr = sys.argv[1] if len(sys.argv) == 2 else get_deployer_address_from_env()
    
    if not addr:
        print("Error: No deployer address provided and could not find REACT_APP_DEPLOYER_ADDRESS in frontend/.env")
        sys.exit(1)

    find_my_apps(addr)
