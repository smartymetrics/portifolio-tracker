"""
Crypto Portfolio Tracker - Streamlit Web App
A beautiful and intuitive interface for tracking crypto portfolios
"""

import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# Add backend folder to path so we can import our functions
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from api_functions import (
        get_portfolio_data, 
        check_api_keys, 
        validate_ethereum_address
    )
except ImportError:
    st.error("⚠️ Could not import API functions. Make sure api_functions.py is in the backend folder.")
    st.stop()

# Page config
st.set_page_config(
    page_title="Crypto Portfolio Tracker",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for beautiful styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    
    .wallet-address {
        font-family: 'Courier New', monospace;
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        font-size: 14px;
    }
    
    .success-message {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .error-message {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Header
    st.markdown('<h1 class="main-header">🔍 Crypto Portfolio Tracker</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.image("https://cryptologos.cc/logos/ethereum-eth-logo.png", width=100)
        st.title("Portfolio Settings")
        
        # API Key Check
        api_status = check_api_keys()
        st.subheader("API Status")
        
        col1, col2 = st.columns(2)
        with col1:
            if api_status["etherscan"]:
                st.success("✅ Etherscan")
            else:
                st.error("❌ Etherscan")
        
        with col2:
            if api_status["coingecko"]:
                st.success("✅ CoinGecko")
            else:
                st.error("❌ CoinGecko")
        
        if not all(api_status.values()):
            st.error("⚠️ Please add your API keys to the .env file")
            st.stop()
        
        st.markdown("---")
        
        # Sample wallets for testing
        st.subheader("Sample Wallets")
        sample_wallets = {
            "Ethereum Foundation": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
            "Vitalik Buterin": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            "Sample Wallet": "0x742d35Cc6634C0532925a3b8D6Ac0532eb0F400e"
        }
        
        selected_sample = st.selectbox("Choose a sample wallet:", [""] + list(sample_wallets.keys()))
        
        if selected_sample and st.button("Load Sample"):
            st.session_state.wallet_input = sample_wallets[selected_sample]
            st.rerun()
    
    # Main content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Enter Wallet Address")
        wallet_address = st.text_input(
            "Ethereum Wallet Address",
            value=st.session_state.get("wallet_input", ""),
            placeholder="0x742d35Cc6634C0532925a3b8D6Ac0532eb0F400e",
            help="Enter a valid Ethereum wallet address starting with 0x"
        )
    
    with col2:
        st.subheader("Actions")
        analyze_button = st.button("🔍 Analyze Portfolio", type="primary", use_container_width=True)
        
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache cleared! Click Analyze to get fresh data.")
    
    # Validate and analyze
    if analyze_button or wallet_address:
        if not wallet_address:
            st.warning("⚠️ Please enter a wallet address.")
            return
        
        if not validate_ethereum_address(wallet_address):
            st.error("❌ Invalid Ethereum address. Please check the format.")
            return
        
        # Show wallet address
        st.markdown("---")
        st.subheader("Analyzing Wallet")
        st.markdown(f'<div class="wallet-address">{wallet_address}</div>', unsafe_allow_html=True)
        
        # Get portfolio data with caching
        with st.spinner("🔍 Fetching portfolio data..."):
            portfolio_data = get_cached_portfolio_data(wallet_address)
        
        if portfolio_data:
            display_portfolio(portfolio_data)
        else:
            st.error("❌ Failed to fetch portfolio data. Please try again.")

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_cached_portfolio_data(wallet_address):
    """Get portfolio data with caching"""
    return get_portfolio_data(wallet_address)

def display_portfolio(portfolio_data):
    """Display portfolio data in a beautiful format"""
    
    # Overview metrics
    st.markdown("---")
    st.subheader("📊 Portfolio Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        eth_change_color = "green" if portfolio_data["eth_change_24h"] >= 0 else "red"
        st.metric(
            "ETH Balance", 
            f"{portfolio_data['eth_balance']:.4f} ETH",
            f"{portfolio_data['eth_change_24h']:.2f}% (24h)"
        )
    
    with col2:
        st.metric(
            "ETH Price", 
            f"${portfolio_data['eth_price']:,.2f}",
            f"{portfolio_data['eth_change_24h']:.2f}%"
        )
    
    with col3:
        st.metric(
            "ETH Value", 
            f"${portfolio_data['eth_value']:,.2f}"
        )
    
    with col4:
        st.metric(
            "Total Portfolio", 
            f"${portfolio_data['total_value']:,.2f}",
            help="Total value of ETH + ERC-20 tokens"
        )
    
    # Portfolio composition chart
    if portfolio_data["total_value"] > 0:
        st.markdown("---")
        st.subheader("🥧 Portfolio Composition")
        
        # Prepare data for pie chart
        chart_data = [{"Asset": "Ethereum (ETH)", "Value": portfolio_data["eth_value"]}]
        
        for token in portfolio_data["tokens"]:
            if token["value"] > 0:
                chart_data.append({
                    "Asset": f"{token['name']} ({token['symbol']})",
                    "Value": token["value"]
                })
        
        if len(chart_data) > 1:
            df_chart = pd.DataFrame(chart_data)
            
            fig = px.pie(
                df_chart, 
                values="Value", 
                names="Asset",
                title="Portfolio Distribution",
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(height=400)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Portfolio only contains ETH. Token balances will appear here when detected.")
    
    # Detailed holdings
    st.markdown("---")
    st.subheader("💎 Detailed Holdings")
    
    # ETH row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.write("**Ethereum (ETH)**")
    with col2:
        st.write(f"{portfolio_data['eth_balance']:.6f} ETH")
    with col3:
        st.write(f"${portfolio_data['eth_price']:,.2f}")
    with col4:
        st.write(f"**${portfolio_data['eth_value']:,.2f}**")
    
    # ERC-20 tokens
    if portfolio_data["tokens"]:
        st.markdown("**ERC-20 Tokens:**")
        
        # Create DataFrame for better display
        token_data = []
        for token in portfolio_data["tokens"]:
            if token["balance"] > 0 or token["value"] > 0:
                change_indicator = "📈" if token["change_24h"] >= 0 else "📉"
                token_data.append({
                    "Token": f"{token['name']} ({token['symbol']})",
                    "Balance": f"{token['balance']:.6f} {token['symbol']}",
                    "Price": f"${token['price']:.6f}" if token['price'] > 0 else "N/A",
                    "24h Change": f"{change_indicator} {token['change_24h']:.2f}%" if token['change_24h'] != 0 else "N/A",
                    "Value": f"${token['value']:.2f}" if token['value'] > 0 else "$0.00"
                })
        
        if token_data:
            df_tokens = pd.DataFrame(token_data)
            st.dataframe(df_tokens, use_container_width=True, hide_index=True)
        else:
            st.info("No ERC-20 token balances detected or token values are too small to display.")
    else:
        st.info("No ERC-20 token transactions found for this wallet.")
    
    # Portfolio statistics
    st.markdown("---")
    st.subheader("📈 Portfolio Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"**Last Updated:** {portfolio_data['last_updated']}")
        st.info(f"**Number of Assets:** {len([1] + [t for t in portfolio_data['tokens'] if t['value'] > 0])}")
    
    with col2:
        if portfolio_data["tokens"]:
            total_tokens = len(portfolio_data["tokens"])
            active_tokens = len([t for t in portfolio_data["tokens"] if t["value"] > 0])
            st.info(f"**Active Tokens:** {active_tokens} / {total_tokens}")
        
        eth_dominance = (portfolio_data["eth_value"] / portfolio_data["total_value"]) * 100 if portfolio_data["total_value"] > 0 else 100
        st.info(f"**ETH Dominance:** {eth_dominance:.1f}%")

if __name__ == "__main__":
    main()