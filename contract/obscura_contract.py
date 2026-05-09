#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 Navid Azimi

"""
Obscura Smart Contract

This PyTeal contract implements the core on-chain logic for the Obscura
privacy protocol. It handles:
1. Deposits: Storing Pedersen Commitments in Algorand Box Storage.
2. Withdrawals: Verifying Linkable Spontaneous Anonymous Group (LSAG) Ring
   Signatures over the BN254 elliptic curve to ensure zero-knowledge proofs
   of deposit ownership without revealing the specific deposit.
3. Double-Spend Prevention: Storing and checking Nullifiers in Box Storage.
4. Opcode Budget Management: Using Inner OpUps to dynamically expand the AVM
   opcode budget required for complex elliptic curve math.
"""

from pyteal import *

class Obscura:
    def approval_program(self):
        # Global state keys
        next_leaf_key = Bytes("leaf_idx")
        deposit_amount = Int(1000000)  # 1 ALGO
        min_fee = Int(1000)
        storage_cost = Int(100000)  # 0.1 ALGO to cover box storage MBR
        
        on_creation = Seq([
            App.globalPut(next_leaf_key, Int(0)),
            Return(Int(1))
        ])
        
        # ============================================
        # DEPOSIT FUNCTION
        # ============================================
        # Input: 
        #   app_args[1] = commitment (64 bytes, BN254 point)
        on_deposit = Seq([
            Assert(Global.group_size() == Int(2)),
            Assert(Gtxn[1].type_enum() == TxnType.Payment),
            Assert(Gtxn[1].amount() == deposit_amount),
            Assert(Gtxn[1].receiver() == Global.current_application_address()),
            Assert(Len(Txn.application_args[1]) == Int(64)),
            
            (commitment_box_len := App.box_length(
                Concat(Bytes("c"), Extract(Txn.application_args[1], Int(0), Int(32)))
            )),
            Assert(commitment_box_len.hasValue() == Int(0)),
            
            App.box_put(
                Concat(Bytes("c"), Extract(Txn.application_args[1], Int(0), Int(32))),
                Txn.application_args[1] # Store full 64-byte point
            ),
            
            App.globalPut(next_leaf_key, App.globalGet(next_leaf_key) + Int(1)),
            Return(Int(1))
        ])
        
        # ============================================
        # WITHDRAWAL FUNCTION
        # ============================================
        # Input:
        #   app_args[1] = nullifier_point (64 bytes, BN254 point)
        #   app_args[2] = zk_proof (variable length, LSAG Ring Signature)
        #   app_args[3] = recipient (32 bytes)
        
        zk_proof = Txn.application_args[2]
        recipient = Txn.application_args[3]
        nullifier_point = Txn.application_args[1]
        
        n_members = Btoi(Extract(zk_proof, Int(0), Int(1)))
        
        i = ScratchVar(TealType.uint64)
        c_current = ScratchVar(TealType.bytes)
        
        c_offset = Int(1) + (n_members * Int(64))
        
        G = Bytes("base16", "00000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000002")
        H = Bytes("base16", "0000000000000000000000000000000000000000000000000000000000000003228aac9c1a871e92ed261943a31509ffe43913e8f5350b91fcc9692c5f710b6f")
        mask = Bytes("base16", "1FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF")
        
        p_i = Extract(zk_proof, Int(1) + (i.load() * Int(64)), Int(64))
        s_i = Extract(zk_proof, Int(1) + (n_members * Int(64)) + Int(32) + (i.load() * Int(32)), Int(32))
        
        sG = EcScalarMul(EllipticCurve.BN254g1, G, s_i)
        cP = EcScalarMul(EllipticCurve.BN254g1, p_i, c_current.load())
        L_i = EcAdd(EllipticCurve.BN254g1, sG, cP)
        
        sH = EcScalarMul(EllipticCurve.BN254g1, H, s_i)
        cI = EcScalarMul(EllipticCurve.BN254g1, nullifier_point, c_current.load())
        R_i = EcAdd(EllipticCurve.BN254g1, sH, cI)
        
        h = Sha256(Concat(recipient, L_i, R_i))
        
        loop_body = Seq([
            (box_val := App.box_length(Concat(Bytes("c"), Extract(p_i, Int(0), Int(32))))),
            Assert(box_val.hasValue()),
            c_current.store(BytesAnd(h, mask)),
        ])
        
        on_withdraw = Seq([
            Assert(Len(Txn.application_args[1]) == Int(64)),
            Assert(Len(Txn.application_args[3]) == Int(32)),
            
            # Request extra opcode budget dynamically using inner transactions
            # Each member costs ~11400 ops (4x EcScalarMul). 1 inner app call adds 700 budget.
            # We request 20 inner app calls per member. (20 * 700 = 14000)
            # We call the dummy app provided in Txn.applications[1] to avoid self-call error
            For(i.store(Int(0)), i.load() < (n_members * Int(20)), i.store(i.load() + Int(1))).Do(
                Seq([
                    InnerTxnBuilder.Begin(),
                    InnerTxnBuilder.SetFields({
                        TxnField.type_enum: TxnType.ApplicationCall,
                        TxnField.application_id: Txn.applications[1],
                        TxnField.on_completion: OnComplete.NoOp,
                        TxnField.fee: Int(0) # Fee covered by outer transaction fee pooling
                    }),
                    InnerTxnBuilder.Submit()
                ])
            ),
            
            (nullifier_box_len := App.box_length(
                Concat(Bytes("n"), Extract(Txn.application_args[1], Int(0), Int(32)))
            )),
            Assert(nullifier_box_len.hasValue() == Int(0)),
            
            c_current.store(Extract(zk_proof, c_offset, Int(32))),
            For(i.store(Int(0)), i.load() < n_members, i.store(i.load() + Int(1))).Do(loop_body),
            
            Assert(c_current.load() == Extract(zk_proof, c_offset, Int(32))),
            
            App.box_put(
                Concat(Bytes("n"), Extract(Txn.application_args[1], Int(0), Int(32))),
                Bytes("1")
            ),
            
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: Txn.application_args[3],
                TxnField.amount: deposit_amount - min_fee - storage_cost,
                TxnField.fee: min_fee,
            }),
            InnerTxnBuilder.Submit(),
            Return(Int(1))
        ])
        
        on_get_count = Seq([Return(App.globalGet(next_leaf_key))])
        on_opup = Seq([Return(Int(1))])
        
        program = Cond(
            [Txn.application_id() == Int(0), on_creation],
            [Txn.on_completion() == OnComplete.DeleteApplication, Return(Int(0))],
            [Txn.on_completion() == OnComplete.UpdateApplication, Return(Int(0))],
            [Txn.on_completion() == OnComplete.CloseOut, Return(Int(1))],
            [Txn.on_completion() == OnComplete.OptIn, Return(Int(1))],
            [And(Txn.application_args.length() >= Int(2), Txn.application_args[0] == Bytes("deposit")), on_deposit],
            [And(Txn.application_args.length() >= Int(4), Txn.application_args[0] == Bytes("withdraw")), on_withdraw],
            [Txn.application_args[0] == Bytes("get_count"), on_get_count],
            [Txn.application_args[0] == Bytes("opup"), on_opup],
        )
        
        return program
    
    def clear_state_program(self):
        return Return(Int(1))

def compile_obscura_contract():
    obscura = Obscura()
    approval_teal = compileTeal(obscura.approval_program(), Mode.Application, version=10)
    clear_teal = compileTeal(obscura.clear_state_program(), Mode.Application, version=10)
    return approval_teal, clear_teal

if __name__ == "__main__":
    approval, clear = compile_obscura_contract()
    print("=== APPROVAL PROGRAM ===")
    print(approval)
