# --- Imports and Initial Setup ---
import os
from dotenv import load_dotenv
from typing import Dict, List, Optional
import time
import asyncio
import aiohttp
from web3 import Web3
import joblib
import requests
from web3.exceptions import InvalidAddress
import logging
import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env file for local development
load_dotenv()

def get_secret(key):
    """
    Universal secret getter that works:
    - Locally with .env files
    - Locally with Streamlit secrets
    - On Streamlit Cloud with secrets
    - With system environment variables
    """
    # Method 1: Try Streamlit secrets (only if streamlit is available)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except (ImportError, AttributeError, KeyError):
        pass
    
    # Method 2: Try environment variables (from .env or system)
    env_value = os.getenv(key)
    if env_value:
        return env_value
    
    # Method 3: Return None if not found
    return None

WEB3_PROVIDER_URL = get_secret("WEB3_PROVIDER_URL")
COINGECKO_API_KEY = get_secret("COINGECKO_API_KEY")

# Validation
if not WEB3_PROVIDER_URL:
    print("ERROR: Missing WEB3_PROVIDER_URL environment variable")
    exit(1)

# CoinGecko is now optional (fallback only)
if not COINGECKO_API_KEY:
    print("⚠️ COINGECKO_API_KEY not found. Using basic pricing only.")
    logger.warning("No CoinGecko API key found, limited pricing available")

# ERC-20 ABI: A minimal contract ABI to interact with ERC-20 tokens.
ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"}
]

# Database Cache settings
DATABASE_FOLDER = 'database'
TOKEN_DATABASE_CACHE = os.path.join(DATABASE_FOLDER, 'token_price_database.joblib')
CACHE_EXPIRATION_TIME = 30 * 60  # 30 minutes
MAX_TOKEN_PRICE = 200000.0

# Global Web3 instance 
w3: Optional[Web3] = None
web3_initialized = False

def initialize_web3_connection() -> bool:
    """Initialize Web3 connection lazily when needed."""
    global w3, web3_initialized
    
    if web3_initialized:
        return w3 is not None
    
    try:
        # Create Web3 instance with timeout
        w3 = Web3(Web3.HTTPProvider(
            WEB3_PROVIDER_URL,
            request_kwargs={
                'timeout': 20,
                'headers': {
                    'User-Agent': 'CryptoPortfolioTracker/1.0'
                }
            }
        ))
        
        web3_initialized = True
        logger.info("Web3 instance created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Web3: {e}")
        w3 = None
        web3_initialized = True
        return False

def test_web3_connection() -> bool:
    """Test Web3 connection only when needed."""
    if not initialize_web3_connection():
        return False
    
    try:
        # Simple test - get latest block number
        block_number = w3.eth.block_number
        logger.info(f"Web3 connected. Latest block: {block_number}")
        return True
    except Exception as e:
        logger.error(f"Web3 connection test failed: {e}")
        return False

def check_api_keys() -> Dict[str, bool]:
    """Check API keys without initializing connections that might cause recursion."""
    return {
        "web3": bool(WEB3_PROVIDER_URL),  # Just check if URL exists
        "coingecko": bool(COINGECKO_API_KEY)
    }

def validate_ethereum_address(address: str) -> bool:
    """Validate if a given string is a valid Ethereum address."""
    if not address or not isinstance(address, str):
        return False
    
    try:
        # Use Web3's static method (doesn't need connection)
        return Web3.is_address(address)
    except Exception as e:
        logger.error(f"Error validating address {address}: {e}")
        return False

def get_eth_balance(wallet_address: str) -> float:
    """Retrieve the native ETH balance of a wallet address."""
    if not test_web3_connection():
        logger.error("Web3 connection not available")
        return 0.0
        
    try:
        if not validate_ethereum_address(wallet_address):
            logger.error(f"Invalid ETH address provided: {wallet_address}")
            return 0.0
        
        # Get balance in Wei and convert to Ether
        balance_wei = w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
        return float(Web3.from_wei(balance_wei, 'ether'))
        
    except Exception as e:
        logger.error(f"Error getting ETH balance for {wallet_address}: {e}")
        return 0.0

def get_token_info_and_balance(wallet_address: str, contract_address: str) -> Dict:
    """Fetch ERC-20 token info and balance for a wallet."""
    if not test_web3_connection():
        logger.error("Web3 connection not available")
        return {"address": contract_address, "symbol": "Error", "name": "Web3 Not Connected", "balance": 0.0, "decimals": 18}
    
    try:
        if not validate_ethereum_address(wallet_address) or not validate_ethereum_address(contract_address):
            return {"address": contract_address, "symbol": "Invalid", "name": "Invalid Address", "balance": 0.0, "decimals": 18}

        # Create contract instance
        token_contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), 
            abi=ERC20_ABI
        )
        
        # Get token information with individual try-catch blocks
        balance_wei = 0
        decimals = 18
        symbol = "Unknown"
        name = "Unknown Token"
        
        try:
            balance_wei = token_contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
        except Exception as e:
            logger.error(f"Error getting balance for {contract_address}: {e}")
        
        try:
            decimals = token_contract.functions.decimals().call()
        except Exception as e:
            logger.error(f"Error getting decimals for {contract_address}: {e}")
            
        try:
            symbol = token_contract.functions.symbol().call()
        except Exception as e:
            logger.error(f"Error getting symbol for {contract_address}: {e}")
            
        try:
            name = token_contract.functions.name().call()
        except Exception as e:
            logger.error(f"Error getting name for {contract_address}: {e}")
            name = symbol  # Fallback to symbol

        # Convert balance from Wei-like units to readable float
        balance = balance_wei / (10 ** decimals) if decimals > 0 else 0

        return {
            "address": contract_address.lower(),
            "symbol": symbol,
            "name": name,
            "balance": float(balance),
            "decimals": decimals
        }
        
    except Exception as e:
        logger.error(f"Error getting token info for {contract_address}: {e}")
        return {
            "address": contract_address.lower(), 
            "symbol": "Error", 
            "name": "Token Read Error", 
            "balance": 0.0, 
            "decimals": 18
        }

def get_eth_price() -> Dict:
    # Check CoinGecko if available
    if COINGECKO_API_KEY:
        try:
            url = "https://pro-api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": "ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true"
            }
            headers = {"x-cg-pro-api-key": COINGECKO_API_KEY}
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            eth_data = data.get("ethereum", {})
            price = eth_data.get("usd", 0.0)
            change = eth_data.get("usd_24h_change", 0.0)
            
            logger.info(f"Got ETH price from CoinGecko: ${price:.2f}")
            return {"price": price, "change_24h": change, "source": "coingecko"}
            
        except Exception as e:
            logger.error(f"Error getting ETH price from CoinGecko: {e}")
    
    logger.warning("Could not get ETH price from any source")
    return {"price": 0.0, "change_24h": 0.0, "source": "failed"}

# --- Asynchronous Functions ---

async def get_held_tokens_alchemy(wallet_address: str, session: aiohttp.ClientSession) -> List[str]:
    """Get tokens with non-zero balances using Alchemy."""
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid wallet address provided to Alchemy function")
        return []
    
    headers = {"accept": "application/json", "content-type": "application/json"}
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getTokenBalances",
        "params": [Web3.to_checksum_address(wallet_address), "erc20"]
    }
    
    try:
        async with session.post(WEB3_PROVIDER_URL, headers=headers, json=payload, timeout=30) as response:
            response.raise_for_status()
            data = await response.json()
            
            token_addresses = []
            if "result" in data and "tokenBalances" in data["result"]:
                for token_info in data["result"]["tokenBalances"]:
                    if token_info["tokenBalance"] != "0x0":
                        token_addresses.append(token_info["contractAddress"].lower())
                        
            logger.info(f"Found {len(token_addresses)} tokens with non-zero balances")
            return token_addresses
            
    except Exception as e:
        logger.error(f"Error getting held tokens from Alchemy: {e}")
        return []

async def fetch_coingecko_prices(session: aiohttp.ClientSession, tokens: List[str]) -> Dict:
    """Fetch prices from CoinGecko"""
    if not tokens or not COINGECKO_API_KEY:
        return {}

    logger.info(f"Fetching fallback prices for {len(tokens)} tokens from CoinGecko...")
    
    all_prices = {}
    headers = {"accept": "application/json", "x-cg-pro-api-key": COINGECKO_API_KEY}
    
    # Process in smaller chunks for better reliability
    chunk_size = 15
    for i in range(0, len(tokens), chunk_size):
        chunk = tokens[i:i + chunk_size]
        contract_addresses_str = ','.join(chunk)
        url = f"https://pro-api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={contract_addresses_str}&vs_currencies=usd&include_24hr_change=true"

        for attempt in range(2):  # Reduced attempts for fallback
            try:
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status == 429:
                        wait_time = 2 ** attempt
                        logger.warning(f"CoinGecko rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    if response.status == 200:
                        data = await response.json()
                        
                        if isinstance(data, dict):
                            for contract, price_info in data.items():
                                if contract and isinstance(price_info, dict) and "usd" in price_info:
                                    price = price_info.get("usd", 0.0)
                                    if 0 < price <= MAX_TOKEN_PRICE:
                                        all_prices[contract.lower()] = {
                                            "price": price,
                                            "change_24h": price_info.get("usd_24h_change", 0.0),
                                            "source": "coingecko"
                                        }
                                        logger.debug(f"CoinGecko: {contract} = ${price:.6f}")
                    break
                    
            except Exception as e:
                logger.error(f"CoinGecko fallback error: {e}")
                if attempt == 1:
                    break

        await asyncio.sleep(0.3)  # Rate limiting

    logger.info(f"CoinGecko fallback: Found prices for {len(all_prices)} tokens")
    return all_prices

def save_token_database(tokens: Dict):
    """Save token price cache."""
    try:
        joblib.dump(tokens, TOKEN_DATABASE_CACHE)
        logger.info(f"Saved {len(tokens)} tokens to cache")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def load_or_create_token_database() -> Dict:
    """Load token price cache."""
    os.makedirs(DATABASE_FOLDER, exist_ok=True)
    
    try:
        tokens = joblib.load(TOKEN_DATABASE_CACHE)
        logger.info(f"Loaded {len(tokens)} tokens from cache")
        
        # Clean expired entries
        cleaned_tokens = {}
        current_time = time.time()
        
        for addr, data in tokens.items():
            if (isinstance(data, dict) and 
                "price" in data and 
                "timestamp" in data and
                current_time - data["timestamp"] <= CACHE_EXPIRATION_TIME):
                cleaned_tokens[addr] = data
        
        if len(cleaned_tokens) < len(tokens):
            logger.info(f"Cleaned {len(tokens) - len(cleaned_tokens)} expired entries")
            save_token_database(cleaned_tokens)
        
        return cleaned_tokens
        
    except FileNotFoundError:
        logger.info("No cache found, starting fresh")
        return {}
    except Exception as e:
        logger.error(f"Cache error: {e}, starting fresh")
        return {}

async def get_portfolio_data(wallet_address: str) -> Dict:
    """Main function to get a full portfolio breakdown: ETH balance, token balances, and their values."""
    logger.info(f"Analyzing portfolio for {wallet_address}")

    # Load the local token price cache.
    token_database = load_or_create_token_database()

    # Get ETH balance and its price.
    eth_balance = get_eth_balance(wallet_address)
    eth_price_data = get_eth_price()

    # Initialize the portfolio dictionary.
    portfolio = {
        "wallet_address": wallet_address,
        "eth_balance": eth_balance,
        "eth_price": eth_price_data["price"],
        "eth_change_24h": eth_price_data["change_24h"],
        "eth_value": eth_balance * eth_price_data["price"],
        "tokens": [],
        "total_value": eth_balance * eth_price_data["price"],
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Fetch held tokens from Alchemy API.
    async with aiohttp.ClientSession() as session:
        held_token_addresses = await get_held_tokens_alchemy(wallet_address, session)

        # Identify which token prices need to be fetched (not in cache or expired).
        missing_tokens = []
        for addr in held_token_addresses:
            addr_lower = addr.lower()
            if addr_lower not in token_database or (token_database[addr_lower].get("timestamp", 0) < time.time() - CACHE_EXPIRATION_TIME):
                missing_tokens.append(addr)
            else:
                logger.debug(f"Using cached price for {addr_lower}: ${token_database[addr_lower]['price']:.8f}")

        # Fetch prices for missing tokens and update the cache.
        if missing_tokens:
            logger.info(f"Fetching prices for {len(missing_tokens)} tokens...")
            new_prices = await fetch_coingecko_prices(session, missing_tokens)
            for addr, price_data in new_prices.items():
                token_database[addr.lower()] = {
                    "price": price_data["price"],
                    "change_24h": price_data["change_24h"],
                    "source": price_data["source"],
                    "timestamp": time.time()
                }
            save_token_database(token_database)
        else:
            logger.info("All token prices are in the cache and up-to-date.")

        # Process all held tokens to get their details and calculate values.
        if held_token_addresses:
            logger.info(f"Processing {len(held_token_addresses)} tokens...")

            # Run balance and info fetching concurrently using asyncio.to_thread for blocking calls.
            token_info_tasks = [
                asyncio.to_thread(get_token_info_and_balance, wallet_address, addr)
                for addr in held_token_addresses
            ]

            token_infos = await asyncio.gather(*token_info_tasks)

            # Build the final portfolio data structure.
            for token_info in token_infos:
                if token_info["balance"] > 0:
                    addr_lower = token_info["address"].lower()
                    price_data = token_database.get(addr_lower, {"price": 0.0, "change_24h": None, "source": "none", "timestamp": 0})

                    token_info.update({
                        "price": price_data["price"],
                        "change_24h": price_data["change_24h"],
                        "price_source": price_data["source"],
                        "value": token_info["balance"] * price_data["price"]
                    })

                    portfolio["tokens"].append(token_info)
                    portfolio["total_value"] += token_info["value"]

    # Sort tokens by value in descending order.
    portfolio["tokens"].sort(key=lambda x: x["value"], reverse=True)

    logger.info(f"Portfolio analysis complete. Total value: ${portfolio['total_value']:,.2f}")
    return portfolio

# --- Main Execution ---
async def main():
    """Main execution function."""
    wallet_address = "0x226cc0Bae5251EBb637B9ecF5B1CdB99764abBCD"

    logger.info("Starting simplified portfolio analysis (CoinGecko pricing)...")
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid Ethereum address")
        return

    # Get portfolio data
    portfolio = await get_portfolio_data(wallet_address)
    
    if "error" in portfolio:
        print(f"Error: {portfolio['error']}")
        return

    # Print results
    print("\n" + "="*60)
    print(f"Portfolio Summary for {portfolio['wallet_address']}")
    print("="*60)
    print(f"ETH Balance: {portfolio['eth_balance']:.4f} ETH")
    print(f"ETH Price: ${portfolio['eth_price']:,.2f} ({portfolio['eth_change_24h']:+.2f}%)")
    print(f"ETH Value: ${portfolio['eth_value']:,.2f}")
    print(f"Total Portfolio: ${portfolio['total_value']:,.2f}")
    print(f"Tokens: {len(portfolio['tokens'])}")

    if portfolio['tokens']:
        print(f"\nTop 10 Holdings:")
        print("-" * 90)
        print(f"{'Token':<20} {'Balance':<15} {'Price':<15} {'Value':<12} {'24h':<10} {'Source':<12}")
        print("-" * 90)

        for token in portfolio['tokens'][:10]:
            balance_str = f"{token['balance']:.4f}"
            price_str = f"${token['price']:.8f}" if token['price'] < 0.01 else f"${token['price']:,.4f}"
            value_str = f"${token['value']:,.2f}"
            
            # Fixed: Handle None values properly
            change_24h = token.get('change_24h')
            if change_24h is not None and change_24h != 0:
                change_str = f"{change_24h:+.2f}%"
            else:
                change_str = "N/A"
            
            source_str = token.get('price_source', 'none')[:12]

            print(f"{token['symbol']:<20} {balance_str:<15} {price_str:<15} {value_str:<12} {change_str:<10} {source_str:<12}")

if __name__ == "__main__":
    asyncio.run(main())