#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 Navid Azimi

"""
Obscura Smart Contract Verifier

This script checks whether the Obscura application already deployed on chain matches the local PyTeal implementation 
in obscura_contract.py.
It performs the following steps:
1. Reads the application ID from frontend/.env (APP_ID or REACT_APP_MIXER_APP_ID).
   - Optionally uses REACT_APP_ALGOD_SERVER (and tokens) so the same node as the app targets is used for compile and lookups.
2. Connects to that Algod endpoint (default: public TestNet) and loads the deployed approval and clear-state programs as bytecode.
3. Compiles local approval and clear-state TEAL from obscura_contract.py through the same node's /v2/teal/compile API.
4. Compares raw bytecode for a deterministic match and prints a concise report (including offsets on mismatch).
"""

from __future__ import annotations

import base64
import binascii
import sys
from pathlib import Path
from typing import Any, Mapping, TypedDict

try:
    from algosdk.error import AlgodHTTPError
except ImportError:  # pragma: no cover

    class AlgodHTTPError(Exception):
        """Substitute base type if algosdk is absent (caller should raise earlier)."""

def project_root() -> Path:
    return Path(__file__).resolve().parent.parent

def load_app_id(env_path: Path) -> int:
    """Read APP_ID (or frontend REACT_APP_MIXER_APP_ID) from a .env file."""
    try:
        from dotenv import dotenv_values
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "● python-dotenv is required. Install dependencies: pip install python-dotenv"
        ) from exc

    if not env_path.is_file():
        raise FileNotFoundError(
            f"● Environment file not found: {env_path}. "
            f"● Expected key APP_ID or REACT_APP_MIXER_APP_ID."
        )

    env: dict[str, str | None] = dotenv_values(env_path)
    for key in ("APP_ID", "REACT_APP_MIXER_APP_ID"):
        raw = env.get(key)
        if raw is not None:
            stripped = raw.strip().strip('"').strip("'")
            if stripped == "":
                continue
            try:
                return int(stripped)
            except ValueError as err:
                raise ValueError(f"● Invalid {key}: {raw!r} (must be an integer)") from err

    raise KeyError(
        f"● No APP_ID or REACT_APP_MIXER_APP_ID in {env_path}"
    )

def load_algod_config(env_path: Path) -> tuple[str, str]:
    """Return (algod_address, token) for TestNet; token is often '' for public nodes."""
    try:
        from dotenv import dotenv_values
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "● python-dotenv is required. Install dependencies: pip install python-dotenv"
        ) from exc

    default_url = "https://testnet-api.algonode.cloud"
    env: dict[str, str | None] = dotenv_values(env_path) if env_path.is_file() else {}
    addr = ((env.get("REACT_APP_ALGOD_SERVER") or "").strip() or default_url).rstrip("/")
    token = (env.get("ALGOD_TOKEN") or env.get("REACT_APP_ALGOD_TOKEN") or "").strip()
    return addr, token

def make_algod_client(algod_address: str, algod_token: str):
    """Build an algosdk v2 Algod client."""
    try:
        from algosdk.v2client.algod import AlgodClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "● algosdk is required. Install: pip install py-algorand-sdk"
        ) from exc

    return AlgodClient(algod_token, algod_address)

def _application_params(application_info: dict[str, Any]) -> dict[str, Any]:
    app = application_info.get("application")
    if isinstance(app, dict):
        params = app.get("params")
        if isinstance(params, dict):
            return params
    params = application_info.get("params")
    if isinstance(params, dict):
        return params
    raise ValueError(
        "● Unexpected algod application_info payload: missing application.params"
    )

def _b64_program_to_bytes(blob: Any, field_name: str) -> bytes:
    if not isinstance(blob, str) or not blob:
        raise ValueError(f"● Missing or invalid {field_name} in application params")
    raw_ascii = blob.encode("ascii")
    try:
        return base64.b64decode(raw_ascii, validate=True)
    except binascii.Error:
        # Some gateways may omit strict padding / charset; fallback for robustness.
        return base64.b64decode(raw_ascii, validate=False)

def fetch_onchain_program(
    client, app_id: int
) -> tuple[bytes, bytes]:
    """Return (approval bytecode, clear state bytecode) for the deployed app."""
    info = client.application_info(app_id)
    params = _application_params(info)

    def pick_program(*candidate_names: str) -> tuple[str, Any]:
        for name in candidate_names:
            blob = params.get(name)
            if blob:
                return name, blob
        raise KeyError(
            "● Application params omit one of: "
            + ", ".join(candidate_names)
        )

    appr_name, appr_blob = pick_program("approval-program", "approval_program", "approvalProgram")
    clr_name, clr_blob = pick_program(
        "clear-state-program",
        "clear_state_program",
        "clearStateProgram",
    )
    approval = _b64_program_to_bytes(appr_blob, appr_name)
    clear_prog = _b64_program_to_bytes(clr_blob, clr_name)
    return approval, clear_prog

def _compile_result_bytes(resp: Mapping[str, Any], label: str) -> bytes:
    b64_result = resp.get("result")
    if not b64_result:
        raise RuntimeError(
            f"● Algod compile response for {label} missing 'result' key: {resp!r}"
        )
    raw = b64_result.encode("ascii")
    try:
        return base64.b64decode(raw, validate=True)
    except binascii.Error:
        return base64.b64decode(raw, validate=False)

def compile_teal_sources(client, approval_teal: str, clear_teal: str) -> tuple[bytes, bytes]:
    """Compile TEAL text via algod (/v2/teal/compile) and return bytecode."""
    approve_resp = client.compile(approval_teal)
    clear_resp = client.compile(clear_teal)
    approve_bytes = _compile_result_bytes(approve_resp, "approval TEAL")
    clear_bytes = _compile_result_bytes(clear_resp, "clear TEAL")
    return approve_bytes, clear_bytes

def compile_local_program(
    client,
    approval_teal: str,
    clear_teal: str,
) -> tuple[bytes, bytes]:
    """Compile local TEAL text via the same algod node used for fetching on-chain data."""
    return compile_teal_sources(client, approval_teal, clear_teal)

def describe_bytecode_mismatch(on_chain: bytes, local: bytes) -> str:
    lines = [
        f"   - On-chain bytecode length: {len(on_chain)} bytes",
        f"   - Local bytecode length: {len(local)} bytes",
    ]
    mismatched_at = None
    upto = min(len(on_chain), len(local))
    for i in range(upto):
        if on_chain[i] != local[i]:
            mismatched_at = i
            break

    if mismatched_at is not None:
        c_snip = on_chain[mismatched_at : mismatched_at + 8].hex()
        l_snip = local[mismatched_at : mismatched_at + 8].hex()
        lines.append(
            f"   - First differing byte at offset {mismatched_at}: "
            f"on-chain 0x{c_snip}… vs local 0x{l_snip}…"
        )
        return "\n".join(lines)

    if len(on_chain) == len(local):
        lines.append("   - Byte lengths match but mismatch scan failed.")
    else:
        lines.append(
            "   - Prefix is identical between both programs; differs only by length/trailing bytes."
        )
    return "\n".join(lines)

class ProgramCompareReport(TypedDict):
    approval_match: bool
    clear_match: bool
    approval_detail: str
    clear_detail: str

def compare_programs(
    on_approval: bytes,
    local_approval: bytes,
    on_clear: bytes,
    local_clear: bytes,
) -> ProgramCompareReport:
    approval_match = on_approval == local_approval
    clear_match = on_clear == local_clear
    return ProgramCompareReport(
        approval_match=approval_match,
        clear_match=clear_match,
        approval_detail=(
            ""
            if approval_match
            else describe_bytecode_mismatch(on_approval, local_approval)
        ),
        clear_detail=(
            "" if clear_match else describe_bytecode_mismatch(on_clear, local_clear)
        ),
    )

def import_contract_compiler():
    """Load compile_obscura_contract from the contract package directory."""
    contract_dir = Path(__file__).resolve().parent
    if str(contract_dir) not in sys.path:
        sys.path.insert(0, str(contract_dir))
    try:
        from obscura_contract import compile_obscura_contract
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "● Could not import obscure_contract.compile_obscura_contract. "
            "● Run from the repo with contract/obscura_contract.py present."
        ) from exc
    return compile_obscura_contract

def main() -> int:
    root = project_root()
    env_path = root / "frontend" / ".env"
    algod_url = ""

    try:
        app_id = load_app_id(env_path)
        algod_url, algod_token = load_algod_config(env_path)
        client = make_algod_client(algod_url, algod_token)

        on_app, on_clear = fetch_onchain_program(client, app_id)

        compile_obscura = import_contract_compiler()
        approval_teal, clear_teal = compile_obscura()
        local_app, local_clear = compile_local_program(
            client,
            approval_teal,
            clear_teal,
        )
        report = compare_programs(on_app, local_app, on_clear, local_clear)

    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 1
    except AlgodHTTPError as err:
        print(
            "● Algod HTTP error — check APP_ID / network connectivity / algod URL.\n",
            err,
            file=sys.stderr,
            sep="",
        )
        return 1
    except (ConnectionError, TimeoutError) as err:
        suffix = algod_url or "algod endpoint from frontend/.env"
        print(f"● Network error talking to Algorand ({suffix}): {err}", file=sys.stderr)
        return 1
    except KeyError as err:
        print(f"● Configuration or API shape error: {err}", file=sys.stderr)
        return 1
    except ValueError as err:
        print(f"● Invalid data from network or compiler: {err}", file=sys.stderr)
        return 1
    except RuntimeError as err:
        print(err, file=sys.stderr)
        return 1

    matched = report["approval_match"] and report["clear_match"]

    print(f"● App ID: {app_id} (algod {algod_url})")
    print("● Compared raw program bytes produced by `/v2/teal/compile` on that node.")

    if matched:
        print("   - Match: approval and clear-state bytecode identical to deployed app.")
        return 0

    print(
        "   - Mismatch: compiled local bytecode differs from on-chain bytecode."
    )
    if not report["approval_match"]:
        print("\n● Approval program differences:")
        print(report["approval_detail"])
    if not report["clear_match"]:
        print("\n● Clear-state program differences:")
        print(report["clear_detail"])
    print(
        "\n● Hint: bytecode is compiler-version sensitive; mismatches sometimes indicate "
        "different contract sources or deployments against a different algod/teal semantics."
    )
    return 1

if __name__ == "__main__":
    sys.exit(main())
