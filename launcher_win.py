#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
# Copyright (C) 2026 N. Azimi

"""
Obscura Windows launcher: opens separate PowerShell consoles for contract, backend, and frontend.

This script is intended for use on Windows from the project root. Each stage runs in its own
window with the `obscura` Conda environment activated (via `conda shell.powershell` hook),
then `cd` into `contract/`, `core/`, or `frontend/` and runs the commands there.

- Contract: `bootstrap_contract.py` then `list_contracts.py`. Optionally waits until a
  `done.flag` file is created in `contract/` so later stages can start after setup finishes.
- Backend: `core/backend_server.py`.
- Frontend: `npm run build` then `npm start` in `frontend/`.
"""

import os
import subprocess
import time

def run_terminal(title, path, commands, wait_for_completion=False):
    flag_file = os.path.join(path, "done.flag")
    
    # If we are waiting for this one, we tell PowerShell to create a file when done
    if wait_for_completion:
        if os.path.exists(flag_file): os.remove(flag_file)
        # Add a command to create the flag file after the python scripts finish
        commands += f'; New-Item -Path "{flag_file}" -ItemType "file"'

    ps_command = f"""
$Host.UI.RawUI.WindowTitle = "{title}";
(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression;
conda activate obscura;
cd "{path}";
{commands}
"""

    subprocess.Popen([
        "powershell",
        "-NoExit",
        "-Command",
        ps_command
    ], creationflags=subprocess.CREATE_NEW_CONSOLE)

    # Monitor for the flag file instead of the process itself
    if wait_for_completion:
        print(f"[*] Waiting for {title} scripts to finish...")
        while not os.path.exists(flag_file):
            time.sleep(1) # Check every second
        os.remove(flag_file) # Clean up
        print(f"[!] {title} finished! Proceeding...")

if __name__ == "__main__":
    base_dir = os.getcwd()
    contract_path = os.path.join(base_dir, "contract")
    backend_path = os.path.join(base_dir, "core")
    frontend_path = os.path.join(base_dir, "frontend")

    # -------- 1. CONTRACT --------
    # Window stays open, but Python continues once bootstrap/list are done
    run_terminal(
        "CONTRACT",
        contract_path,
        "python bootstrap_contract.py; python list_contracts.py",
        wait_for_completion=True
    )

    # -------- 2. BACKEND --------
    run_terminal("BACKEND", backend_path, "python backend_server.py")

    # -------- 3. FRONTEND --------
    run_terminal("FRONTEND", frontend_path, "npm run build; npm start")

    print("[+] All systems running.")
