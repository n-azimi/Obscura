#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 Navid Azimi

"""
Obscura Core Backend (Flask)

HTTP API for the web app: on-chain pool statistics, Pedersen commitment helpers,
and ring-signature / proof packing for Obscura withdrawals. Configuration is read
from `../frontend/.env` (app id, contract address, Algod URL).

Routes:
- GET  /api/monitor         — contract balance, commitment/nullifier box counts, unspent UTXOs, recommended/effective ring size
- POST /generate_proof      — build LSAG proof bytes for a withdrawal (expects secret, recipient, ring commitments)
- POST /compute_commitment  — derive commitment hex from a deposit secret

Run: python backend_server.py  (listens on port 5000 by default)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import base64
from dotenv import load_dotenv
from algosdk.v2client import algod
from obscura_engine import ZKLSAGSystem
from algosdk.encoding import decode_address

# Load .env from the frontend directory
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', '.env')
load_dotenv(env_path)

APP_ID = int(os.getenv("REACT_APP_MIXER_APP_ID", 0))
APP_ADDRESS = os.getenv("REACT_APP_CONTRACT_ADDRESS", "")
ALGOD_SERVER = os.getenv("REACT_APP_ALGOD_SERVER", "https://testnet-api.algonode.cloud")

algod_client = algod.AlgodClient("", ALGOD_SERVER, headers={"X-API-Key": ""})

def fetch_contract_state():
    try:
        account_info = algod_client.account_info(APP_ADDRESS)
        balance_algo = account_info.get("amount", 0) / 1_000_000
    except Exception:
        balance_algo = 0.0

    commitments = 0
    nullifiers = 0
    try:
        boxes_response = algod_client.application_boxes(APP_ID)
        for box in boxes_response.get("boxes", []):
            name_bytes = base64.b64decode(box["name"])
            if name_bytes.startswith(b'c'):
                commitments += 1
            elif name_bytes.startswith(b'n'):
                nullifiers += 1
    except Exception:
        pass

    unspent = commitments - nullifiers
    return balance_algo, commitments, nullifiers, unspent

app = Flask(__name__)
CORS(app)
zk = ZKLSAGSystem()

@app.route('/api/monitor', methods=['GET'])
def get_monitor_data():
    try:
        balance, deposits, withdrawals, unspent = fetch_contract_state()
        
        recommended_ring = min(unspent, 5)
        if recommended_ring < 0:
            recommended_ring = 0

        return jsonify({
            'success': True,
            'data': {
                'balance': balance,
                'deposits': deposits,
                'withdrawals': withdrawals,
                'unspent': unspent,
                'recommendedRing': recommended_ring,
                'effectiveRing': recommended_ring,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate_proof', methods=['POST'])
def generate_proof():
    data = request.json
    try:
        secret = data['secret']
        recipient = data['recipient']
        commitments = data['commitments']
        commitment = data['commitment']
        
        # recipient to hex
        recipient_bytes = decode_address(recipient)
        recipient_hex = recipient_bytes.hex()
        
        signer_index = commitments.index(commitment)
        
        sig = zk.generate_ring_signature(secret, commitments, signer_index, recipient_hex)
        
        # Generate the compact proof formatted for PyTeal
        num_members = len(commitments)
        proof_bytes = bytes([num_members])
        for c in commitments:
            proof_bytes += bytes.fromhex(c)
        proof_bytes += bytes.fromhex(sig['c0'][2:])
        for s in sig['s']:
            proof_bytes += bytes.fromhex(s[2:])
            
        return jsonify({
            'success': True,
            'nullifier': sig['nullifier'],
            'proof': proof_bytes.hex()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/compute_commitment', methods=['POST'])
def compute_commitment():
    data = request.json
    try:
        secret = data['secret']
        commitment = zk.compute_commitment(secret)
        return jsonify({'success': True, 'commitment': commitment})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    app.run(port=5000)
