#!/usr/bin/env python3
"""
Obscura Lens: Transaction Topology & Flow Analyzer

An interactive Dash application for visualizing Algorand blockchain activity.
It fetches transaction data from the Algorand Indexer and renders a dynamic,
searchable graph of accounts, contracts, applications, and their interactions.
"""

import requests
import pandas as pd
import dash
import dash_cytoscape as cyto
from dash import html, dcc
from dash.dependencies import Input, Output, State
import os
import time
import random
import webbrowser
from threading import Timer

INDEXER_URL = "https://testnet-idx.algonode.cloud"

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def short_addr(addr):
    if addr is None:
        return "None"
    return str(addr)[:4] + "..." + str(addr)[-4:]

def safe_get(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    return {}

def fetch_transactions(address):
    txs = []
    next_token = None
    while True:
        url = f"{INDEXER_URL}/v2/accounts/{address}/transactions?limit=1000"
        if next_token:
            url += f"&next={next_token}"
        
        data = safe_get(url)
        fetched_txs = data.get("transactions", [])
        if not fetched_txs:
            break
            
        txs.extend(fetched_txs)
        next_token = data.get("next-token")
        if not next_token:
            break
            
        # Hard limit for UI performance
        if len(txs) > 3000:
            break
            
    return txs

def parse_transactions(txs):
    records = []
    for tx in txs:
        txid = tx.get("id")
        sender = tx.get("sender")
        round_time = tx.get("round-time")

        # Payment
        if "payment-transaction" in tx:
            pay = tx["payment-transaction"]
            records.append({
                "TxID": txid, "Type": "Payment", "From": sender,
                "To": pay.get("receiver"), "Amount": pay.get("amount",0)/1e6, "Time": round_time
            })

        # Application call
        if "application-transaction" in tx:
            app = tx["application-transaction"]
            records.append({
                "TxID": txid, "Type": "App Call", "From": sender,
                "To": f"App-{app.get('application-id')}", "Amount": 0, "Time": round_time
            })

        # Inner transactions
        if "inner-txns" in tx:
            for inner in tx["inner-txns"]:
                if "payment-transaction" in inner:
                    pay = inner["payment-transaction"]
                    records.append({
                        "TxID": inner.get("id", txid), "Type": "Inner Payment",
                        "From": inner.get("sender", sender), "To": pay.get("receiver"),
                        "Amount": pay.get("amount",0)/1e6, "Time": round_time
                    })
    return pd.DataFrame(records)

def build_cytoscape_elements(df, main_contract):
    if df.empty:
        return []
        
    summary = (
        df.groupby(["From", "To", "Type"])
        .agg({"Amount": "sum", "TxID": lambda x: list(x)})
        .reset_index()
    )
    summary["Count"] = summary["TxID"].apply(len)

    # Track inbound/outbound relationships for layout positioning
    node_stats = {}
    for _, row in summary.iterrows():
        s, t = row["From"], row["To"]
        if s not in node_stats: node_stats[s] = {'in': False, 'out': False}
        if t not in node_stats: node_stats[t] = {'in': False, 'out': False}
        
        if t == main_contract: node_stats[s]['in'] = True  # s sends TO center
        if s == main_contract: node_stats[t]['out'] = True # t receives FROM center

    # Calculate Structured Column Layout (Left, Center, Right)
    col_left, col_center, col_right = [], [], []
    for n, stats in node_stats.items():
        if n == main_contract:
            col_center.append(n)
        elif str(n).startswith("App-"):
            col_right.append(n)
        elif stats['in'] and not stats['out']:
            col_left.append(n)
        elif stats['out'] and not stats['in']:
            col_right.append(n)
        else:
            col_center.append(n)

    # Assign exact coordinates (expanded spacing for better UI)
    positions = {}
    for col_idx, col in enumerate([col_left, col_center, col_right]):
        x_pos = col_idx * 700  # Spread columns wider
        y_start = - (len(col) * 90) / 2 # Spread nodes vertically more
        for i, node in enumerate(col):
            positions[node] = {'x': x_pos, 'y': y_start + (i * 90)}

    elements = []
    
    # Add Nodes
    for node in node_stats.keys():
        if node == main_contract:
            node_class = 'center-node'
        elif str(node).startswith("App-"):
            node_class = 'app-node'
        elif node_stats[node]['in'] and not node_stats[node]['out']:
            node_class = 'inbound-node'
        elif node_stats[node]['out'] and not node_stats[node]['in']:
            node_class = 'outbound-node'
        else:
            node_class = 'mixed-node'
            
        elements.append({
            'data': {'id': node, 'label': short_addr(node), 'full_address': node, 'original_class': node_class},
            'position': positions[node],
            'classes': node_class
        })

    # Add Edges
    for _, row in summary.iterrows():
        label = f"{row['Type']} ({row['Count']})"
        if row["Amount"] > 0:
            label += f"\n{row['Amount']:.2f} ALGO"
            
        elements.append({
            'data': {
                'source': row["From"], 'target': row["To"],
                'label': label, 'type': row['Type'],
                'amount': row['Amount'], 'count': row['Count'],
                'txids': row['TxID'],
                'original_class': 'edge'
            },
            'classes': 'edge'
        })
        
    return elements

# --------------------------------------------------
# Dash App Layout
# --------------------------------------------------
app = dash.Dash(__name__)
app.title = "Obscura Lens"

DEFAULT_CONTRACT = ""

# Modern UI Styles
btn_style = {
    'padding': '8px 15px', 'marginRight': '5px', 'backgroundColor': '#0074D9', 
    'color': 'white', 'border': 'none', 'borderRadius': '4px', 
    'cursor': 'pointer', 'fontWeight': 'bold', 'fontSize': '12px'
}

app.layout = html.Div([
    # Top Navbar
    html.Div([
        html.H1("Obscura Lens", style={'margin': '0', 'color': '#ffffff', 'fontSize': '24px', 'paddingLeft': '20px', 'display': 'inline-block'}),
        html.Div("⛓️ Algorand Testnet", style={'float': 'right', 'color': '#ffffff', 'fontSize': '16px', 'fontWeight': 'bold', 'paddingRight': '24px', 'marginTop': '4px'})
    ], style={'backgroundColor': '#002b36', 'padding': '15px 0', 'boxShadow': '0 2px 5px rgba(0,0,0,0.2)', 'zIndex': '10', 'position': 'relative'}),
    
    # Main Dashboard Container
    html.Div([
        
        # LEFT SIDEBAR (Controls & Legend)
        html.Div([
            html.H3("Configuration", style={'marginTop': '0', 'color': '#333', 'borderBottom': '2px solid #ddd', 'paddingBottom': '10px'}),
            
            html.Label(html.B("Target Contract / Address:")),
            dcc.Input(id='contract-input', type='text', value=DEFAULT_CONTRACT, style={'width': '100%', 'padding': '10px', 'marginTop': '5px', 'marginBottom': '10px', 'boxSizing': 'border-box', 'borderRadius': '4px', 'border': '1px solid #ccc'}),
            
            html.Button('Analyze Flow', id='analyze-btn', n_clicks=0, style={'width': '100%', 'padding': '12px', 'backgroundColor': '#2ECC40', 'color': 'white', 'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer', 'fontWeight': 'bold', 'marginBottom': '20px'}),
            
            html.Label(html.B("Graph Layout:")),
            dcc.RadioItems(
                id='layout-toggle',
                options=[
                    {'label': ' Structured Flow', 'value': 'preset'},
                    {'label': ' Dynamic Flow', 'value': 'cose'}
                ],
                value='preset',
                labelStyle={'display': 'block', 'margin': '8px 0', 'color': '#555'},
                style={'marginBottom': '30px'}
            ),
            
            html.H3("Legend", style={'color': '#333', 'borderBottom': '2px solid #ddd', 'paddingBottom': '10px'}),
            html.Div([
                html.Div([html.Span("■", style={'color': '#FFDC00', 'fontSize': '20px', 'marginRight': '10px'}), "Target Contract / Address"], style={'marginBottom': '5px'}),
                html.Div([html.Span("■", style={'color': '#7FDBFF', 'fontSize': '20px', 'marginRight': '10px'}), "Deposit / Inbound"], style={'marginBottom': '5px'}),
                html.Div([html.Span("■", style={'color': '#2ECC40', 'fontSize': '20px', 'marginRight': '10px'}), "Withdrawal / Outbound"], style={'marginBottom': '5px'}),
                html.Div([html.Span("■", style={'color': '#B10DC9', 'fontSize': '20px', 'marginRight': '10px'}), "Application"], style={'marginBottom': '5px'}),
                html.Div([html.Span("■", style={'color': '#FF851B', 'fontSize': '20px', 'marginRight': '10px'}), "Mixed / Other"], style={'marginBottom': '5px'}),
            ], style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '6px', 'border': '1px solid #e0e0e0', 'fontSize': '14px'})
            
        ], style={'width': '300px', 'minWidth': '300px', 'padding': '20px', 'backgroundColor': '#f4f6f8', 'borderRight': '1px solid #ddd', 'boxSizing': 'border-box', 'overflowY': 'auto'}),
        
        # CENTER PANEL (Graph)
        html.Div([
            # Graph Toolbar
            html.Div([
                html.Div(id='status-msg', style={'fontWeight': 'bold', 'color': '#555', 'display': 'inline-block', 'marginTop': '8px'}),
                html.Div([
                    dcc.Input(id='search-input', type='text', placeholder='Search address/TxID...', style={'padding': '6px', 'marginRight': '5px', 'borderRadius': '4px', 'border': '1px solid #ccc', 'width': '200px'}),
                    html.Button('✖', id='btn-search-clear', title='Clear Search', style={'padding': '6px 10px', 'marginRight': '15px', 'backgroundColor': '#FF4136', 'color': 'white', 'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer', 'fontWeight': 'bold'}),
                    html.Button('Zoom In (+)', id='btn-zoom-in', style=btn_style),
                    html.Button('Zoom Out (-)', id='btn-zoom-out', style=btn_style),
                    html.Button('Reset View', id='btn-zoom-reset', style={'padding': '8px 15px', 'backgroundColor': '#AAAAAA', 'color': 'white', 'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer', 'fontWeight': 'bold', 'fontSize': '12px'})
                ], style={'float': 'right'})
            ], style={'padding': '10px 20px', 'backgroundColor': '#ffffff', 'borderBottom': '1px solid #ddd', 'height': '40px'}),
            
            # Graph Canvas
            dcc.Loading(
                id="loading", type="circle",
                children=[
                    cyto.Cytoscape(
                        id='tx-graph',
                        elements=[],
                        layout={'name': 'preset', 'fit': True, 'padding': 50}, 
                        style={'width': '100%', 'height': 'calc(100vh - 120px)', 'backgroundColor': '#ffffff'},
                        stylesheet=[
                            {'selector': 'node', 'style': {'label': 'data(label)', 'text-valign': 'center', 'text-halign': 'center', 'font-size': '12px', 'width': 45, 'height': 45, 'border-width': 2, 'border-color': '#333', 'font-weight': 'bold'}},
                            {'selector': '.center-node', 'style': {'background-color': '#FFDC00', 'width': 65, 'height': 65, 'border-width': 3}},
                            {'selector': '.inbound-node', 'style': {'background-color': '#7FDBFF'}},
                            {'selector': '.outbound-node', 'style': {'background-color': '#2ECC40'}},
                            {'selector': '.app-node', 'style': {'background-color': '#B10DC9', 'color': '#000'}},
                            {'selector': '.mixed-node', 'style': {'background-color': '#FF851B'}},
                            {'selector': 'node.highlighted', 'style': {'border-color': '#FF4136', 'border-width': 5, 'width': 75, 'height': 75, 'z-index': 999}},
                            {'selector': 'node.dimmed', 'style': {'opacity': 0.15, 'background-color': '#ccc', 'border-color': '#ccc', 'color': 'transparent', 'text-outline-width': 0}},
                            {'selector': 'edge', 'style': {
                                'label': 'data(label)', 'font-size': '10px', 'curve-style': 'bezier',
                                'control-point-step-size': 50, # Separate overlapping edges
                                'target-arrow-shape': 'triangle', 'target-arrow-color': '#999',
                                'line-color': '#ddd', 'width': 2, 'text-wrap': 'wrap',
                                'text-rotation': 'autorotate', 'text-margin-y': -12, 
                                'text-outline-color': '#ffffff', 'text-outline-width': 3, 'color': '#222'
                            }},
                            {'selector': 'edge.highlighted', 'style': {'line-color': '#FF4136', 'target-arrow-color': '#FF4136', 'width': 5, 'z-index': 999}},
                            {'selector': 'edge.dimmed', 'style': {'opacity': 0.15, 'line-color': '#eee', 'target-arrow-color': '#eee', 'color': 'transparent', 'text-outline-width': 0}},
                            {'selector': 'node:selected', 'style': {'background-color': '#9CA3AF', 'border-color': '#6B7280', 'border-width': 4}},
                            {'selector': 'edge:selected', 'style': {'line-color': '#9CA3AF', 'target-arrow-color': '#9CA3AF', 'width': 5, 'z-index': 999}},
                        ]
                    )
                ]
            )
        ], style={'flex': '1', 'display': 'flex', 'flexDirection': 'column', 'position': 'relative'}),
        
        # RIGHT SIDEBAR (Details)
        html.Div([
            html.H3("Selection Details", style={'marginTop': '0', 'color': '#333', 'borderBottom': '2px solid #ddd', 'paddingBottom': '10px'}),
            html.Div(id='details-panel', children=html.Div("Click a node or edge to view details.", style={'color': '#888', 'fontStyle': 'italic'}), style={'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all', 'fontSize': '14px', 'lineHeight': '1.6'})
        ], style={'width': '320px', 'minWidth': '320px', 'padding': '20px', 'backgroundColor': '#f4f6f8', 'borderLeft': '1px solid #ddd', 'boxSizing': 'border-box', 'overflowY': 'auto'})
        
    ], style={'display': 'flex', 'flexDirection': 'row', 'height': 'calc(100vh - 65px)', 'fontFamily': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif'})
], style={'margin': '0', 'padding': '0', 'height': '100vh', 'overflow': 'hidden'})

# --------------------------------------------------
# Callbacks
# --------------------------------------------------

# Handle Search Clear Button
@app.callback(
    Output('search-input', 'value'),
    [Input('btn-search-clear', 'n_clicks')]
)
def clear_search(n_clicks):
    if n_clicks:
        return ""
    return dash.no_update

# Handle Zoom Controls
@app.callback(
    Output('tx-graph', 'zoom'),
    [Input('btn-zoom-in', 'n_clicks'),
     Input('btn-zoom-out', 'n_clicks')],
    [State('tx-graph', 'zoom')]
)
def update_zoom(btn_in, btn_out, current_zoom):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
        
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if current_zoom is None:
        current_zoom = 1.0
        
    if trigger_id == 'btn-zoom-in':
        return current_zoom * 1.2
    elif trigger_id == 'btn-zoom-out':
        return current_zoom / 1.2

    return dash.no_update

# Handle Graph Loading, Layout & Search Highlighting
@app.callback(
    [Output('tx-graph', 'elements'),
     Output('tx-graph', 'layout'),
     Output('status-msg', 'children')],
    [Input('analyze-btn', 'n_clicks'),
     Input('layout-toggle', 'value'),
     Input('search-input', 'value'),
     Input('btn-zoom-reset', 'n_clicks')],
    [State('contract-input', 'value'),
     State('tx-graph', 'elements')]
)
def update_graph(n_clicks, layout_mode, search_val, reset_clicks, contract_address, current_elements):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # If reset view or layout toggle was clicked, we just update the layout
    if trigger_id in ['btn-zoom-reset', 'layout-toggle'] and current_elements:
        layout_cfg = {'name': layout_mode, 'fit': True, 'padding': 40, 'animate': True, 'randomize': False, 'seed': random.random()}
        if layout_mode == 'cose':
            layout_cfg.update({'idealEdgeLength': 200, 'nodeRepulsion': 800000, 'nodeOverlap': 50})
        elif layout_mode == 'preset':
            # Force preset layout to use the exact original positions
            node_positions = {el['data']['id']: el.get('position', {'x': 0, 'y': 0}) for el in current_elements if 'source' not in el.get('data', {})}
            layout_cfg.update({'positions': node_positions})
            
        return dash.no_update, layout_cfg, dash.no_update

    # If only search changed, just update classes of existing elements
    if trigger_id == 'search-input' and current_elements:
        search_str = (search_val or "").strip().lower()
        new_elements = []
        
        if not search_str:
            for el in current_elements:
                new_el = el.copy()
                new_el['classes'] = new_el.get('data', {}).get('original_class', '')
                new_elements.append(new_el)
            return new_elements, dash.no_update, dash.no_update
            
        # Pass 1: Find explicit matches
        explicit_node_ids = set()
        explicit_edge_indices = set()
        
        for i, el in enumerate(current_elements):
            data = el.get('data', {})
            is_edge = 'source' in data and 'target' in data
            
            if not is_edge:
                # It's a node
                node_id = data.get('id', '')
                if search_str in node_id.lower() or search_str in data.get('label', '').lower():
                    explicit_node_ids.add(node_id)
            else:
                # It's an edge
                if search_str in data.get('label', '').lower() or any(search_str in str(txid).lower() for txid in data.get('txids', [])):
                    explicit_edge_indices.add(i)
                    
        # Pass 2: Find connected elements
        connected_node_ids = set()
        connected_edge_indices = set()
        
        for i, el in enumerate(current_elements):
            data = el.get('data', {})
            is_edge = 'source' in data and 'target' in data
            
            if is_edge:
                src = data['source']
                tgt = data['target']
                
                # If this edge connects to an explicitly matched node
                if src in explicit_node_ids or tgt in explicit_node_ids:
                    connected_edge_indices.add(i)
                    connected_node_ids.add(src)
                    connected_node_ids.add(tgt)
                    
                # If this edge is explicitly matched
                if i in explicit_edge_indices:
                    connected_node_ids.add(src)
                    connected_node_ids.add(tgt)
                    
        # Pass 3: Apply classes
        for i, el in enumerate(current_elements):
            new_el = el.copy()
            data = new_el.get('data', {})
            is_edge = 'source' in data and 'target' in data
            classes = data.get('original_class', '')
            
            if not is_edge:
                node_id = data.get('id', '')
                if node_id in explicit_node_ids:
                    classes += ' highlighted'
                elif node_id in connected_node_ids:
                    pass # unchanged
                else:
                    classes += ' dimmed'
            else:
                if i in explicit_edge_indices:
                    classes += ' highlighted'
                elif i in connected_edge_indices:
                    pass # unchanged
                else:
                    classes += ' dimmed'
                    
            new_el['classes'] = classes.strip()
            new_elements.append(new_el)
            
        return new_elements, dash.no_update, dash.no_update

    # Otherwise, rebuild the graph
    if not contract_address:
        return [], {'name': layout_mode}, "Please enter a valid address."
        
    contract_address = contract_address.strip()
    txs = fetch_transactions(contract_address)
    
    if not txs:
        return [], {'name': layout_mode}, f"No transactions found for {short_addr(contract_address)}"
        
    df = parse_transactions(txs)
    elements = build_cytoscape_elements(df, contract_address)
    
    # Configure the chosen layout parameters
    layout_cfg = {'name': layout_mode, 'fit': True, 'padding': 40, 'animate': True, 'randomize': False, 'seed': random.random()}
    if layout_mode == 'cose':
        layout_cfg.update({'idealEdgeLength': 200, 'nodeRepulsion': 800000, 'nodeOverlap': 50})
    elif layout_mode == 'preset':
        node_positions = {el['data']['id']: el.get('position', {'x': 0, 'y': 0}) for el in elements if 'source' not in el.get('data', {})}
        layout_cfg.update({'positions': node_positions})
        
    stats_msg = f"🟢 Loaded {len(df)} txs | {len(elements)} elements"
    return elements, layout_cfg, stats_msg

# Handle Node / Edge Details (Using Pera Explorer)
@app.callback(
    Output('details-panel', 'children'),
    [Input('tx-graph', 'selectedNodeData'),
     Input('tx-graph', 'selectedEdgeData')]
)
def display_details(node_data_list, edge_data_list):
    if not node_data_list and not edge_data_list:
        return html.Div("Click a node or edge to view details.", style={'color': '#888', 'fontStyle': 'italic'})
        
    if node_data_list:
        node_data = node_data_list[0]
        is_app = str(node_data.get('full_address')).startswith("App-")
        # Ensure we strip 'App-' to get just the ID for the URL
        clean_addr = str(node_data.get('full_address')).replace('App-', '')
        
        # Use PeraWallet Testnet Explorer
        explorer_url = f"https://testnet.explorer.perawallet.app/application/{clean_addr}" if is_app else f"https://testnet.explorer.perawallet.app/address/{clean_addr}"
        
        return html.Div([
            html.Div([html.B("Node Type"), html.Br(), "🖥️ Application" if is_app else "👤 Account / Contract"], style={'marginBottom': '15px'}),
            html.Div([html.B("Short ID"), html.Br(), html.Code(node_data.get('label'), style={'backgroundColor': '#e8e8e8', 'padding': '2px 6px', 'borderRadius': '3px'})], style={'marginBottom': '15px'}),
            html.Div([html.B("Full Address / ID"), html.Br(), html.Div(node_data.get('full_address'), style={'wordBreak': 'break-all', 'backgroundColor': '#fff', 'border': '1px solid #ddd', 'padding': '8px', 'borderRadius': '4px', 'marginTop': '5px'})], style={'marginBottom': '20px'}),
            html.A("🔗 View on Pera Explorer", href=explorer_url, target="_blank", style={'display': 'inline-block', 'width': '100%', 'textAlign': 'center', 'padding': '10px 0', 'backgroundColor': '#0074D9', 'color': 'white', 'textDecoration': 'none', 'borderRadius': '4px', 'fontWeight': 'bold'})
        ])
        
    elif edge_data_list:
        edge_data = edge_data_list[0]
        txids = edge_data.get('txids', [])
        txid_divs = []
        
        # Display all TxIDs
        for t in txids:
            txid_divs.append(html.Div(t, style={'wordBreak': 'break-all', 'fontSize': '12px', 'fontFamily': 'monospace', 'backgroundColor': '#fff', 'border': '1px solid #ddd', 'padding': '4px', 'borderRadius': '3px', 'marginBottom': '4px'}))
            
        return html.Div([
            html.Div([html.B("Transaction Type"), html.Br(), f"🔄 {edge_data.get('type')}"], style={'marginBottom': '15px'}),
            html.Div([html.B("From"), html.Br(), html.Div(edge_data.get('source'), style={'wordBreak': 'break-all', 'color': '#d9534f'})], style={'marginBottom': '15px'}),
            html.Div([html.B("To"), html.Br(), html.Div(edge_data.get('target'), style={'wordBreak': 'break-all', 'color': '#5cb85c'})], style={'marginBottom': '15px'}),
            html.Div([html.B("Total Amount"), html.Br(), html.Span(f"{edge_data.get('amount', 0):.4f} ALGO", style={'fontSize': '18px', 'fontWeight': 'bold', 'color': '#333'})], style={'marginBottom': '15px'}),
            html.Div([html.B("Transaction Count"), html.Br(), html.Span(str(edge_data.get('count')), style={'fontSize': '16px'})], style={'marginBottom': '15px'}),
            html.Div([html.B("Transaction IDs"), html.Br(), html.Div(txid_divs, style={'maxHeight': '300px', 'overflowY': 'auto', 'paddingRight': '5px'})], style={'marginBottom': '15px'})
        ])
        
    return html.Div("Click a node or edge to view details.", style={'color': '#888', 'fontStyle': 'italic'})

def open_browser():
    webbrowser.open_new("http://127.0.0.1:8050/")

if __name__ == '__main__':
    print("Starting Obscura Lens...")
    print("Opening http://127.0.0.1:8050/ in your browser...")
    
    # Only open browser once (prevents double-opening due to Flask's auto-reloader)
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1.25, open_browser).start()
        
    app.run(debug=False)