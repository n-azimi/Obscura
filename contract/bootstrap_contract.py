#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 N. Azimi

"""
Obscura Smart Contract Bootstrapper

This script automates the deployment and initial funding of the Obscura contract.
It performs the following steps:
1. Prompts for existing deployer credentials or generates a new Algorand account.
   - If a new account is generated, it displays a QR code to fund it with 0.6 ALGO.
2. Deploys a dummy application (used for Inner OpUps to dynamically expand opcode budget).
3. Deploys the main Obscura contract with Box Storage support for unlimited scalability.
4. Automatically funds the deployed contract with 0.2 ALGO to cover withdrawal transaction fees.
5. Generates and saves the necessary environment variables (.env) for the frontend.
"""

from algosdk import account, mnemonic, constants, transaction
from algosdk.v2client import algod
from algosdk.logic import get_application_address
from pyteal import compileTeal, Mode, Return, Int
from obscura_contract import compile_obscura_contract
import base64
import os
import qrcode
from datetime import datetime, timezone

def get_deployer_credentials():
    """Get deployer credentials securely"""
    print("-" * 90)
    
    # Option 1: Use existing mnemonic
    print("● Do you have an existing Algorand account mnemonic?")
    user_input = input("  Enter 'y', 'n', or paste your mnemonic directly: ").strip()
    
    # Handle case where user pastes mnemonic directly
    is_mnemonic_paste = len(user_input.split()) > 10
    
    if user_input.lower() == 'y' or is_mnemonic_paste:
        if is_mnemonic_paste:
            deployer_mnemonic = user_input
            print("  [OK] Mnemonic detected from input")
        else:
            print("  Enter your 25-word mnemonic phrase:")
            print("  (You can paste it all at once, separated by spaces)")
            deployer_mnemonic = input("  Mnemonic: ").strip()
        
        # Validate mnemonic
        try:
            deployer_private_key = mnemonic.to_private_key(deployer_mnemonic)
            deployer_address = account.address_from_private_key(deployer_private_key)
            print(f"  [OK] Valid mnemonic for address: {deployer_address}")
            return deployer_private_key, deployer_address
        except Exception as e:
            print(f"  [ERROR] Invalid mnemonic: {e}")
            return None, None
    
    # Option 2: Generate new account
    else:
        print("● Generating new Algorand account...")
        deployer_private_key, deployer_address = account.generate_account()
        deployer_mnemonic = mnemonic.from_private_key(deployer_private_key)
        
        print(f"  [OK] New account generated: {deployer_address}")
        print("\n" + "="*90)
        print("● IMPORTANT: STORE THIS MNEMONIC SECURELY")
        print("="*90)
        print(deployer_mnemonic)
        print("="*90)
        
        input("\n● Press Enter after you've saved the mnemonic phrase...")
        
        print(f"● New account needs funding for contract deployment and initial contract funding.")
        print(f"  Please fund the account with at least 0.6 ALGO.")
        print(f"  Address: {deployer_address}")
        
        try:
            qr_data = f"algorand://{deployer_address}?amount=600000"
            qr = qrcode.make(qr_data)
            print("  Opening QR code... Please scan with your Algorand wallet to fund.")
            qr.show()
        except Exception as e:
            print(f"  Note: Could not display QR code: {e}")
            
        input("\n● Press Enter after you have funded the account and closed the QR code...")
        
        return deployer_private_key, deployer_address

def check_algorand_connection(algod_client):
    """Check connection to Algorand network"""
    try:
        status = algod_client.status()
        print(f"  [OK] Connected to Algorand TestNet")
        print(f"       Last round: {status.get('last-round', 'N/A')}")
        return True
        
    except Exception as e:
        print(f"  [ERROR] Failed to connect to Algorand: {e}")
        return False

def check_account_balance(algod_client, address):
    """Check if account has sufficient balance for deployment and funding"""
    try:
        account_info = algod_client.account_info(address)
        balance = account_info['amount']
        min_balance = account_info.get('min-balance', 100000)
        available = balance - min_balance
        
        print(f"       Account balance: {balance / 1_000_000:.6f} ALGO")
        print(f"       Available: {available / 1_000_000:.6f} ALGO")
        
        # We need ~0.002 ALGO for deployment fees + 0.2 ALGO to fund the contract + ~0.2785 ALGO extra min balance for creating apps
        if available < 500_000:
            print(f"\n● Low balance detected. You need at least 0.6 ALGO to deploy and fund.")
            print(f"  Address: {address}")
            
            proceed = input("\n● Proceed anyway? (y/n): ").lower().strip()
            return proceed == 'y'
        
        return True
        
    except Exception as e:
        print(f"  [WARNING] Could not check balance: {e}")
        proceed = input("● Proceed with deployment anyway? (y/n): ").lower().strip()
        return proceed == 'y'

def fund_contract(algod_client, sender_private_key, sender_address, contract_address, amount_algos=0.2):
    """Fund the contract with the specified amount of ALGOs directly from deployer"""
    print(f"\n● Funding contract with {amount_algos} ALGOs...")
    
    try:
        sender_info = algod_client.account_info(sender_address)
        
        if sender_info['amount'] < (amount_algos * 1000000 + 1000):
            print("  [ERROR] Sender doesn't have enough funds to fund the contract.")
            print(f"    Required: {(amount_algos * 1000000 + 1000) / 1000000} ALGOs")
            print(f"    Available: {sender_info['amount'] / 1000000} ALGOs")
            return False
            
        params = algod_client.suggested_params()
        
        funding_txn = transaction.PaymentTxn(
            sender=sender_address,
            sp=params,
            receiver=contract_address,
            amt=int(amount_algos * 1000000)
        )
        
        # Sign and submit
        signed_txn = funding_txn.sign(sender_private_key)
        txid = algod_client.send_transaction(signed_txn)
        
        print(f"● Funding transaction submitted. Waiting for confirmation (txid: {txid})...")
        confirmed = transaction.wait_for_confirmation(algod_client, txid, 4)
        
        print(f"  [OK] Contract funded successfully.")
        
        # Check new balance
        contract_info = algod_client.account_info(contract_address)
        print(f"       New contract balance: {contract_info['amount'] / 1000000} ALGOs")
        
        return True
        
    except Exception as e:
        print(f"  [ERROR] Error funding contract: {e}")
        return False

def deploy_and_fund_obscura_contract():
    """Deploy the Obscura contract to Algorand testnet and fund it"""
    
    algod_client = algod.AlgodClient(
        algod_token="",
        algod_address="https://testnet-api.algonode.cloud"
    )
    
    print("● Connecting to Algorand TestNet...")
    if not check_algorand_connection(algod_client):
        return None
    
    deployer_private_key, deployer_address = get_deployer_credentials()
    if not deployer_private_key:
        return None
    
    if not check_account_balance(algod_client, deployer_address):
        return None

    print("-" * 90)
    
    print("● Deploying Obscura contract...")
    
    try:
        print("● Compiling smart contract...")
        approval_teal, clear_teal = compile_obscura_contract()
        
        print("  [OK] Contract compiled to TEAL successfully")
        
        print("● Compiling TEAL to bytecode...")
        approval_result = algod_client.compile(approval_teal)
        approval_binary = base64.b64decode(approval_result['result'])
        
        clear_result = algod_client.compile(clear_teal)
        clear_binary = base64.b64decode(clear_result['result'])
        
        print("  [OK] TEAL compiled to bytecode successfully")
        print(f"       Approval bytecode size: {len(approval_binary)} bytes")
        print(f"       Clear bytecode size: {len(clear_binary)} bytes")
        
        params = algod_client.suggested_params()

        # Deploy dummy app first for opups
        print("● Deploying dummy app for opcode budget...")

        dummy_teal = compileTeal(Return(Int(1)), Mode.Application, version=10)
        dummy_binary = base64.b64decode(algod_client.compile(dummy_teal)['result'])
        
        dummy_create_txn = transaction.ApplicationCreateTxn(
            sender=deployer_address,
            sp=params,
            on_complete=transaction.OnComplete.NoOpOC,
            approval_program=dummy_binary,
            clear_program=dummy_binary,
            global_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
            local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        )
        signed_dummy = dummy_create_txn.sign(deployer_private_key)
        txid_dummy = algod_client.send_transaction(signed_dummy)
        print(f"● Waiting for dummy app deployment (txid: {txid_dummy})...")
        confirmed_dummy = transaction.wait_for_confirmation(algod_client, txid_dummy, 10)
        dummy_app_id = confirmed_dummy["application-index"]
        print(f"  [OK] Dummy App ID: {dummy_app_id}")
        
        # Optimized global state schema + Box Storage for infinite scaling
        print("● Creating main obscura application with Box Storage support...")
        app_create_txn = transaction.ApplicationCreateTxn(
            sender=deployer_address,
            sp=params,
            on_complete=transaction.OnComplete.NoOpOC,
            approval_program=approval_binary,
            clear_program=clear_binary,
            # Minimal global state: 1 uint (leaf_idx), 1 byte slice (root)
            # Commitments and Nullifiers are stored in Boxes (unlimited)
            global_schema=transaction.StateSchema(num_uints=1, num_byte_slices=1),
            local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        )
        
        print("● Signing transaction...")
        signed_txn = app_create_txn.sign(deployer_private_key)
        
        print("● Submitting deployment transaction...")
        txid = algod_client.send_transaction(signed_txn)
        print(f"  [OK] Transaction submitted with ID: {txid}")
        
        print("● Waiting for confirmation...")
        confirmed_txn = transaction.wait_for_confirmation(algod_client, txid, 10)
        
        app_id = confirmed_txn["application-index"]
        
        print("\n" + "="*90)
        print("● DEPLOYMENT SUCCESSFUL")
        print("="*90)
        print(f"App ID: {app_id}")
        print(f"Transaction ID: {txid}")
        print(f"Deployer: {deployer_address}")
        print(f"Confirmed in round: {confirmed_txn['confirmed-round']}")
        
        app_address = get_application_address(app_id)
        print(f"Contract Address: {app_address}")
        print("="*90)
        
        # Fund the contract automatically
        fund_contract(algod_client, deployer_private_key, deployer_address, app_address, amount_algos=0.2)
        
        # Save results
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        
        deployment_info = f"""Obscura Contract Deployment Information
======================================
Deployment Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC

App ID: {app_id}
Transaction ID: {txid}
Deployer Address: {deployer_address}
Contract Address: {app_address}
Network: Algorand Testnet
Block: {confirmed_txn['confirmed-round']}

Explorer Links:
- Application: https://testnet.explorer.perawallet.app/application/{app_id}
- Transaction: https://testnet.explorer.perawallet.app/tx/{txid}
- Contract Address: https://testnet.explorer.perawallet.app/address/{app_address}
======================================
"""
        
        # Convert deployment info to comments
        commented_info = "\n".join([f"# {line}" for line in deployment_info.split("\n")])
        
        env_content = f"""{commented_info}

REACT_APP_MIXER_APP_ID={app_id}
REACT_APP_DUMMY_APP_ID={dummy_app_id}
REACT_APP_DEPLOYER_ADDRESS={deployer_address}
REACT_APP_CONTRACT_ADDRESS={app_address}
REACT_APP_ALGOD_SERVER=https://testnet-api.algonode.cloud
"""
        # Update frontend/.env
        frontend_dir = os.path.join(project_root, "frontend")
        if os.path.exists(frontend_dir):
             frontend_env_path = os.path.join(frontend_dir, ".env")
             with open(frontend_env_path, "w") as f:
                f.write(env_content)
             print(f"● Frontend Environment file created: {frontend_env_path}")
             
             # Save backup with app_id
             backup_env_path = os.path.join(frontend_dir, f"{app_id}.env.bak")
             with open(backup_env_path, "w") as f:
                f.write(env_content)
             print(f"● Backup Environment file created: {backup_env_path}")
        else:
             print(f"● [WARNING] Frontend directory not found at {frontend_dir}, .env not saved.")
        
        return app_id
        
    except Exception as e:
        print(f"  [ERROR] Deployment failed: {e}")
        
        # Specific error handling
        if "insufficient balance" in str(e).lower():
            print("\n● Fund your account with test ALGOs.")
            print(f"   Send to: {deployer_address}")
        
        return None

if __name__ == "__main__":
    print("Obscura Smart Contract Bootstrapper")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("-" * 90)
    
    app_id = deploy_and_fund_obscura_contract()
    
    if app_id:
        print(f"● Obscura contract is deployed and funded.")
        print(f"  App ID: {app_id}")
        print(f"● View the contract:")
        print(f"  https://testnet.explorer.perawallet.app/application/{app_id}")
    else:
        print("\n● Deployment failed. Please try running the script again.")
