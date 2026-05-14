<div align="center">
  <img src="/img/logo.png" alt="Logo" width="180"/>
</div>



## Obscura: Privacy-Preserving Protocol for the Algorand Blockchain Using LSAG Ring Signatures

[![Google Scholar](https://img.shields.io/badge/Google%20Scholar-Paper-4285F4?logo=googlescholar&logoColor=white)](https://scholar.google.com/scholar_lookup?arxiv_id=2605.02077)
[![arXiv](https://img.shields.io/badge/arXiv-2605.02077-b31b1b.svg)](https://arxiv.org/abs/2605.02077)
[![IACR](https://img.shields.io/badge/IACR-2026%2F917-2E2E2E.svg?logo=databricks&logoColor=white)](https://ia.cr/2026/917)
[![Python Version](https://img.shields.io/badge/Python-3.12.12-blue.svg?logo=python&logoColor=white)](#)
[![Node.js Version](https://img.shields.io/badge/Node.js-22.16.0-339933.svg?logo=node.js&logoColor=white)](#)
[![npm](https://img.shields.io/badge/npm-v10.9.2-CB3837.svg?logo=npm&logoColor=white)](#)
[![Algorand Testnet](https://img.shields.io/badge/Blockchain-Algorand%20Testnet-7C3AED.svg?logo=algorand&logoColor=white)](#)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20MacOS%20%7C%20Windows-lightgrey.svg)](#)
[![No Maintenance Intended](https://img.shields.io/badge/Status-Maintained-green.svg)](#)



## 📋 Overview

While public blockchains provide transparent and auditable transaction histories, they inherently compromise user privacy. Existing privacy-enhancing protocols, such as those deployed on Ethereum, typically rely on succinct zero-knowledge proofs (zk-SNARKs) to obscure the transaction graph. However, implementing comparable cryptographic guarantees on high-throughput blockchains like Algorand is challenging due to strict per-call execution budgets and the state contention introduced by global Merkle accumulators. This work presents *Obscura*, a decentralized, non-custodial privacy protocol tailored for constrained smart contract environments. Obscura achieves transaction anonymity using Linkable Spontaneous Anonymous Group (LSAG) signatures over the BN254 elliptic curve, verified entirely on-chain. To overcome limitations of the Algorand Virtual Machine (AVM), we introduce a novel state model that leverages Algorand's Box Storage for $O(1)$ commitment membership checks, eliminating the need for global Merkle accumulators, and a dynamic opcode-budget expansion mechanism via pooled inner application calls. Our implementation demonstrates that signer-ambiguous privacy is practical and efficient on Algorand without relying on trusted setups or succinct proofs. Obscura provides a robust privacy layer for transparent ledgers, bridging the gap between high-throughput blockchain architectures and the dual requirements of cryptographic privacy and selective auditability.

<p align="center">
  <img src="/img/figures/Obscura_end-to-end_architecture.png" alt="Obscura protocol end-to-end architecture" width="500">
  <br>
  Figure 1. Obscura protocol end-to-end architecture
</p>



## 💡 Key Features

- **Linkable Ring Signatures**: Implements Linkable Spontaneous Anonymous Group signatures (LSAG) over the BN254 elliptic curve. Verification is performed natively on-chain using AVM elliptic-curve opcodes (`EcAdd`, `EcScalarMul`). The heavy cryptographic generation *KeyGen* and *Sign* is executed off-chain via a Python-based local prover (`core/obscura_engine.py`).
- **$O(1)$ State Verification via Box Storage**: Eliminates the need for state-heavy global Merkle accumulators. Public commitments ($P = xG$) and key images/nullifiers ($I = xH$) are stored directly in Algorand Box Storage, enabling $O(1)$ membership and double-spend checks.
- **Dynamic Opcode Pooling**: Bypasses the strict per-transaction execution budget of the AVM. The smart contract dynamically expands its computational headroom by issuing $20n$ inner application calls to a stateless dummy application, allowing $O(n)$ signature verification to complete in a single epoch.
- **Privacy-Hardened Client Architecture** (`frontend/src/components/Obscura.tsx`):
  - **Recency-Biased Decoy Selection**: Mitigates temporal intersection attacks by querying the blockchain indexer for recent deposits and drawing decoys from a bounded active window.
  - **Cryptographically Secure Shuffling**: Prevents positional deanonymization by permuting the anonymity set (ring) using a Fisher-Yates shuffle seeded by `crypto.getRandomValues()`.
- **Analytical Tooling**: Includes **Obscura Lens** (a Dash/Cytoscape transaction graph explorer) and **Obscura Inspector** (an indexer-backed transaction classifier) for evaluating ledger state and transaction topology.
- **Automated Bootstrapping**: `contract/bootstrap_contract.py` streamlines deployment by provisioning the dummy and main applications, funding the contract, and configuring the client environment.



## 🏗️ Architecture & Components

The Obscura ecosystem is partitioned into three distinct domains to optimize execution:

1. **Client Application**: The React/TypeScript frontend (`frontend/`) and Pera Wallet. Responsible for querying the blockchain indexer, selecting decoys, constructing the anonymity set, and submitting signed transaction groups to the network.
2. **Local Prover Enclave**: The Flask API and LSAG engine (`core/`). Exposes stateless endpoints (`/generate_proof`, `/compute_commitment`) that perform the heavy BN254 curve arithmetic.
3. **Smart Contract Layer (Algorand AVM)**: The PyTeal contracts (`contract/`). Enforces atomic state transitions, manages Box Storage ($\mathcal{B}_C$ for commitments, $\mathcal{B}_N$ for nullifiers), executes the native LSAG verification loop, and utilizes a dummy application for opcode expansion.

<p align="center">
  <img src="/img/figures/Obscura_implementation_architecture.png" alt="Obscura implementation architecture" width="500">
  <br>
  Figure 2. Obscura implementation architecture
</p>



## 🔄 Workflow

The protocol operates in two primary phases: deposit and withdrawal.

### 1. Deposit Phase (Commitment)
- **Off-Chain**: The client application samples a fresh, uniformly random secret scalar $x$ and requests the public commitment $P = xG$ from the local prover. The secret $x$ is stored securely in local storage.
- **On-Chain**: The user submits an atomic transaction group: `TxGroup[Deposit(P), Pay(1 ALGO)]`. The smart contract asserts that the commitment box $\mathcal{B}_C(P)$ does not exist, allocates it, writes $P$, and increments the global deposit counter.

<p align="center">
  <img src="/img/figures/Deposit_phase_sequence_diagram.png" alt="Deposit phase sequence diagram" width="500">
  <br>
  Figure 3. Deposit phase sequence diagram
</p>

### 2. Withdrawal Phase (Anonymous Spending)
- **Anonymity Set Construction**: The client fetches recent public commitments from the indexer, selects decoys, injects its own $P$, and shuffles the ring $R$.
- **Off-Chain Signing**: The client sends the secret $x$, the ring $R$, and the recipient address $m$ to the local prover. The prover computes the key image $I = xH$ and generates the LSAG signature $\sigma$.
- **On-Chain Verification**: The user submits a single application call: `Withdraw(I, \sigma, m, R)`. The smart contract:
  1. Issues $20n$ inner `opup` calls to expand the opcode budget.
  2. Asserts the nullifier box $\mathcal{B}_N(I)$ does not exist (double-spend prevention).
  3. Asserts all commitment boxes $\mathcal{B}_C(P_i)$ for $P_i \in R$ exist (membership verification).
  4. Executes the native LSAG verification algorithm.
  5. Allocates $\mathcal{B}_N(I)$ to mark the deposit as spent and issues an inner payment to $m$.
 
<p align="center">
  <img src="/img/figures/Withdrawal_phase_sequence_diagram.png" alt="Withdrawal phase sequence diagram" width="500">
  <br>
  Figure 4. Withdrawal phase sequence diagram
</p>



## 🖥️ Deployment

### Testnet Deployment (Current Implementation)
1. **Fund the Deployer**: Ensure your deployer account has sufficient Testnet ALGO for app creation and box storage minimum balance requirements (MBR).
2. **Bootstrap**: Run `python bootstrap_contract.py` in the `contract/` directory. This script deploys the dummy and main applications, funds the contract, and configures `frontend/.env`.
3. **Launch Stack**: Start the Flask prover (`python backend_server.py`) and the React client (`npm start`).

### Mainnet Considerations
This project is **experimental software** designed for research and evaluation on Algorand Testnet. It should **not** be deployed to MainNet without:
- An independent security audit and formal verification.
- Comprehensive economic testing of fee structures and MBR dynamics.
- Legal and regulatory compliance reviews for your jurisdiction.



## ⚙️ Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/n-azimi/Obscura.git
cd Obscura
```

That creates the project root (the directory that contains `requirements.txt`, `contract/`, `core/`, and `frontend/`). If you use a source zip instead of `git clone`, `cd` into the unpacked folder, its name may differ (e.g. `Obscura-3.6.0`).

The following steps assume your shell is in that project root.

### 2. Install Node.js and npm

Ensure you have Node.js (v22.16.0 or compatible) and npm (v10.9.2 or compatible) installed. You can download them from the [official Node.js website](https://nodejs.org/).

### 3. Create and activate the Python environment (Conda)

Use the same conda env anywhere you run Python: `contract/`, `core/`, `tools/`, and the launcher scripts (`launcher_unix.py` / `launcher_win.py`) if you use them.

**First time only**, from the project root:

```bash
conda create -n obscura python=3.12.12
conda activate obscura
```

**Later sessions**, open a shell, then:

```bash
conda activate obscura
```

(If you do not use Conda, create a venv with Python 3.12 and activate it instead, then use `pip` as in the next step.)

### 4. Install dependencies

From the project root, with the python environment activated:

```bash
python -m pip install -r requirements.txt
```

**Frontend (Node.js)**, install the React app’s packages (from the project root):

```bash
cd frontend
npm install
```

*(If the install fails on peer dependencies, try `npm install --force`.)* Configure `frontend/.env` after the contract is deployed (see below). A production-like build is `npm run build`; local development is `npm start`.

### (Optional) Multi-terminal launch

After §3–4 (conda env, `pip install -r requirements.txt`, `npm install` in `frontend/`), you can open separate terminals for the stack from the repository root instead of only using manual terminals in §5–6 below.

**Commands:**

```bash
# Linux / macOS
python3 launcher_unix.py
```

```powershell
# Windows (PowerShell or cmd)
python launcher_win.py
```

| Platform | Script | What it does |
|----------|--------|----------------|
| **Linux / macOS** | `launcher_unix.py` | 1) **CONTRACT** - `bootstrap_contract.py` then `list_contracts.py` (the script waits for this to finish), 2) **BACKEND** - `python3 backend_server.py` in `core/`, 3) **FRONTEND** - `npm run build && npm start` in `frontend/`. Uses gnome-terminal (typical on Ubuntu) or AppleScript + Terminal on macOS. |
| **Windows** | `launcher_win.py` | 1) **CONTRACT** - `bootstrap_contract.py` then `list_contracts.py` (waits for completion via a flag file), 2) **BACKEND** - `python backend_server.py` in `core/`, 3) **FRONTEND** - `npm run build; npm start` in `frontend/`. Uses separate PowerShell consoles with the `obscura` Conda environment automatically activated. |

**Requirements:** the `obscura` conda env, Node/npm on `PATH` for the frontend window, and (for the Unix script) a compatible terminal app. `launcher_unix.py` uses `python3` for Python commands.

From §5 onward, the steps below assume you are running each command by hand in your own terminals (e.g. §5.1 contract, then §5.2 backend, then §6 frontend), instead of only using the optional launchers above. Follow that order the first time you set up, or use the same commands whenever you need finer control.

**Note:** You need a valid `frontend/.env` (from multi-terminal launch, bootstrap or a manual config) before the app can connect to the contract and the proof server.

### (Optional) Obscura Lens and Inspector

Each tool is a **separate** Python process (use a different terminal for each if you run both).

**Obscura Lens** (Dash graph UI, default `http://127.0.0.1:8050`):

```bash
cd tools
python obscura_lens.py
```

**Obscura Inspector** (Indexer fetch + JSON classification, CLI):

```bash
cd tools
python obscura_inspector.py
```

### 5. Backend setup

#### 5.1 Bootstrap the smart contract

Activate your env (`conda activate obscura`), stay at the project root, then use **terminal 1** for deployment.

`bootstrap_contract.py` (in `contract/`) deploys the dummy (opcode-budget helper) app and the main Obscura app to Algorand Testnet, funds the Obscura contract, and writes `frontend/.env` (deployer address, app ids, contract address, node URLs, etc.). Follow the prompts, if you generate a new deployer account, you will fund it via QR code.

```bash
# Navigate to contract directory
cd contract
# Deploy and fund the obscura smart contract
python bootstrap_contract.py
```

> **Using a Third-Party Deployment:** You can bypass the bootstrap script and manually populate `frontend/.env` with an existing deployment's configuration. However, you must verify the integrity of any third-party contract before use. Run `python verify_contract.py` in the `contract/` directory to assert that the deployed on-chain bytecode exactly matches the local PyTeal source code (`obscura_contract.py`).

A working testnet environment configuration (e.g., `762021711.env.bak`) is provided in the `frontend/` directory. If you want to use the existing public deployment and bypass the bootstrap script, you can simply copy this file to `.env` and use it as-is without any modifications:

```bash
cd frontend
cp 762021711.env.bak .env
```

**Optional – list apps created by the deployer** (`list_contracts.py`). With no arguments it reads `REACT_APP_DEPLOYER_ADDRESS` from `frontend/.env` (after bootstrap, that file exists). You can also pass the deployer address explicitly:

```bash
cd contract
python list_contracts.py
```

```bash
cd contract
python list_contracts.py <DEPLOYER_58_CHAR_ADDRESS>
```

#### 5.2 Start the backend / API server (`core`)

The Flask server generates withdrawal proofs and serves `/api/monitor` pool stats to the frontend.

**Terminal 2:**

```bash
# Navigate to core directory
cd core 
python backend_server.py
```

*The server will run on `http://localhost:5000`.*

### 6. Frontend setup

**Terminal 3:**

```bash
# Navigate to frontend directory
cd frontend
npm start
```

*The web app will open at `http://localhost:3000`.*



## 🧭 Usage Guide

### 1. Connect and Deposit
Connect your Pera Wallet (Testnet) and approve the grouped transaction: a 1 ALGO transfer to the contract plus an application call that records your commitment on-chain. Ensure you have sufficient Testnet ALGO to cover fees. Once confirmed, save the values displayed in the UI, your secret and your commitment. The contract does **not** store your secret.

### 2. Store Credentials Safely
Your secret and commitment are the only means to construct a valid withdrawal later. Back them up securely and offline (as you would a seed phrase). If you lose them, the deposit becomes permanently inaccessible. If someone else obtains them, they can spend your funds.

### 3. Build Anonymity
For withdrawals, connect a different wallet than the one used for the deposit (a “withdrawal” or “handler” account). While the ring structure makes individual spends cryptographically ambiguous, reusing the same account across deposit and withdrawal introduces linkability. Using separate accounts, and allowing time for more deposits and withdrawals to mix into the pool, improves practical anonymity within the ring.

### 4. Withdraw Privately
Ensure your withdrawal wallet has enough ALGO for transaction fees. Enter your secret, commitment, and the recipient address. The system selects decoy commitments, the core service generates the ring proof, and you sign and submit the transaction through your wallet. The blockchain records a nullifier to prevent double-spending, without revealing which ring member you were.

<table align="center" cellspacing="8" cellpadding="4">
  <tr>
    <td><img src="img/obscura/obscura_(01).png" width="200"></td>
    <td><img src="img/obscura/obscura_(02).png" width="200"></td>
    <td><img src="img/obscura/obscura_(03).png" width="200"></td>
    <td><img src="img/obscura/obscura_(04).png" width="200"></td>
    <td><img src="img/obscura/obscura_(05).png" width="200"></td>
  </tr>
  <tr>
    <td><img src="img/obscura/obscura_(06).png" width="200"></td>
    <td><img src="img/obscura/obscura_(07).png" width="200"></td>
    <td><img src="img/obscura/obscura_(08).png" width="200"></td>
    <td><img src="img/obscura/obscura_(09).png" width="200"></td>
    <td><img src="img/obscura/obscura_(10).png" width="200"></td>
  </tr>
</table>



## 📊 Analysis Tools

### Obscura Lens
An interactive Dash application (`tools/obscura_lens.py`) for visualizing Algorand blockchain (Testnet) activity. It fetches transaction data from the Algorand Indexer and renders a dynamic, searchable Cytoscape graph of accounts, contracts, applications, and their interactions, providing a clear view of transaction topology and flow.
- **Dynamic Graph Layout**: Automatically structures nodes into inbound, outbound, and central contract columns to clearly visualize the flow of funds and application calls.
- **Transaction Aggregation**: Groups multiple interactions between addresses, displaying aggregated transaction counts and ALGO volumes on the edges.
- **Inner Transaction Tracing**: Recursively unpacks and visualizes inner transactions (e.g., inner payments from the contract to a withdrawal recipient).

<table align="center" cellspacing="8" cellpadding="4">
  <tr>
    <td><img src="img/obscura_lens/obscura_lens_(01).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(02).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(03).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(04).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(05).png" width="200"></td>
  </tr>
  <tr>
    <td><img src="img/obscura_lens/obscura_lens_(06).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(07).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(08).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(09).png" width="200"></td>
    <td><img src="img/obscura_lens/obscura_lens_(10).png" width="200"></td>
  </tr>
</table>

### Obscura Inspector
A transaction classification tool (`tools/obscura_inspector.py`) that fetches and normalizes full transaction histories for the Obscura smart contract using the Algorand Indexer API. 
- **Automated Classification**: Categorizes transactions into `Deposits` (grouped payment + app call), `Withdrawals` (app calls with the 'withdraw' argument), `Fund Contract` (direct ALGO payments), and `Other`.
- **Deep Data Normalization**: Recursively extracts and normalizes all relevant fields (Base64, Hex, ASCII) from application arguments, box references, global state deltas, and inner transactions.
- **Structured Output**: Outputs a highly detailed, human-readable JSON file (`transactions.json`) for deep ledger state inspection and auditing.



## 🗂️ Code Structure

```bash
Obscura/
├── contract/                                                    # Smart contract (Algorand AVM)
│   ├── bootstrap_contract.py
│   ├── list_contracts.py
│   ├── obscura_contract.py
│   └── verify_contract.py
├── core/                                                        # Local prover enclave
│   ├── backend_server.py
│   ├── bn_254.py
│   └── obscura_engine.py
├── frontend/                                                    # Client application (React/TypeScript)
│   ├── public/
│   ├── src/
│   ├── .env
│   ├── package.json
│   └── tsconfig.json
├── img/                                                         # Figures and images
├── tools/                                                       # Analytical tooling
│   ├── obscura_inspector.py
│   └── obscura_lens.py
├── launcher_unix.py                                             # Multi-terminal launch script for Linux/macOS
├── launcher_win.py                                              # Multi-terminal launch script for Windows
├── README.md                                                    # Documentation
└── requirements.txt                                             # Python dependencies
```



## 🔒 Security & Privacy

Obscura's security guarantees are grounded in formal cryptographic properties and the AVM's execution model:

- **Signer Ambiguity**: Given a ring of size $n$, an adversary cannot identify the true signer with probability significantly greater than $1/n$. The commitment $P$ and key image $I$ use independent generators ($G$ and $H$), rendering them unconditionally unlinkable without knowledge of $x$.
- **Unforgeability (EUF-CMA)**: Assuming the hardness of the Elliptic Curve Discrete Logarithm Problem (ECDLP) on BN254, producing a valid signature without knowing the secret scalar corresponding to a ring member is computationally infeasible.
- **Double-Spend Resistance**: Linkability ensures that any two signatures generated from the same secret $x$ yield the identical key image $I$. The atomic assertion of $\mathcal{B}_N(I)$ guarantees deterministic double-spend prevention.
- **Replay Resistance**: The recipient address $m$ is bound into the Fiat-Shamir challenge chain. Altering the payout destination breaks the signature closure, causing the transaction to revert.

### Known Limitations
- **Fixed Denominations**: In the current testnet implementation, transactions are strictly fixed to 1 ALGO to ensure commitment indistinguishability. Supporting arbitrary amounts would require transitioning to a full Confidential Transaction scheme, which currently exceeds AVM opcode limits.
- **Anonymity Set Size**: Due to the $O(n)$ scaling of LSAG verification and AVM execution limits, the ring size is currently capped at $n=5$.
- **Post-Quantum Vulnerability**: Like all classical elliptic-curve protocols, Obscura is vulnerable to Shor's algorithm. A quantum adversary could recover $x$ from $P = xG$ to deanonymize or forge a withdrawal for that specific deposit.

> **Disclaimer:** This project is experimental software, aimed at research (e.g. on Algorand Testnet), and it has not been through a formal product audit. Do not deploy to mainnet or use with real funds without your own review, any audits you require, and compliance with the laws and regulations that apply to you. You are responsible for how you use the software and for any loss of funds, privacy, or data.



## 🧩 API Reference

The integration path bridges the React frontend, the local Flask prover, and the Algorand blockchain. The specifications below map directly to `contract/obscura_contract.py` and `core/backend_server.py`.

### Smart Contract (PyTeal)

Methods are routed via `application-args[0]` as a UTF-8 string (`deposit`, `withdraw`, `get_count`, or `opup` on the dummy application).

#### `deposit`
- **Group**: 2-transaction atomic group: (1) Payment of 1,000,000 microAlgos to the contract, (2) Application call.
- **Application Call Args**:
  - `args[0]`: `deposit`
  - `args[1]`: 64-byte public commitment $P = xG$ on BN254.
- **State Transition**: The contract verifies the 1 ALGO payment, asserts uniqueness, and allocates a new box $\mathcal{B}_C(P)$ keyed by `c` $\parallel$ `P[0:32]`. It also increments the global deposit counter.

#### `withdraw`
- **Group**: Single application call. The outer transaction fee must cover the pooled execution cost.
- **Application Call Args**:
  - `args[0]`: `withdraw`
  - `args[1]`: 64-byte key image (nullifier) $I = xH$ on BN254.
  - `args[2]`: Packed LSAG signature $\sigma$ ($96n + 33$ bytes). Layout:
    - 1 byte: ring size $n$
    - $n \times 64$ bytes: ring members (public commitments $P_i \in R$)
    - 32 bytes: challenge $c_0$
    - $n \times 32$ bytes: responses $s_i$
  - `args[3]`: 32-byte recipient public key $m$.
- **Dependencies**: 
  - Requires $20n$ inner `opup` calls to the dummy app (passed in `Txn.applications[1]`) to dynamically expand the opcode budget.
  - Requires box references (`appl` box array) for $I$ and all $P_i \in R$ to load ring members from on-chain state.
- **State Transition**: On successful verification, records the nullifier in a box $\mathcal{B}_N(I)$ keyed by `n` $\parallel$ `I[0:32]` and issues an inner payment to $m$ (deducting network fees and storage MBR).

**Optional Read-Only / Helper Methods**: `get_count` returns the global deposit counter; `opup` on the dummy app is used strictly to pad the opcode budget.

### Local Prover API (HTTP, port 5000)

| Method | Path | Body (JSON) | Returns |
|--------|------|-------------|---------|
| `GET` | `/api/monitor` | — | Contract balance, box counts, deposit counts, and effective ring size (capped at 5). |
| `POST` | `/compute_commitment` | `secret` (hex scalar $x$) | `commitment` (128-hex point $P = xG$) |
| `POST` | `/generate_proof` | `secret` $x$, `recipient` $m$, `commitments` $R$, and the user's `commitment` $P$ | `nullifier` $I = xH$ and the packed `proof` $\sigma$ (hex) |

The frontend calls `/compute_commitment` during the deposit phase and `/generate_proof` during the withdrawal phase (see `frontend/src/components/Obscura.tsx`).



## 📑 Citation

The academic research paper detailing the cryptographic foundations, transaction architectures, and security features of Obscura is available at the links below:

[![Google Scholar](https://img.shields.io/badge/Google%20Scholar-Paper-4285F4?logo=googlescholar&logoColor=white)](https://scholar.google.com/scholar_lookup?arxiv_id=2605.02077)
[![arXiv](https://img.shields.io/badge/arXiv-2605.02077-b31b1b.svg)](https://arxiv.org/abs/2605.02077)
[![IACR](https://img.shields.io/badge/IACR-2026%2F917-2E2E2E.svg?logo=databricks&logoColor=white)](https://ia.cr/2026/917)

If this repository or the paper has contributed to your research, please acknowledge our work by citing it:

[![Google Scholar](https://img.shields.io/badge/Google%20Scholar-Cite-34A853?logo=googlescholar&logoColor=white)](https://scholar.google.com/scholar_lookup?arxiv_id=2605.02077#d=gs_cit&t=1778328630780&u=%2Fscholar%3Fq%3Dinfo%3AOYa_rKRWrYAJ%3Ascholar.google.com%2F%26output%3Dcite%26scirp%3D0%26hl%3Den)

```
@article{azimi2026obscura,
  title={Obscura: Privacy-Preserving Protocol for the Algorand Blockchain Using LSAG Ring Signatures},
  author={Azimi, Navid},
  journal={arXiv preprint arXiv:2605.02077},
  year={2026}
}
```

```
@misc{cryptoeprint:2026/917,
      author = {Navid Azimi},
      title = {Obscura: Privacy-Preserving Protocol for the Algorand Blockchain Using {LSAG} Ring Signatures},
      howpublished = {Cryptology {ePrint} Archive, Paper 2026/917},
      year = {2026},
      doi = {10.48550/arXiv.2605.02077},
      url = {https://eprint.iacr.org/2026/917}
}
```



## 📜 License

Obscura is provided under the **GNU General Public License v3.0** ([**GPL-3.0**](https://www.gnu.org/licenses/gpl-3.0.en.html)). In short: you may run, study, share, and modify the code, but if you distribute a modified version you must do so under GPL-3.0 as well, including source for your changes, and you must keep license and copyright notices intact.



## 🌐 Resources

**Algorand Ecosystem**

- [Algorand Developer Portal](https://developer.algorand.org/docs/)
- [Smart Contract Overview](https://developer.algorand.org/docs/get-details/dapps/smart-contracts/)
- [Algorand Virtual Machine](https://developer.algorand.org/docs/get-details/dapps/avm/)
- [Box Storage Documentation](https://dev.algorand.co/concepts/smart-contracts/storage/box/)
- [PyTeal](https://github.com/algorand/pyteal)
- [Pera Wallet](https://perawallet.app/)
- [py-algorand-sdk](https://github.com/Algorand/py-algorand-sdk)
- [js-algorand-sdk](https://github.com/Algorand/js-algorand-sdk)

**Cryptographic Foundations**
- Liu *et al.*, *Linkable Spontaneous Anonymous Group Signatures for Ad Hoc Groups* (ACISP 2004)
- Rivest, Shamir, Tauman, *How to Leak a Secret* (ASIACRYPT 2001)
- Fiat, Shamir, *How to Prove Yourself: Practical Solutions to Identification and Signature Problems* (CRYPTO '86)
- Pertsev, Semenov, Storm, *Tornado cash privacy solution version 1.4* (Tornado cash privacy solution version 1(6) 2019)

