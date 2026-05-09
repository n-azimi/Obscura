#!/usr/bin/env python3
"""
Obscura Engine: Core Cryptographic Protocol

This module implements the privacy-preserving cryptographic engine for Obscura,
utilizing Linkable Spontaneous Anonymous Group (LSAG) Ring Signatures over the BN254 curve.

Key Security Properties:
1. Soundness: A malicious prover cannot create a valid proof without knowing the secret.
2. Zero-Knowledge: The proof reveals nothing about the secret or which commitment is being claimed.
3. Unlinkability: Observers cannot link withdrawal transactions to deposit transactions.
4. Double-Spend Protection: Uses a unique Key Image (Nullifier) mathematically bound to the deposit.

Protocol:
- Deposit: commitment (64 bytes) = secret * G
- Withdrawal: Ring signature proving knowledge of secret corresponding to one of N commitments,
  along with key image (nullifier) I = secret * H
"""

import hashlib
import secrets
from typing import Dict, List
import bn_254 as curve

class ZKLSAGSystem:
    def __init__(self):
        self.q = curve.q
        self.G = curve.G
        self.H = curve.H
    
    def generate_secret(self) -> str:
        """Generate cryptographically secure secret (private key) for deposit"""
        # Secret must be < q
        secret = secrets.randbelow(self.q)
        return f"0x{secret:064x}"
    
    def compute_commitment(self, secret: str) -> str:
        """
        Compute Pedersen commitment on BN254: C = secret * G
        (Since this is an LSAG over single keys, the commitment is just the public key)
        """
        self._validate_hex_format(secret, "secret")
        secret_int = int(secret[2:], 16)
        
        C = curve.point_mul(self.G, secret_int)
        return curve.point_to_bytes(C).hex()
    
    def compute_nullifier(self, secret: str) -> str:
        """
        Compute key image (nullifier): I = secret * H
        This is revealed during withdrawal (prevents double-spend)
        """
        self._validate_hex_format(secret, "secret")
        secret_int = int(secret[2:], 16)
        
        I = curve.point_mul(self.H, secret_int)
        return curve.point_to_bytes(I).hex()
    
    def hash_to_scalar(self, data: bytes) -> int:
        """Hash bytes to a scalar in Z_q by masking top bits"""
        h = hashlib.sha256(data).digest()
        val = int.from_bytes(h, 'big')
        mask = int("1F" + "FF" * 31, 16)
        return val & mask
    
    def generate_ring_signature(
        self,
        secret: str,
        commitments: List[str],
        signer_index: int,
        message: str
    ) -> Dict:
        """
        Generate a Linkable Ring Signature (Abe-Ohkubo-Suzuki style)
        
        Proves knowledge of the secret for commitments[signer_index] and that
        the nullifier I = secret * H corresponds to it.
        """
        n = len(commitments)
        if n == 0: raise ValueError("Ring cannot be empty")
        if signer_index >= n: raise ValueError("Invalid signer index")
        
        secret_int = int(secret[2:], 16)
        I = curve.point_mul(self.H, secret_int)
        I_bytes = curve.point_to_bytes(I)
        
        msg_bytes = bytes.fromhex(message)
        
        # Parse commitments
        ring = []
        for c in commitments:
            ring.append(curve.bytes_to_point(bytes.fromhex(c)))
            
        alpha = secrets.randbelow(self.q)
        
        # c array and s array
        c = [0] * n
        s = [0] * n
        
        L_pi = curve.point_mul(self.G, alpha)
        R_pi = curve.point_mul(self.H, alpha)
        
        # Compute c_{pi+1}
        c[(signer_index + 1) % n] = self.hash_to_scalar(
            msg_bytes + curve.point_to_bytes(L_pi) + curve.point_to_bytes(R_pi)
        )
        
        # Iterate from pi+1 to pi-1
        for i in range(signer_index + 1, signer_index + n):
            idx = i % n
            s[idx] = secrets.randbelow(self.q)
            
            # L_i = s_i * G + c_i * P_i
            sG = curve.point_mul(self.G, s[idx])
            cP = curve.point_mul(ring[idx], c[idx])
            L_i = curve.point_add(sG, cP)
            
            # R_i = s_i * H + c_i * I
            sH = curve.point_mul(self.H, s[idx])
            cI = curve.point_mul(I, c[idx])
            R_i = curve.point_add(sH, cI)
            
            c[(idx + 1) % n] = self.hash_to_scalar(
                msg_bytes + curve.point_to_bytes(L_i) + curve.point_to_bytes(R_i)
            )
            
        # Finally, solve for s_{pi}
        # s_pi = alpha - c_pi * secret (mod q)
        s[signer_index] = (alpha - c[signer_index] * secret_int) % self.q
        
        return {
            'nullifier': I_bytes.hex(),
            'c0': f"0x{c[0]:064x}",
            's': [f"0x{si:064x}" for si in s]
        }
        
    def verify_ring_signature(
        self,
        signature: Dict,
        commitments: List[str],
        message: str
    ) -> bool:
        """Verify the Linkable Ring Signature"""
        n = len(commitments)
        I = curve.bytes_to_point(bytes.fromhex(signature['nullifier']))
        c0 = int(signature['c0'][2:], 16)
        s = [int(si[2:], 16) for si in signature['s']]
        
        msg_bytes = bytes.fromhex(message)
        
        ring = [curve.bytes_to_point(bytes.fromhex(c)) for c in commitments]
        
        c_current = c0
        for i in range(n):
            # L_i = s_i * G + c_i * P_i
            sG = curve.point_mul(self.G, s[i])
            cP = curve.point_mul(ring[i], c_current)
            L_i = curve.point_add(sG, cP)
            
            # R_i = s_i * H + c_i * I
            sH = curve.point_mul(self.H, s[i])
            cI = curve.point_mul(I, c_current)
            R_i = curve.point_add(sH, cI)
            
            c_current = self.hash_to_scalar(
                msg_bytes + curve.point_to_bytes(L_i) + curve.point_to_bytes(R_i)
            )
            
        return c_current == c0

    def generate_compact_proof(self, signature: Dict, ring_indices: List[int]) -> str:
        """
        Encode proof for on-chain verification
        Format:
        [num_ring_members(1 byte)]
        [ring_index_0(4 bytes)] ... [ring_index_n(4 bytes)]
        [c0(32 bytes)]
        [s0(32 bytes)] ... [sn(32 bytes)]
        """
        n = len(ring_indices)
        res = bytes([n])
        for idx in ring_indices:
            res += idx.to_bytes(4, 'big')
        
        res += bytes.fromhex(signature['c0'][2:])
        for si in signature['s']:
            res += bytes.fromhex(si[2:])
            
        return res.hex()

    def _validate_hex_format(self, value: str, name: str):
        if not value.startswith('0x') or len(value) != 66:
            raise ValueError(
                f"Invalid {name} format: expected '0x' + 64 hex chars, got {len(value)} chars"
            )

def test_proof_system():
    zk = ZKLSAGSystem()
    print("=" * 60)
    print("● ZK RING SIGNATURE TEST")
    print("=" * 60)
    
    # 1. Setup Ring
    secrets_list = [zk.generate_secret() for _ in range(5)]
    commitments = [zk.compute_commitment(s) for s in secrets_list]
    
    # Signer chooses index 2
    signer_index = 2
    secret = secrets_list[signer_index]
    
    message = "00" * 32 # Dummy recipient or message
    
    # 2. Generate Proof
    print(f"● Generating Ring Signature for Anonymity Set Size = {len(commitments)}")
    sig = zk.generate_ring_signature(secret, commitments, signer_index, message)
    nullifier = sig['nullifier']
    
    print(f"● Nullifier (Public): {nullifier[:32]}...")
    print(f"  c0: {sig['c0']}")
    
    # 3. Verify Proof
    is_valid = zk.verify_ring_signature(sig, commitments, message)
    print(f"● Verification Result: {is_valid}")
    
    compact = zk.generate_compact_proof(sig, list(range(5)))
    print(f"● Compact proof size: {len(compact)//2} bytes")
    
    assert is_valid, "● Ring signature failed to verify."

if __name__ == "__main__":
    test_proof_system()
