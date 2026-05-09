// SPDX-License-Identifier: GPL-3.0
// Copyright (C) 2026 Navid Azimi

/**
 * Obscura Privacy-Preserving Protocol for the Algorand Blockchain - Frontend Component
 * 
 * This component implements a privacy-preserving protocol interface that uses
 * Zero-Knowledge Linkable Spontaneous Anonymous Group (LSAG) Ring Signatures to ensure:
 * 1. Observers cannot link deposits to withdrawals
 * 2. Only the owner who knows the secret can withdraw
 * 
 * SECURITY: ZKP Ring Signatures executed natively on the AVM using BN254.
 */

import React, { useState, useEffect } from 'react';
import { PeraWalletConnect } from '@perawallet/connect';
import algosdk from 'algosdk';
import './Obscura.css';

interface DepositData {
  secret: string;
  commitment: string;
  txId: string;
  timestamp: number;
}

const Obscura: React.FC = () => {
  const [peraWallet] = useState(new PeraWalletConnect());
  const [accountAddress, setAccountAddress] = useState<string>('');
  const [isConnected, setIsConnected] = useState(false);
  const [deposits, setDeposits] = useState<DepositData[]>([]);
  const [withdrawalAddress, setWithdrawalAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [appId, setAppId] = useState<number>(0);
  const [dummyAppId, setDummyAppId] = useState<number>(0);
  const [showManualEntry, setShowManualEntry] = useState(false);
  const [manualDepositData, setManualDepositData] = useState({
    secret: '',
    commitment: '',
    txId: ''
  });
  const [monitorData, setMonitorData] = useState<any>(null);

  useEffect(() => {
    const fetchMonitorData = async () => {
      try {
        const res = await fetch('http://localhost:5000/api/monitor');
        const data = await res.json();
        if (data.success) {
          setMonitorData(data.data);
        }
      } catch (e) {
        console.error('Failed to fetch monitor data:', e);
      }
    };

    fetchMonitorData();
    const interval = setInterval(fetchMonitorData, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const envAppId = process.env.REACT_APP_MIXER_APP_ID;
    const envDummyAppId = process.env.REACT_APP_DUMMY_APP_ID;
    
    if (envAppId) {
      setAppId(parseInt(envAppId));
    }
    if (envDummyAppId) {
      setDummyAppId(parseInt(envDummyAppId));
    }

    const savedDeposits = localStorage.getItem('obscura-deposits');
    if (savedDeposits) {
      try {
        setDeposits(JSON.parse(savedDeposits));
      } catch (e) {
        console.error('Failed to load saved deposits:', e);
      }
    }

    peraWallet.reconnectSession().then((accounts) => {
      if (accounts.length > 0) {
        setAccountAddress(accounts[0]);
        setIsConnected(true);
      }
    });
  }, [peraWallet]);

  useEffect(() => {
    localStorage.setItem('obscura-deposits', JSON.stringify(deposits));
  }, [deposits]);

  const connectWallet = async () => {
    try {
      setStatus('Connecting wallet...');
      const accounts = await peraWallet.connect();
      setAccountAddress(accounts[0]);
      setIsConnected(true);
      setStatus('Wallet connected successfully!');
      setTimeout(() => setStatus(''), 3000);
    } catch (error) {
      console.error('Failed to connect wallet:', error);
      setStatus('Failed to connect wallet');
      setTimeout(() => setStatus(''), 3000);
    }
  };

  const disconnectWallet = () => {
    peraWallet.disconnect();
    setAccountAddress('');
    setIsConnected(false);
    setStatus('Wallet disconnected');
    setTimeout(() => setStatus(''), 3000);
  };

  // ============================================
  // CRYPTOGRAPHIC UTILITIES
  // ============================================

  const generateRandomHex = (bytes: number): string => {
    const array = new Uint8Array(bytes);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
  };

  const hexToBytes = (hex: string): Uint8Array => {
    const cleanHex = hex.startsWith('0x') ? hex.slice(2) : hex;
    const bytes = new Uint8Array(cleanHex.length / 2);
    for (let i = 0; i < cleanHex.length; i += 2) {
      bytes[i / 2] = parseInt(cleanHex.substring(i, i + 2), 16);
    }
    return bytes;
  };

  const bytesToHex = (bytes: Uint8Array): string => {
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  };

  const stringToBytes = (str: string): Uint8Array => {
    return new TextEncoder().encode(str);
  };

  // Cryptographically secure Fisher-Yates shuffle
  const secureShuffle = <T,>(array: T[]): T[] => {
    const shuffled = [...array];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const randomBuffer = new Uint32Array(1);
      crypto.getRandomValues(randomBuffer);
      // Map the random 32-bit integer to the range [0, i]
      const j = randomBuffer[0] % (i + 1);
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  };

  // ============================================
  // DEPOSIT FUNCTION
  // ============================================

  const makeDeposit = async () => {
    if (!isConnected || !appId) {
      setStatus('Please connect wallet and ensure app is deployed');
      return;
    }

    setLoading(true);
    setStatus('Creating deposit...');

    try {
      const algodClient = new algosdk.Algodv2('', 'https://testnet-api.algonode.cloud', '');
      
      // In production, the frontend should generate the BN254 secret and compute the
      // corresponding commitment locally (e.g., via a WASM cryptography library).
      // This avoids sending any sensitive material outside the client and removes
      // the dependency on a backend service for commitment generation.

      // For this implementation, we generate the secret in the frontend but delegate
      // the BN254 commitment computation to a local Python backend that performs the
      // elliptic curve operations.

      const secret = generateRandomHex(32);
      
      // Call the local proof service to compute the BN254 commitment corresponding
      // to the generated secret.

      const commitRes = await fetch('http://localhost:5000/compute_commitment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ secret: '0x' + secret })
      });
      const commitData = await commitRes.json();
      if (!commitData.success) throw new Error(commitData.error);
      const commitment = commitData.commitment;

      console.log('Generated deposit details (KEEP PRIVATE):');
      console.log('  Secret:', secret.slice(0, 16) + '...');
      console.log('  Commitment (goes on-chain):', commitment);

      setStatus('Preparing transactions...');

      const appAddress = algosdk.getApplicationAddress(appId);
      const suggestedParams = await algodClient.getTransactionParams().do();
      
      const commitmentBytes = hexToBytes(commitment);
      
      // Pad to 64 bytes to match BN254 point size
      const commitmentArg = new Uint8Array(64);
      commitmentArg.set(commitmentBytes);

      // Box name: "c" + first 32 bytes
      const boxName = new Uint8Array(33);
      boxName.set(stringToBytes('c'), 0);
      boxName.set(commitmentBytes.slice(0, 32), 1);

      // Create application call transaction
      const appCallTxn = algosdk.makeApplicationNoOpTxn(
        accountAddress,
        suggestedParams,
        appId,
        [stringToBytes('deposit'), commitmentArg],
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        [{ appIndex: appId, name: boxName }]
      );

      // Create payment transaction
      const paymentTxn = algosdk.makePaymentTxnWithSuggestedParams(
        accountAddress,
        appAddress,
        1000000, // 1 ALGO
        undefined,
        undefined,
        suggestedParams
      );

      // Group transactions
      const groupedTxns = [appCallTxn, paymentTxn];
      algosdk.assignGroupID(groupedTxns);

      setStatus('Please sign the transaction in your wallet...');

      const signedTxns = await peraWallet.signTransaction([
        [
          { txn: appCallTxn, signers: [accountAddress] },
          { txn: paymentTxn, signers: [accountAddress] }
        ]
      ]);

      setStatus('Submitting transaction...');

      const { txId } = await algodClient.sendRawTransaction(signedTxns).do();
      
      setStatus('Waiting for confirmation...');
      await algosdk.waitForConfirmation(algodClient, txId, 4);

      // Store deposit data locally
      const depositData: DepositData = {
        secret,
        commitment,
        txId: txId,
        timestamp: Date.now()
      };
      
      setDeposits([...deposits, depositData]);
      
      setStatus(`Deposit successful! TX: ${txId.substring(0, 8)}...`);
      setTimeout(() => setStatus(''), 5000);

    } catch (error: any) {
      console.error('Deposit failed:', error);
      const errorMessage = error?.message || error?.toString() || 'Unknown error';
      if (errorMessage.includes('overspend')) {
        setStatus('Deposit failed: Insufficient funds. Please fund your wallet.');
      } else if (errorMessage.includes('box')) {
        setStatus(`Deposit failed: Box storage error. ${errorMessage}`);
      } else {
        setStatus(`Deposit failed: ${errorMessage}`);
      }
      setTimeout(() => setStatus(''), 8000);
    } finally {
      setLoading(false);
    }
  };

  // ============================================
  // WITHDRAWAL FUNCTION
  // ============================================

  const makeWithdrawal = async (depositData: DepositData) => {
    if (!withdrawalAddress) {
      setStatus('Please enter withdrawal address');
      return;
    }

    if (!algosdk.isValidAddress(withdrawalAddress)) {
      setStatus('Invalid withdrawal address');
      return;
    }

    setLoading(true);
    setStatus('Creating withdrawal transaction...');

    try {
      const algodClient = new algosdk.Algodv2('', 'https://testnet-api.algonode.cloud', '');
      
      // -------------------------------------------------
      // Retrieve all deposit commitments stored in boxes
      // -------------------------------------------------
      // Each deposit is stored in a contract box named:
      //   "c" + first 32 bytes of the commitment
      // The box value contains the full 64-byte BN254 point.

      setStatus('Retrieving contract state...');
      let commitments: string[] = [];
      
      try {
        // @ts-ignore
        const boxesResponse = await algodClient.getApplicationBoxes(appId).do();
        const boxes = boxesResponse.boxes || [];
        
        for (const box of boxes) {
          let boxNameBytes: Uint8Array;

          // Box names may be returned as base64 strings by the SDK
          if (typeof box.name === 'string') {
            const binString = atob(box.name);
            boxNameBytes = Uint8Array.from(binString, (m) => m.codePointAt(0)!);
          } else {
            // @ts-ignore
            boxNameBytes = box.name;
          }
          
          // Only process deposit boxes ("c" prefix)
          if (boxNameBytes.length === 33 && boxNameBytes[0] === 99) {

            // Fetch the full stored commitment (64-byte BN254 point)
            // @ts-ignore
            const boxResponse = await algodClient.getApplicationBoxByName(appId, boxNameBytes).do();
            // @ts-ignore
            const pointBytes = boxResponse.value;

            const hexVal = bytesToHex(pointBytes);
            commitments.push(hexVal);
          }
        }
      } catch (e) {
        console.error("Error fetching boxes:", e);
        setStatus('Error fetching contract storage');
        setLoading(false);
        return;
      }

      // Ensure the user's deposit commitment exists on-chain
      if (!commitments.includes(depositData.commitment)) {
        setStatus('Error: Your deposit was not found in the contract');
        setLoading(false);
        return;
      }

      // =====================================================================
      // ANONYMITY SET SELECTION
      // =====================================================================
      // We construct a ring of commitments consisting of:
      //   - the user's real commitment
      //   - several decoy commitments
      // These decoys form the anonymity set used by the ring signature.
      // The verifier can confirm that *one* member of the ring is valid
      // without revealing which commitment actually corresponds to the user.
      //
      // To mitigate timing-based analysis attacks, we prioritize recent commitments.
      // Note: In a ZKP system, we cannot know which commitments are "non-nullified" 
      // without breaking privacy, because nullifiers are mathematically decoupled.
      // However, prioritizing recent commitments statistically increases the likelihood 
      // of selecting unspent ones and mimics natural user behavior, strengthening 
      // the anonymity set against temporal correlation.
      
      setStatus('Fetching recent deposits to form the anonymity set...');
      const indexerClient = new algosdk.Indexer('', 'https://testnet-idx.algonode.cloud', '');
      let recentCommitments: string[] = [];
      try {
        // Query recent application calls to extract deposit commitments
        const txnsResponse = await indexerClient.searchForTransactions()
          .address(algosdk.getApplicationAddress(appId))
          .txType('appl')
          .limit(200)
          .do();
          
        const txns = txnsResponse.transactions || [];
        for (const tx of txns) {
          if (tx['application-transaction'] && tx['application-transaction']['application-args']) {
            const args = tx['application-transaction']['application-args'];
            // deposit(...) calls use "deposit" as the first argument (ZGVwb3NpdA== in base64)
            if (args[0] === 'ZGVwb3NpdA==' && args[1]) {
              const binString = atob(args[1]);
              const commitBytes = Uint8Array.from(binString, (m) => m.codePointAt(0)!);
              const commitHex = bytesToHex(commitBytes);

              // Commitments are 64-byte BN254 points
              if (commitHex.length === 128) { // 64 bytes = 128 hex chars
                recentCommitments.push(commitHex);
              }
            }
          }
        }
      } catch (e) {
        // If the indexer is unavailable, fall back to random selection
        console.warn("Could not fetch recent transactions from indexer, falling back to random selection", e);
      }

      // -------------------------------------------------
      // Build decoy pool (exclude user's real commitment)
      // -------------------------------------------------
      let validDecoys = commitments.filter(c => c !== depositData.commitment && !c.endsWith('0000000000000000000000000000000000000000000000000000000000000000'));

      // Sort decoys: recent ones first. If not in recent list, keep them at the end.
      validDecoys.sort((a, b) => {
        const indexA = recentCommitments.indexOf(a);
        const indexB = recentCommitments.indexOf(b);
        
        // Both found in recent (lower index means more recent in indexer response)
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        // Only A is recent
        if (indexA !== -1) return -1;
        // Only B is recent
        if (indexB !== -1) return 1;
        // Neither is recent, keep random order
        return 0.5 - Math.random();
      });

      // -------------------------------------------------
      // Random selection from a recent decoy pool
      // -------------------------------------------------
      // To avoid deterministic bias (which would reduce the anonymity set if we ALWAYS pick the exact 4 most recent),
      // we select randomly from a "recent pool" (e.g., the 20 most recent valid decoys).
      const RECENT_POOL_SIZE = 20;
      let recentPool = validDecoys.slice(0, RECENT_POOL_SIZE);
      
      // Shuffle the recent pool to ensure non-deterministic selection within the recent window
      recentPool = secureShuffle(recentPool);
      
      // -------------------------------------------------
      // Determine ring size
      // -------------------------------------------------
      // We need (ringSize - 1) decoys + 1 real = ringSize members
      // We dynamically fetch the effective ring size from the monitor API.
      // If it fails, we default to 5.
      let targetRingSize = 5;
      try {
        const monitorRes = await fetch('http://localhost:5000/api/monitor');
        const monitorData = await monitorRes.json();
        if (monitorData.success && monitorData.data.effectiveRing > 0) {
          targetRingSize = monitorData.data.effectiveRing;
        }
      } catch (e) {
        console.warn("Could not fetch dynamic ring size, defaulting to 5", e);
      }
      
      const numDecoys = targetRingSize - 1;
      
      // If insufficient decoys exist, reduce ring size accordingly
      const actualDecoys = Math.min(numDecoys, recentPool.length);
      let ring = recentPool.slice(0, actualDecoys); 
      
      // Insert the real commitment to the ring
      ring.push(depositData.commitment);
      
      // Final shuffle using cryptographically secure Fisher-Yates to ensure the 
      // real commitment is uniformly distributed across all 5 positions.
      ring = secureShuffle(ring);

      // -------------------------------------------------
      // Generate zero-knowledge ring signature proof
      // -------------------------------------------------

      // Call the backend proof server to do the heavy BN254 math
      const response = await fetch('http://localhost:5000/generate_proof', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            secret: '0x' + depositData.secret,
            recipient: withdrawalAddress,
            commitments: ring,
            commitment: depositData.commitment
          }),
        });

        const proofData = await response.json();

        if (!proofData.success) {
          throw new Error(`Failed to generate proof: ${proofData.error}`);
        }

        // -------------------------------------------------
        // Prepare proof inputs for the smart contract
        // -------------------------------------------------

        const proofBytes = hexToBytes(proofData.proof);

        // Nullifier prevents double-spending of the same deposit
        const nullifierHashBytes = hexToBytes(proofData.nullifier.slice(0, 64)); // taking just 32 bytes if it's longer
        
        const recipientBytes = algosdk.decodeAddress(withdrawalAddress).publicKey;

        console.log('ZK Ring Signature proof generated by backend');
        console.log('  Nullifier point:', proofData.nullifier);
        console.log('  Proof size:', proofBytes.length, 'bytes');

        const suggestedParams = await algodClient.getTransactionParams().do();
        
        // -------------------------------------------------
        // Construct nullifier storage box
        // -------------------------------------------------
        // Format: "n" + first 32 bytes of the nullifier
        const nullifierBoxName = new Uint8Array(33);
        nullifierBoxName.set(stringToBytes('n'), 0);
        nullifierBoxName.set(nullifierHashBytes.slice(0, 32), 1);

        // -------------------------------------------------
        // Fee calculation
        // -------------------------------------------------
        // Calculate required fee for inner opups
        // We have `ring.length` members. Each member takes 20 inner opup txns. 
        // Plus 1 inner payout txn. Plus outer txn.
        const totalInnerTxns = (ring.length * 20) + 1;
        const requiredFee = (totalInnerTxns + 1) * suggestedParams.minFee;
        
        suggestedParams.fee = requiredFee;
        suggestedParams.flatFee = true;

        // -------------------------------------------------
        // Create withdrawal application call
        // -------------------------------------------------
        const withdrawalTxn = algosdk.makeApplicationNoOpTxn(
          accountAddress,
          suggestedParams,
          appId,
          [
            stringToBytes('withdraw'),
            hexToBytes(proofData.nullifier), // Full 64 bytes point
            proofBytes,                      // ZK proof
            recipientBytes,                  // Recipient address
          ],
          [withdrawalAddress],
          [dummyAppId],
          undefined,
          undefined,
          undefined,
          undefined,
          [
            { appIndex: appId, name: nullifierBoxName },
            // Provide all ring commitment boxes to the contract
            ...ring.map(c => {
               const bName = new Uint8Array(33);
               bName.set(stringToBytes('c'), 0);
               bName.set(hexToBytes(c).slice(0, 32), 1);
               return { appIndex: appId, name: bName };
            })
          ]
        );

        setStatus('Please sign the withdrawal transaction...');

        const txnsToSign = [{ txn: withdrawalTxn, signers: [accountAddress] }];
        const signedTxn = await peraWallet.signTransaction([txnsToSign]);

        setStatus('Submitting withdrawal...');

        const { txId } = await algodClient.sendRawTransaction(signedTxn).do();
        
        setStatus('Waiting for confirmation...');
        await algosdk.waitForConfirmation(algodClient, txId, 4);
        
        console.log('WITHDRAWAL COMPLETE');
        console.log('  TX:', txId);

        setStatus(`Withdrawal successful! TX: ${txId.substring(0, 8)}...`);
        
        // Remove used deposit
        setDeposits(deposits.filter(d => d.commitment !== depositData.commitment));
        
        setTimeout(() => setStatus(''), 5000);

    } catch (error: any) {
      console.error('Withdrawal failed:', error);
      setStatus(`Withdrawal failed: ${error.message || 'Please try again.'}`);
      setTimeout(() => setStatus(''), 8000);
    } finally {
      setLoading(false);
    }
  };

  // ============================================
  // UI UTILITIES
  // ============================================

  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setStatus(`${label} copied to clipboard!`);
      setTimeout(() => setStatus(''), 2000);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      setStatus('Failed to copy to clipboard');
      setTimeout(() => setStatus(''), 2000);
    }
  };

  const clearDeposits = () => {
    if (window.confirm('Are you sure you want to clear all saved deposits? This cannot be undone.')) {
      setDeposits([]);
      localStorage.removeItem('obscura-deposits');
      setStatus('Deposits cleared');
      setTimeout(() => setStatus(''), 3000);
    }
  };

  const addManualDeposit = () => {
    if (!manualDepositData.secret || !manualDepositData.commitment) {
      setStatus('Please fill in all required fields');
      setTimeout(() => setStatus(''), 3000);
      return;
    }

    const newDeposit: DepositData = {
      secret: manualDepositData.secret,
      commitment: manualDepositData.commitment,
      txId: manualDepositData.txId || 'manual-entry',
      timestamp: Date.now()
    };

    setDeposits([...deposits, newDeposit]);
    setManualDepositData({ secret: '', commitment: '', txId: '' });
    setShowManualEntry(false);
    setStatus('Manual deposit entry added successfully!');
    setTimeout(() => setStatus(''), 3000);
  };

  const cancelManualEntry = () => {
    setManualDepositData({ secret: '', commitment: '', txId: '' });
    setShowManualEntry(false);
  };

  const exportDeposits = () => {
    if (deposits.length === 0) {
      setStatus('No deposits to export');
      setTimeout(() => setStatus(''), 3000);
      return;
    }

    const exportData = {
      timestamp: new Date().toISOString(),
      appId: appId,
      deposits: deposits.map(deposit => ({
        secret: deposit.secret,
        commitment: deposit.commitment,
        txId: deposit.txId,
        date: new Date(deposit.timestamp).toISOString()
      }))
    };

    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `obscura-deposits-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setStatus('Deposits exported successfully!');
    setTimeout(() => setStatus(''), 3000);
  };

  return (
    <div className="algo-mixer">
      <div className="header">
        {/* <h1>🔒 Obscura</h1> */}
        <h1
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "10px",
          }}
        >
          <img
            src="/icon.png"
            alt="Obscura logo"
            style={{
              width: "1.3em",
              height: "1.3em",
              display: "block",
            }}
          />
          Obscura
        </h1>
        <p>
          Decentralized, Non-Custodial Privacy-Preserving Protocol for the <br />
          Algorand Blockchain Using LSAG Ring Signatures
        </p>
        <p className="privacy-badge">⛓️ Algorand Testnet</p>
        {appId && <p className="app-id">App ID: {appId}</p>}
        {status && <div className="status-message">{status}</div>}
      </div>

      <div className="wallet-section">
        {!isConnected ? (
          <button onClick={connectWallet} className="connect-btn" disabled={loading}>
            Connect Pera Wallet
          </button>
        ) : (
          <div className="connected-wallet">
            <p>Connected: {accountAddress.slice(0, 8)}...{accountAddress.slice(-8)}</p>
            <button onClick={disconnectWallet} className="disconnect-btn">
              Disconnect
            </button>
          </div>
        )}
      </div>

      {isConnected && appId && (
        <div className="mixer-interface">
          <div className="deposit-section">
            <h2>💰 Make a Deposit</h2>
            
            {monitorData && (
              <div className="monitor-dashboard">
                <h3>
                  <a 
                    href={`https://testnet.explorer.perawallet.app/application/${appId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="View Contract on Explorer"
                    style={{ textDecoration: 'none' }}
                  >
                    📊
                  </a>{' '}
                  Pool Statistics
                </h3>
                <div className="monitor-grid">
                  <div className="monitor-stat">
                    <span className="stat-label">Total Deposits</span>
                    <span className="stat-value">{monitorData.deposits}</span>
                  </div>
                  <div className="monitor-stat">
                    <span className="stat-label">Total Withdrawals</span>
                    <span className="stat-value">{monitorData.withdrawals}</span>
                  </div>
                  <div className="monitor-stat">
                    <span className="stat-label">Unspent UTXOs</span>
                    <span className="stat-value">{monitorData.unspent}</span>
                  </div>
                  <div className="monitor-stat">
                    <span className="stat-label">Effective Ring Size</span>
                    <span className="stat-value">{monitorData.effectiveRing}</span>
                  </div>
                  <div className="monitor-stat full-width">
                    <span className="stat-label">Pool Balance</span>
                    <span className="stat-value">{monitorData.balance.toFixed(6)} ALGO</span>
                  </div>
                </div>
              </div>
            )}

            <div className="deposit-info">
              <p><strong>Deposit Amount:</strong> 1 ALGO</p>
              <p><strong>Deposit Fee:</strong> 0.001 ALGO</p>
              <p><strong>You Receive:</strong> 0.899 ALGO (on withdrawal)</p>
              <p className="privacy-note">
                🌀 Calculated for Privacy Pool of 5 Participants
              </p>
            </div>
            <button 
              onClick={makeDeposit} 
              disabled={loading || !appId}
              className="deposit-btn"
            >
              {loading ? 'Processing...' : 'Deposit 1 ALGO'}
            </button>
          </div>

          <div className="withdrawal-section">
            <h2>🕶️ Withdraw Anonymously</h2>
            <div className="deposit-info">
              <p className="text-emerald-600 dark:text-emerald-500">
               🔔 Obscura leverages zero-knowledge LSAG ring signatures to ensure that only the rightful owner can authorize withdrawals while keeping all deposits and withdrawals unlinkable. Each transaction is secured with unforgeable proofs, preserving both ownership and privacy.
              </p>
            </div>
            <input
              type="text"
              placeholder="Enter withdrawal address"
              value={withdrawalAddress}
              onChange={(e) => setWithdrawalAddress(e.target.value)}
              className="address-input"
              disabled={loading}
            />
            
            <div className="deposits-list">
              <div className="deposits-header">
                <h3>Your Deposits ({deposits.length})</h3>
                <div className="header-buttons">
                  <button 
                    onClick={() => setShowManualEntry(!showManualEntry)} 
                    className="add-manual-btn"
                  >
                    {showManualEntry ? '❌ Cancel' : '➕ Add Manual Entry'}
                  </button>
                  {deposits.length > 0 && (
                    <>
                      <button onClick={exportDeposits} className="export-btn">
                        💾 Export All
                      </button>
                      <button onClick={clearDeposits} className="clear-btn">
                        Clear All
                      </button>
                    </>
                  )}
                </div>
              </div>
              
              {showManualEntry && (
                <div className="manual-entry-form">
                  <h4>📝 Enter Deposit Details Manually</h4>
                  <p className="form-description">
                    Enter your deposit details.
                  </p>
                  
                  <div className="form-group">
                    <label><strong>Secret (required):</strong></label>
                    <input
                      type="text"
                      placeholder="64 character hex string"
                      value={manualDepositData.secret}
                      onChange={(e) => setManualDepositData({...manualDepositData, secret: e.target.value})}
                      className="manual-input"
                    />
                  </div>

                  <div className="form-group">
                    <label><strong>Commitment (required):</strong></label>
                    <input
                      type="text"
                      placeholder="128 character hex string"
                      value={manualDepositData.commitment}
                      onChange={(e) => setManualDepositData({...manualDepositData, commitment: e.target.value})}
                      className="manual-input"
                    />
                  </div>

                  <div className="form-group">
                    <label><strong>Tx ID (optional):</strong></label>
                    <input
                      type="text"
                      placeholder="Deposit transaction ID"
                      value={manualDepositData.txId}
                      onChange={(e) => setManualDepositData({...manualDepositData, txId: e.target.value})}
                      className="manual-input"
                    />
                  </div>

                  <div className="form-buttons">
                    <button onClick={addManualDeposit} className="add-btn">
                      ✅ Add Deposit
                    </button>
                    <button onClick={cancelManualEntry} className="cancel-btn">
                      ❌ Cancel
                    </button>
                  </div>
                </div>
              )}
              
              {deposits.length === 0 && !showManualEntry ? (
                <div className="no-deposits">
                  <p>No deposits found</p>
                  <p>Make a deposit or add manual details</p>
                </div>
              ) : (
                <>
                  {deposits.length > 0 && (
                    <div className="security-warning">
                      <p><strong>🔐 Security Notice</strong><br /></p>
                      <p>
                         Your commitment is stored on-chain, while your secret remains completely private. Back up both securely. If they are lost or shared, your deposited funds could be permanently lost or stolen.
                      </p>
                    </div>
                  )}
                  {deposits.map((deposit, index) => (
                    <div key={index} className="deposit-item">
                      <div className="deposit-details">
                        <div className="detail-row">
                          <p><strong>Secret:</strong></p>
                          <div className="value-container">
                            <span className="full-value" title={deposit.secret}>
                              {deposit.secret.slice(0, 8)}...{deposit.secret.slice(-8)}
                            </span>
                            <button 
                              className="copy-btn" 
                              onClick={() => copyToClipboard(deposit.secret, 'Secret')}
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        <div className="detail-row">
                          <p><strong>Commitment:</strong></p>
                          <div className="value-container">
                            <span className="full-value" title={deposit.commitment}>
                              {deposit.commitment.slice(0, 8)}...{deposit.commitment.slice(-8)}
                            </span>
                            <button 
                              className="copy-btn" 
                              onClick={() => copyToClipboard(deposit.commitment, 'Commitment')}
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        {deposit.txId && deposit.txId !== 'manual-entry' && (
                          <div className="detail-row">
                            <p><strong>Tx ID:</strong></p>
                            <div className="value-container">
                              <span className="full-value" title={deposit.txId}>
                                {deposit.txId.slice(0, 8)}...{deposit.txId.slice(-8)}
                              </span>
                              <button 
                                className="copy-btn" 
                                onClick={() => copyToClipboard(deposit.txId, 'Tx ID')}
                              >
                                📋
                              </button>
                              <a 
                                href={`https://testnet.explorer.perawallet.app/tx/${deposit.txId}`} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="copy-btn"
                                title="View on Explorer"
                              >
                                🔗
                              </a>
                            </div>
                          </div>
                        )}
                        <div className="detail-row">
                          <p><strong>Date:</strong> {new Date(deposit.timestamp).toLocaleString()}</p>
                        </div>
                      </div>
                      <button 
                        onClick={() => makeWithdrawal(deposit)}
                        disabled={loading || !withdrawalAddress}
                        className="withdraw-btn"
                      >
                        {loading ? 'Processing...' : 'Withdraw'}
                      </button>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="info-section">
        <h2>How to Use Obscura</h2>
        <div className="steps">
          <div className="step">
            <div className="step-header">
              <span className="step-number">1</span>
              <h3>Connect & Deposit</h3>
            </div>
            <p>Connect your Pera Wallet to initiate a deposit. Ensure your wallet has sufficient funds to cover transaction fees. Once confirmed, you will receive a unique Commitment and Secret.</p>
          </div>
          <div className="step">
            <div className="step-header">
              <span className="step-number">2</span>
              <h3>Secure Credentials</h3>
            </div>
            <p>Store your Commitment and Secret in a secure location. These are your only proof of ownership. If lost or stolen, your funds cannot be recovered.</p>
          </div>
          <div className="step">
            <div className="step-header">
              <span className="step-number">3</span>
              <h3>Build Anonymity</h3>
            </div>
            <p>Disconnect your current (deposit) wallet, then connect a new wallet (withdrawal or handler). Allow time for your deposit to mix in the pool to increase anonymity and break the link to your deposit.</p>
          </div>
          <div className="step">
            <div className="step-header">
              <span className="step-number">4</span>
              <h3>Withdraw Privately</h3>
            </div>
            <p>Ensure your withdrawal (or handler) wallet has enough funds for transaction fees. Then provide your Secret, Commitment, and withdrawal address to withdraw privately, breaking the link to the original deposit.</p>
          </div>
        </div>
        
        <div className="security-notice">
          <h3>Security & Privacy</h3>
          <p className="warning-note">
            ⚠️ This deployment is for experimental use only. Do not deposit real assets, as they cannot be recovered.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Obscura;
