#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 N. Azimi

"""
BN254 Elliptic Curve Math Operations

This module provides basic elliptic curve operations (point addition and scalar multiplication)
over the BN254 curve, which is natively supported by the Algorand Virtual Machine (AVM).
"""

p = 21888242871839275222246405745257275088696311157297823662689037894645226208583
q = 21888242871839275222246405745257275088548364400416034343698204186575808495617

G = (1, 2)
H = (3, 15623653055687506787251894162198937787223604445717050005178866010732071291759)

def point_add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and y1 == y2:
        if y1 == 0: return None
        m = (3 * x1 * x1) * pow(2 * y1, p - 2, p)
    else:
        if x1 == x2: return None
        m = (y2 - y1) * pow(x2 - x1, p - 2, p)
    m = m % p
    x3 = (m * m - x1 - x2) % p
    y3 = (m * (x1 - x3) - y1) % p
    return (x3, y3)

def point_mul(pt, scalar):
    if scalar == 0 or pt is None:
        return None
    scalar = scalar % q
    result = None
    addend = pt
    while scalar:
        if scalar & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        scalar >>= 1
    return result

def point_to_bytes(pt):
    if pt is None:
        return b'\x00' * 64
    return pt[0].to_bytes(32, 'big') + pt[1].to_bytes(32, 'big')

def bytes_to_point(b):
    if len(b) != 64: raise ValueError("Point must be 64 bytes")
    x = int.from_bytes(b[:32], 'big')
    y = int.from_bytes(b[32:], 'big')
    if x == 0 and y == 0: return None
    return (x, y)
