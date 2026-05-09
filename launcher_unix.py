#!/usr/bin/env python3
"""
Obscura Unix launcher: opens separate terminal windows for contract, backend, and frontend.
Works on Ubuntu (Linux) and macOS.
"""

import os
import subprocess
import time
import sys

def run_terminal(title, path, commands, wait_for_completion=False):
    flag_file = os.path.join(path, "done.flag")
    
    if wait_for_completion:
        if os.path.exists(flag_file): os.remove(flag_file)
        # Append flag creation to the shell command
        commands += f' && touch "{flag_file}"'

    # The shell script to execute inside the new terminal
    # We use 'bash -i' to ensure .bashrc is sourced, or manually call conda init logic
    full_command = f'cd "{path}" && eval "$(conda shell.bash hook)" && conda activate obscura && {commands}; exec bash'

    if sys.platform == "darwin":
        # macOS: Use AppleScript to open a new Terminal window
        osascript = f'tell application "Terminal" to do script "{full_command}"'
        subprocess.Popen(["osascript", "-e", osascript])
        
    else:
        # Linux (Ubuntu): Usually gnome-terminal. 
        # If gnome-terminal isn't present, you might need xterm or konsole.
        try:
            subprocess.Popen([
                "gnome-terminal", 
                "--title", title, 
                "--", "bash", "-c", full_command
            ])
        except FileNotFoundError:
            # Fallback for other Linux distros using xterm
            subprocess.Popen([
                "xterm", "-T", title, "-e", f"bash -c '{full_command}'"
            ])

    if wait_for_completion:
        print(f"[*] Waiting for {title} scripts to finish...")
        while not os.path.exists(flag_file):
            time.sleep(1)
        os.remove(flag_file)
        print(f"[!] {title} finished! Proceeding...")

if __name__ == "__main__":
    base_dir = os.getcwd()
    contract_path = os.path.join(base_dir, "contract")
    backend_path = os.path.join(base_dir, "core")
    frontend_path = os.path.join(base_dir, "frontend")

    # 1. CONTRACT (Optional wait)
    run_terminal("CONTRACT", contract_path, "python3 bootstrap_contract.py && python3 list_contracts.py", wait_for_completion=True)

    # 2. BACKEND
    run_terminal("BACKEND", backend_path, "python3 backend_server.py")

    # 3. FRONTEND
    run_terminal("FRONTEND", frontend_path, "npm run build && npm start")

    print("[+] All systems running in separate windows.")
