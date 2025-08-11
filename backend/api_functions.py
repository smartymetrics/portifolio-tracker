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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env file for local development
load_dotenv()

def get_secret(key):
    """Universal secret getter for environment variables."""
    return os.getenv(key)

WEB3_PROVIDER_URL = get_secret("WEB3_PROVIDER_URL")
COINGECKO_API_KEY = get_secret("COINGECKO_API_KEY")
ETHERSCAN_API_KEY = get_secret("ETHERSCAN_API_KEY")  # Add this to your .env

# Validation
if not WEB3_PROVIDER_URL:
    print("ERROR: Missing WEB3_PROVIDER_URL environment variable")
    exit(1)

if not ETHERSCAN_API_KEY:
    print("ERROR: Missing ETHERSCAN_API_KEY environment variable")
    print("Get one for free at: https://etherscan.io/apis")
    exit(1)

if not COINGECKO_API_KEY:
    print("⚠️ COINGECKO_API_KEY not found. Using basic pricing only.")
    logger.warning("No CoinGecko API key found, limited pricing available")

# ERC-20 ABI
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
        w3 = Web3(Web3.HTTPProvider(
            WEB3_PROVIDER_URL,
            request_kwargs={
                'timeout': 20,
                'headers': {'User-Agent': 'CryptoPortfolioTracker/1.0'}
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
    
def check_api_keys() -> Dict[str, bool]:
    """Check API keys without initializing connections that might cause recursion."""
    return {
        "web3": bool(WEB3_PROVIDER_URL),  # Just check if URL exists
        "coingecko": bool(COINGECKO_API_KEY),
        "etherscan": bool(ETHERSCAN_API_KEY)
    }

def test_web3_connection() -> bool:
    """Test Web3 connection only when needed."""
    if not initialize_web3_connection():
        return False
    
    try:
        block_number = w3.eth.block_number
        logger.info(f"Web3 connected. Latest block: {block_number}")
        return True
    except Exception as e:
        logger.error(f"Web3 connection test failed: {e}")
        return False

def validate_ethereum_address(address: str) -> bool:
    """Validate if a given string is a valid Ethereum address."""
    if not address or not isinstance(address, str):
        return False
    
    try:
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

        token_contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), 
            abi=ERC20_ABI
        )
        
        # Get token information with error handling
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
            name = symbol

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
    """Get ETH price from CoinGecko."""
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

# --- Etherscan API Functions ---

async def get_held_tokens_etherscan(wallet_address: str, session: aiohttp.ClientSession) -> List[str]:
    """Get tokens with non-zero balances using Etherscan API."""
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid wallet address provided to Etherscan function")
        return []
    
    # Etherscan API endpoint for ERC-20 token transfers
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokentx",
        "address": wallet_address,
        "page": 1,
        "offset": 1000,  # Get last 1000 transactions
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        async with session.get(url, params=params, timeout=30) as response:
            response.raise_for_status()
            data = await response.json()
            
            if data.get("status") == "1" and "result" in data:
                # Extract unique token contract addresses
                token_addresses = set()
                
                for tx in data["result"]:
                    contract_address = tx.get("contractAddress", "").lower()
                    if contract_address and validate_ethereum_address(contract_address):
                        token_addresses.add(contract_address)
                
                logger.info(f"Etherscan found {len(token_addresses)} unique token contracts from transaction history")
                return list(token_addresses)
            else:
                logger.warning(f"Etherscan API returned status: {data.get('status')}, message: {data.get('message')}")
                return []
                
    except Exception as e:
        logger.error(f"Error getting held tokens from Etherscan: {e}")
        return []

async def get_token_balances_etherscan(wallet_address: str, session: aiohttp.ClientSession) -> List[Dict]:
    """Get current token balances using Etherscan API."""
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid wallet address provided to Etherscan function")
        return []
    
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokenbalance",
        "address": wallet_address,
        "tag": "latest",
        "apikey": ETHERSCAN_API_KEY
    }
    
    # This is a simpler approach - we'll get token addresses first, then check balances
    token_addresses = await get_held_tokens_etherscan(wallet_address, session)
    
    # Add known important tokens that might not show up in recent transactions
    important_tokens = [
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
        "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
        "0xa0b86a33e6dd835b44f4164b67c7dd14c4c7f5cf",  # USDC
        "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
        "0x514910771af9ca656af840dff83e8264ecf986ca",  # LINK
        "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",  # UNI
    ]
    
    # Combine discovered tokens with known important tokens
    all_tokens = list(set(token_addresses + [addr.lower() for addr in important_tokens]))
    
    logger.info(f"Checking balances for {len(all_tokens)} tokens (including important tokens)")
    return all_tokens

async def fetch_coingecko_prices(session: aiohttp.ClientSession, tokens: List[str]) -> Dict:
    """Fetch prices from CoinGecko"""
    if not tokens or not COINGECKO_API_KEY:
        return {}

    logger.info(f"Fetching prices for {len(tokens)} tokens from CoinGecko...")
    
    all_prices = {}
    headers = {"accept": "application/json", "x-cg-pro-api-key": COINGECKO_API_KEY}
    
    # Process in chunks
    chunk_size = 15
    for i in range(0, len(tokens), chunk_size):
        chunk = tokens[i:i + chunk_size]
        contract_addresses_str = ','.join(chunk)
        url = f"https://pro-api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={contract_addresses_str}&vs_currencies=usd&include_24hr_change=true"

        for attempt in range(2):
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
                logger.error(f"CoinGecko error: {e}")
                if attempt == 1:
                    break

        await asyncio.sleep(0.5)  # Rate limiting

    logger.info(f"CoinGecko: Found prices for {len(all_prices)} tokens")
    return all_prices

def save_token_database(tokens: Dict):
    """Save token price cache."""
    try:
        os.makedirs(DATABASE_FOLDER, exist_ok=True)
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

async def get_portfolio_data(wallet_address: str, debug_mode: bool = False) -> Dict:
    """Main function to get portfolio data using Etherscan API."""
    logger.info(f"Analyzing portfolio for {wallet_address} using Etherscan API")

    # Load token price cache
    token_database = load_or_create_token_database()

    # Get ETH balance and price
    eth_balance = get_eth_balance(wallet_address)
    eth_price_data = get_eth_price()

    # Initialize portfolio
    portfolio = {
        "wallet_address": wallet_address,
        "eth_balance": eth_balance,
        "eth_price": eth_price_data["price"],
        "eth_change_24h": eth_price_data["change_24h"],
        "eth_value": eth_balance * eth_price_data["price"],
        "tokens": [],
        "total_value": eth_balance * eth_price_data["price"],
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "debug_info": [] if debug_mode else None
    }

    # Get token addresses using Etherscan
    async with aiohttp.ClientSession() as session:
        held_token_addresses = await get_token_balances_etherscan(wallet_address, session)

        if debug_mode:
            portfolio["debug_info"].append(f"Found {len(held_token_addresses)} token addresses from Etherscan")
            portfolio["debug_info"].append(f"First 10 addresses: {held_token_addresses[:10]}")

        # Check for missing prices
        missing_tokens = []
        for addr in held_token_addresses:
            addr_lower = addr.lower()
            if addr_lower not in token_database or (token_database[addr_lower].get("timestamp", 0) < time.time() - CACHE_EXPIRATION_TIME):
                missing_tokens.append(addr)

        # Fetch prices for missing tokens
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

        # Get token balances and info
        if held_token_addresses:
            logger.info(f"Processing {len(held_token_addresses)} tokens...")

            # Get token info concurrently
            token_info_tasks = [
                asyncio.to_thread(get_token_info_and_balance, wallet_address, addr)
                for addr in held_token_addresses
            ]

            token_infos = await asyncio.gather(*token_info_tasks)

            # Build portfolio
            for i, token_info in enumerate(token_infos):
                addr_lower = token_info["address"].lower()
                
                if debug_mode:
                    portfolio["debug_info"].append(f"Token {i+1}: {token_info['symbol']} - Balance: {token_info['balance']:.8f}")
                
                # Include tokens with any balance > 0
                if token_info["balance"] > 0:
                    price_data = token_database.get(addr_lower, {"price": 0.0, "change_24h": None, "source": "none", "timestamp": 0})

                    # Special handling for WETH
                    if token_info["symbol"].upper() == "WETH" and price_data["price"] == 0.0:
                        price_data = {
                            "price": eth_price_data["price"],
                            "change_24h": eth_price_data["change_24h"],
                            "source": "eth_price_mirror",
                            "timestamp": time.time()
                        }
                        logger.info(f"Using ETH price for WETH: ${price_data['price']:.2f}")

                    token_info.update({
                        "price": price_data["price"],
                        "change_24h": price_data["change_24h"],
                        "price_source": price_data["source"],
                        "value": token_info["balance"] * price_data["price"]
                    })

                    portfolio["tokens"].append(token_info)
                    portfolio["total_value"] += token_info["value"]
                    
                    if debug_mode:
                        portfolio["debug_info"].append(f"  ✅ Added: {token_info['symbol']} = ${token_info['value']:.2f}")

    # Sort by value
    portfolio["tokens"].sort(key=lambda x: x["value"], reverse=True)

    logger.info(f"Portfolio analysis complete. Total value: ${portfolio['total_value']:,.2f}")
    return portfolio

# --- Main Execution ---
async def main():
    """Main execution function."""
    wallet_address = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"

    logger.info("Starting portfolio analysis with Etherscan API...")
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid Ethereum address")
        return

    # Get portfolio data
    portfolio = await get_portfolio_data(wallet_address, debug_mode=True)
    
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
    print(f"Tokens Found: {len(portfolio['tokens'])}")

    # Show debug info
    if portfolio.get("debug_info"):
        print(f"\nDEBUG INFO:")
        for info in portfolio["debug_info"]:
            print(f"  • {info}")

    if portfolio['tokens']:
        print(f"\nAll Token Holdings:")
        print("-" * 110)
        print(f"{'Token':<20} {'Balance':<18} {'Price':<15} {'Value':<12} {'24h Change':<12} {'Source':<12}")
        print("-" * 110)

        for token in portfolio['tokens']:
            balance_str = f"{token['balance']:.8f}"
            price_str = f"${token['price']:.8f}" if token['price'] < 0.01 else f"${token['price']:,.4f}"
            value_str = f"${token['value']:,.2f}"
            
            change_24h = token.get('change_24h')
            if change_24h is not None and change_24h != 0:
                change_str = f"{change_24h:+.2f}%"
            else:
                change_str = "N/A"
            
            source_str = token.get('price_source', 'none')[:12]

            # Highlight WETH
            symbol_display = token['symbol']
            if token['symbol'].upper() == "WETH":
                symbol_display = f"🔥 {token['symbol']} 🔥"

            print(f"{symbol_display:<20} {balance_str:<18} {price_str:<15} {value_str:<12} {change_str:<12} {source_str:<12}")

    print("\n" + "="*60)
    print("Analysis complete!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())