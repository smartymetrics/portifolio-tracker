import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import asyncio

# ========================================
# SETUP AND IMPORTS
# ========================================

# Add backend folder to path so we can import our custom functions
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    # Import our custom API functions from the backend directory
    from backend.api_functions import (
        get_portfolio_data, 
        check_api_keys, 
        validate_ethereum_address,
        load_or_create_token_database
        )
except ImportError:
    # If imports fail, show error and stop the app
    st.error("⚠️ Could not import API functions. Make sure api_functions.py is in the backend folder.")
    st.stop()

# ========================================
# PAGE CONFIGURATION AND STYLING
# ========================================

# Configure Streamlit page settings
st.set_page_config(
    page_title="Crypto Portfolio Tracker",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling the app interface
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

# ========================================
# MAIN APPLICATION FUNCTION
# ========================================

def main():
    """Main application function that handles the UI and user interactions"""
    
    # Display main header with custom styling
    st.markdown('<h1 class="main-header">🔍 Crypto Portfolio Tracker</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # ========================================
    # SIDEBAR: API STATUS AND SAMPLE WALLETS
    # ========================================
    
    with st.sidebar:
        # Display Ethereum logo and sidebar title
        st.image("https://pbs.twimg.com/profile_images/1806587073492586497/XKkVaB4g_400x400.jpg", width=100)
        st.title("Portfolio Settings")
        
        # Check and display API connection status
        api_status = check_api_keys()
        st.subheader("API Status")
        
        # Show API status in three columns
        col1, col2 = st.columns(2)
        # with col1:
        #     if api_status["web3"]:
        #         st.success("✅ Alchemy")
        #     else:
        #         st.error("❌ Alchemy")
        
        with col1:
            if api_status["coingecko"]:
                st.success("✅ CoinGecko")
            else:
                st.error("❌ CoinGecko")
            
        with col2:
            if api_status["etherscan"]:
                st.success("✅ Etherscan")
            else:
                st.error("❌ Etherscan")
        
        # Stop the app if API keys are missing
        if not all(api_status.values()):
            st.error("⚠️ Please check your API keys in the backend/api_functions.py file.")
            st.stop()
        
        st.markdown("---")
        
        # Provide sample wallet addresses for testing
        st.subheader("Sample Wallets")
        sample_wallets = {
            "Ethereum Foundation": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
            "Vitalik Buterin": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            "Sample Wallet": "0x742d35Cc6634C0532925a3b8D6Ac0532eb0F400e"
        }
        
        # Allow user to select and load a sample wallet
        selected_sample = st.selectbox("Choose a sample wallet:", [""] + list(sample_wallets.keys()))
        
        if selected_sample and st.button("Load Sample"):
            # Store selected wallet in session state and refresh
            st.session_state.wallet_input = sample_wallets[selected_sample]
            st.rerun()
    
    # ========================================
    # MAIN CONTENT: WALLET INPUT AND ACTIONS
    # ========================================
    
    # Create two columns for wallet input and action buttons
    col1, col2 = st.columns([2, 1])
    
    # Column 1: Wallet address input
    with col1:
        st.subheader("Enter Wallet Address")
        wallet_address = st.text_input(
            "Ethereum Wallet Address",
            value=st.session_state.get("wallet_input", ""),
            placeholder="0x742d35Cc6634C0532925a3b8D6Ac0532eb0F400e",
            help="Enter a valid Ethereum wallet address starting with 0x"
        )
    
    # Column 2: Action buttons
    with col2:
        st.subheader("Actions")
        
        # Main analyze button
        analyze_button = st.button("🔍 Analyze Portfolio", type="primary", use_container_width=True)
        
        # Update token database button
        if st.button("🔄 Update Token Database", use_container_width=True):
            with st.spinner("Updating comprehensive token database..."):
                load_or_create_token_database()
            st.success("Token database updated! This improves price accuracy.")
        
        # Clear cache button for fresh data
        if st.button("🗑️ Clear Cache", use_container_width=True):
            st.cache_data.clear()
            st.success("Cache cleared! Click Analyze to get fresh data.")
    
    # ========================================
    # PORTFOLIO ANALYSIS LOGIC
    # ========================================
    
    # Trigger analysis when button is clicked or wallet address is entered
    if analyze_button or wallet_address:
        # Validate wallet address input
        if not wallet_address:
            st.warning("⚠️ Please enter a wallet address.")
            return
        
        # Check if the Ethereum address format is valid
        if not validate_ethereum_address(wallet_address):
            st.error("❌ Invalid Ethereum address. Please check the format.")
            return
        
        # Display wallet being analyzed
        st.markdown("---")
        st.subheader("Analyzing Wallet")
        st.markdown(f'<div class="wallet-address">{wallet_address}</div>', unsafe_allow_html=True)
        
        # Fetch portfolio data with loading spinner
        with st.spinner("🔍 Fetching portfolio data via Web3 + Alchemy..."):
            portfolio_data = get_cached_portfolio_data(wallet_address)
        
        # Display results or error message
        if portfolio_data:
            display_portfolio(portfolio_data)
        else:
            st.error("❌ Failed to fetch portfolio data. Please try again.")

# ========================================
# CACHING AND DATA FETCHING
# ========================================

@st.cache_data(ttl=300)  # Cache for 5 minutes to avoid repeated API calls
def get_cached_portfolio_data(wallet_address):
    """
    Get portfolio data with caching - runs the async function and returns serializable data.
    This function handles the async-to-sync conversion and ensures data is cacheable.
    """
    
    # Run the async function to get portfolio data
    portfolio_data = asyncio.run(get_portfolio_data(wallet_address))
    
    # Ensure the data is serializable by converting complex objects to basic types
    if portfolio_data:
        # Convert all values to basic Python types (str, int, float, list, dict)
        # This ensures Streamlit's caching system can properly serialize the data
        serializable_data = {
            'eth_balance': float(portfolio_data.get('eth_balance', 0)),
            'eth_price': float(portfolio_data.get('eth_price', 0)),
            'eth_value': float(portfolio_data.get('eth_value', 0)),
            'eth_change_24h': float(portfolio_data.get('eth_change_24h', 0)),
            'total_value': float(portfolio_data.get('total_value', 0)),
            'tokens': [
                {
                    'name': str(token.get('name', '')),
                    'symbol': str(token.get('symbol', '')),
                    'balance': float(token.get('balance', 0)),
                    'price': float(token.get('price', 0)),
                    'value': float(token.get('value', 0)),
                    'change_24h': float(token.get('change_24h') or 0)
                }
                for token in portfolio_data.get('tokens', [])
            ],
            'last_updated': str(portfolio_data.get('last_updated', datetime.now().isoformat()))
        }
        return serializable_data
    
    return portfolio_data

# ========================================
# PORTFOLIO DISPLAY FUNCTIONS
# ========================================

def display_portfolio(portfolio_data):
    """Display portfolio data in a beautiful, organized format with charts and metrics"""
    
    # ========================================
    # PORTFOLIO OVERVIEW METRICS
    # ========================================
    
    st.markdown("---")
    st.subheader("📊 Portfolio Overview")
    
    # Display key metrics in four columns
    col1, col2, col3, col4 = st.columns(4)
    
    # ETH Balance with 24h change
    with col1:
        eth_change_color = "green" if portfolio_data["eth_change_24h"] >= 0 else "red"
        st.metric(
            "ETH Balance", 
            f"{portfolio_data['eth_balance']:.4f} ETH",
            f"{portfolio_data['eth_change_24h']:.2f}% (24h)"
        )
    
    # Current ETH Price
    with col2:
        st.metric(
            "ETH Price", 
            f"${portfolio_data['eth_price']:,.2f}",
            f"{portfolio_data['eth_change_24h']:.2f}%"
        )
    
    # Total ETH Value in USD
    with col3:
        st.metric(
            "ETH Value", 
            f"${portfolio_data['eth_value']:,.2f}"
        )
    
    # Total Portfolio Value (ETH + Tokens)
    with col4:
        st.metric(
            "Total Portfolio", 
            f"${portfolio_data['total_value']:,.2f}",
            help="Total value of ETH + ERC-20 tokens"
        )
    
    # ========================================
    # PORTFOLIO COMPOSITION PIE CHART
    # ========================================
    
    # Only show chart if portfolio has value
    if portfolio_data["total_value"] > 0:
        st.markdown("---")
        st.subheader("🥧 Portfolio Composition")
        
        # Prepare data for pie chart
        chart_data = [{"Asset": "Ethereum (ETH)", "Value": portfolio_data["eth_value"]}]
        
        # Add tokens with positive values to chart data
        for token in portfolio_data["tokens"]:
            if token["value"] > 0:
                chart_data.append({
                    "Asset": f"{token['name']} ({token['symbol']})",
                    "Value": token["value"]
                })
        
        # Create and display pie chart if there are multiple assets
        if len(chart_data) > 1:
            df_chart = pd.DataFrame(chart_data)
            
            # Create interactive pie chart with Plotly
            fig = px.pie(
                df_chart, 
                values="Value", 
                names="Asset",
                title="Portfolio Distribution",
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            
            # Customize chart appearance
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(height=400)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Portfolio only contains ETH. Token balances will appear here when detected.")
    
    # ========================================
    # DETAILED HOLDINGS TABLE
    # ========================================
    
    st.markdown("---")
    st.subheader("💎 Detailed Holdings")
    
    # Display ETH holdings first
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.write("**Ethereum (ETH)**")
    with col2:
        st.write(f"{portfolio_data['eth_balance']:.6f} ETH")
    with col3:
        st.write(f"${portfolio_data['eth_price']:,.2f}")
    with col4:
        st.write(f"**${portfolio_data['eth_value']:,.2f}**")
    
    # Display ERC-20 tokens if any exist
    if portfolio_data["tokens"]:
        st.markdown("**ERC-20 Tokens:**")
        
        # Prepare token data for display
        token_data = []
        for token in portfolio_data["tokens"]:
            # Only show tokens with balance or value
            if token["balance"] > 0 or token["value"] > 0:
                # Format price display based on token value
                change_indicator = "📈" if token["change_24h"] >= 0 else "📉"
                price_str = f"${token['price']:.8f}" if token['price'] > 0 and token['price'] < 0.01 else f"${token['price']:.4f}" if token['price'] > 0 else "N/A"
                
                # Add token to display table
                token_data.append({
                    "Token": f"{token['name']} ({token['symbol']})",
                    "Balance": f"{token['balance']:.6f} {token['symbol']}",
                    "Price": price_str,
                    "24h Change": f"{change_indicator} {token['change_24h']:.2f}%" if token['change_24h'] != 0 else "N/A",
                    "Value": f"${token['value']:.2f}" if token['value'] > 0 else "$0.00"
                })
        
        # Display token table or info message
        if token_data:
            df_tokens = pd.DataFrame(token_data)
            st.dataframe(df_tokens, use_container_width=True, hide_index=True)
        else:
            st.info("No ERC-20 token balances detected or token values are too small to display.")
    else:
        st.info("No ERC-20 token transactions found for this wallet.")
    
    # ========================================
    # PORTFOLIO STATISTICS
    # ========================================
    
    st.markdown("---")
    st.subheader("📈 Portfolio Statistics")
    
    # Display statistics in two columns
    col1, col2 = st.columns(2)
    
    # Left column: General statistics
    with col1:
        st.info(f"**Last Updated:** {portfolio_data['last_updated']}")
        st.info(f"**Number of Assets:** {len([1] + [t for t in portfolio_data['tokens'] if t['value'] > 0])}")
    
    # Right column: Token and dominance statistics
    with col2:
        # Show token statistics if tokens exist
        if portfolio_data["tokens"]:
            total_tokens = len(portfolio_data["tokens"])
            active_tokens = len([t for t in portfolio_data["tokens"] if t['value'] > 0])
            st.info(f"**Active Tokens:** {active_tokens} / {total_tokens}")
        
        # Calculate and display ETH dominance percentage
        eth_dominance = (portfolio_data["eth_value"] / portfolio_data["total_value"]) * 100 if portfolio_data["total_value"] > 0 else 100
        st.info(f"**ETH Dominance:** {eth_dominance:.1f}%")

# ========================================
# APPLICATION ENTRY POINT
# ========================================

if __name__ == "__main__":
    # Run the main application function when script is executed
    main()