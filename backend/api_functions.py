# --- Imports and Initial Setup ---
import os
from dotenv import load_dotenv
from typing import Dict, List
import time
import asyncio
import aiohttp
from web3 import Web3
import joblib
import requests
from web3.exceptions import InvalidAddress
import logging

# Configure basic logging to provide informative output and error messages.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from a .env file for API keys and sensitive data.
load_dotenv()

# Define and validate environment variables for API endpoints.
WEB3_PROVIDER_URL = os.getenv("WEB3_PROVIDER_URL")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

if not WEB3_PROVIDER_URL:
    logger.error("WEB3_PROVIDER_URL not set in .env file")
    exit(1)
if not COINGECKO_API_KEY:
    logger.error("COINGECKO_API_KEY not set in .env file")
    exit(1)

# Establish a connection to the Ethereum network using the Web3 provider URL.
w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URL))

if w3.is_connected():
    logger.info("Connected to Ethereum network.")
else:
    logger.error("Connection to Ethereum network failed.")
    exit(1)

# --- Constants and Configuration ---
# ERC-20 ABI: A minimal contract ABI to interact with ERC-20 tokens.
# It includes functions to get balance, decimals, symbol, and name.
ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"}
]

# Cache settings for storing token price data locally to reduce API calls.
DATABASE_FOLDER = 'database'
TOKEN_DATABASE_CACHE = os.path.join(DATABASE_FOLDER, 'defillama_token_database.joblib')
CACHE_EXPIRATION_TIME = 30 * 60  # Cache entries expire after 30 minutes.
MAX_TOKEN_PRICE = 200000.0  # Set a max price to filter out potentially erroneous data.

# --- Helper Functions ---

def check_api_keys() -> Dict[str, bool]:
    """Check if API keys are loaded successfully and return a status dictionary."""
    return {"web3": w3.is_connected(), "coingecko": bool(COINGECKO_API_KEY)}

def validate_ethereum_address(address: str) -> bool:
    """Validate if a given string is a valid Ethereum address."""
    try:
        return w3.is_address(address)
    except InvalidAddress:
        return False
    except Exception as e:
        logger.error(f"Error validating address {address}: {e}")
        return False

def get_eth_balance(wallet_address: str, w3: Web3) -> float:
    """Retrieve the native ETH balance of a wallet address."""
    try:
        if not validate_ethereum_address(wallet_address):
            logger.error(f"Invalid ETH address provided: {wallet_address}")
            return 0.0
        # Get balance in Wei and convert to Ether.
        balance_wei = w3.eth.get_balance(w3.to_checksum_address(wallet_address))
        return float(w3.from_wei(balance_wei, 'ether'))
    except Exception as e:
        logger.error(f"Error getting ETH balance for {wallet_address}: {e}")
        return 0.0

def get_token_info_and_balance(wallet_address: str, contract_address: str, w3: Web3) -> Dict:
    """Fetch ERC-20 token info (name, symbol, decimals) and balance for a wallet."""
    try:
        if not validate_ethereum_address(wallet_address) or not validate_ethereum_address(contract_address):
            return {"address": contract_address, "symbol": "Invalid", "name": "Invalid", "balance": 0.0, "decimals": 18}

        # Create a contract instance with its address and ABI.
        token_contract = w3.eth.contract(address=w3.to_checksum_address(contract_address), abi=ERC20_ABI)
        balance_wei = token_contract.functions.balanceOf(w3.to_checksum_address(wallet_address)).call()
        decimals = token_contract.functions.decimals().call()
        symbol = token_contract.functions.symbol().call()

        try:
            name = token_contract.functions.name().call()
        except:
            name = symbol

        # Convert the balance from its smallest unit (Wei-like) to a readable float.
        balance = balance_wei / (10 ** decimals)

        return {
            "address": contract_address.lower(),
            "symbol": symbol,
            "name": name,
            "balance": float(balance),
            "decimals": decimals
        }
    except Exception as e:
        logger.error(f"Error getting token info for {contract_address}: {e}")
        return {"address": contract_address.lower(), "symbol": "Unknown", "name": "Unknown Token", "balance": 0.0, "decimals": 18}

def get_eth_price_sync() -> Dict:
    """Synchronously get the current price of Ethereum from the CoinGecko Pro API."""
    try:
        url = "https://pro-api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "x_cg_pro_api_key": COINGECKO_API_KEY
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        eth_data = data.get("ethereum", {})
        return {
            "price": eth_data.get("usd", 0.0),
            "change_24h": eth_data.get("usd_24h_change", 0.0)
        }
    except Exception as e:
        logger.error(f"Error getting ETH price: {e}")
        return {"price": 0.0, "change_24h": 0.0}

def get_coingecko_token_list() -> List[Dict]:
    """Fetch a list of all supported tokens from CoinGecko to validate contract addresses."""
    try:
        url = "https://pro-api.coingecko.com/api/v3/coins/list?include_platform=true"
        params = {"x_cg_pro-api-key": COINGECKO_API_KEY}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching CoinGecko token list: {e}")
        return []

def is_token_supported(contract_address: str, token_list: List[Dict]) -> bool:
    """Check if a specific contract address exists in the CoinGecko token list."""
    for token in token_list:
        if token.get("platforms", {}).get("ethereum", "").lower() == contract_address.lower():
            return True
    return False

# --- Asynchronous Functions ---

async def get_held_tokens_alchemy(wallet_address: str, session: aiohttp.ClientSession) -> List[str]:
    """Asynchronously fetch all ERC-20 token addresses with non-zero balances for a wallet using Alchemy's API."""
    if not validate_ethereum_address(wallet_address):
        logger.error(f"Invalid wallet address provided to Alchemy function.")
        return []
    headers = {"accept": "application/json", "content-type": "application/json"}
    payload = {
        "id": 1, "jsonrpc": "2.0", "method": "alchemy_getTokenBalances", "params": [w3.to_checksum_address(wallet_address), "erc20"]
    }
    try:
        async with session.post(WEB3_PROVIDER_URL, headers=headers, json=payload, timeout=20) as response:
            response.raise_for_status()
            data = await response.json()
            token_addresses = []
            if "result" in data and "tokenBalances" in data["result"]:
                for token_info in data["result"]["tokenBalances"]:
                    if token_info["tokenBalance"] != "0x0":
                        token_addresses.append(token_info["contractAddress"].lower())
            logger.info(f"Found {len(token_addresses)} tokens with non-zero balances.")
            return token_addresses
    except Exception as e:
        logger.error(f"Error getting held tokens from Alchemy: {e}")
        return []

async def fetch_token_prices(session: aiohttp.ClientSession, tokens: List[str]) -> Dict:
    """Asynchronously fetch prices for a list of tokens from CoinGecko Pro API, with rate limiting and retry logic."""
    if not tokens:
        return {}

    all_prices = {}
    headers = {"accept": "application/json", "x-cg-pro-api-key": COINGECKO_API_KEY}
    token_list = get_coingecko_token_list()
    valid_tokens = []
    unsupported_tokens = []

    # Filter for valid and supported tokens to avoid unnecessary API calls.
    for token in tokens:
        if token and isinstance(token, str) and validate_ethereum_address(token):
            if is_token_supported(token, token_list):
                valid_tokens.append(token)
            else:
                unsupported_tokens.append(token)
        else:
            logger.warning(f"Invalid token address skipped: {token}")

    logger.info(f"Valid tokens: {len(valid_tokens)}, Unsupported tokens: {len(unsupported_tokens)}")

    # Fetch prices in chunks to respect API limits.
    chunk_size = 20
    for i in range(0, len(valid_tokens), chunk_size):
        chunk = valid_tokens[i:i + chunk_size]
        contract_addresses_str = ','.join(chunk)
        url = f"https://pro-api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={contract_addresses_str}&vs_currencies=usd"

        logger.debug(f"Request URL: {url}")

        for attempt in range(3):
            try:
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status == 429:
                        logger.warning(f"Rate limited, waiting for {2 ** attempt} seconds...")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    response.raise_for_status()
                    data = await response.json()
                    logger.debug(f"API response data: {data}")

                    if not isinstance(data, dict):
                        logger.error("Unexpected API response format.")
                        continue

                    for contract, price_info in data.items():
                        if contract and isinstance(contract, str):
                            price = price_info.get("usd", 0.0)
                            if price > MAX_TOKEN_PRICE:
                                logger.error(f"Error: Token {contract} has invalid price of ${price:,.2f}, excluding from portfolio")
                                continue
                            all_prices[contract.lower()] = {
                                "price": price,
                                "change_24h": 0.0 # Note: The simple/token_price endpoint does not provide 24h change, so this is hardcoded to 0.0.
                            }
                        else:
                            logger.error(f"Invalid contract address in response: {contract}")
                    break
            except Exception as e:
                logger.error(f"Error fetching prices for chunk {chunk}: {e}, status: {response.status if 'response' in locals() else 'N/A'}")
                if attempt == 2:
                    for contract in chunk:
                        all_prices[contract.lower()] = {"price": 0.0, "change_24h": 0.0}

        await asyncio.sleep(0.5)

    # Handle tokens that were found but not supported by CoinGecko.
    for token in unsupported_tokens:
        all_prices[token.lower()] = {"price": 0.0, "change_24h": 0.0}
        logger.warning(f"Token {token} not supported by CoinGecko, setting price to $0.00")

    logger.info(f"Fetched prices for {len(all_prices)} tokens.")
    return all_prices

def load_or_create_token_database() -> Dict:
    """Load the token price cache from a file or create an empty dictionary if the file doesn't exist."""
    os.makedirs(DATABASE_FOLDER, exist_ok=True)
    try:
        tokens = joblib.load(TOKEN_DATABASE_CACHE)
        logger.info(f"Loaded {len(tokens)} tokens from database cache.")
        
        # Clean expired entries from the cache.
        cleaned_tokens = {}
        current_time = time.time()
        for addr, data in tokens.items():
            if isinstance(data, dict) and "price" in data and "timestamp" in data:
                if current_time - data["timestamp"] <= CACHE_EXPIRATION_TIME:
                    cleaned_tokens[addr] = data
        if len(cleaned_tokens) < len(tokens):
            logger.info(f"Cleaned {len(tokens) - len(cleaned_tokens)} expired entries from cache.")
            save_token_database(cleaned_tokens) # Save the cleaned cache.
        return cleaned_tokens
    except FileNotFoundError:
        logger.warning("Token database not found. Starting with an empty database.")
        return {}
    except Exception as e:
        logger.error(f"Error loading token database: {e}. Starting with an empty database.")
        return {}

def save_token_database(tokens: Dict):
    """Save the current token price dictionary to a file using joblib."""
    try:
        joblib.dump(tokens, TOKEN_DATABASE_CACHE)
        logger.info(f"Saved {len(tokens)} tokens to database cache.")
    except Exception as e:
        logger.error(f"Failed to save token database cache: {e}")

# --- Main Logic Function ---

async def get_portfolio_data(wallet_address: str) -> Dict:
    """Main function to get a full portfolio breakdown: ETH balance, token balances, and their values."""
    logger.info(f"Analyzing portfolio for {wallet_address}")

    # Load the local token price cache.
    token_database = load_or_create_token_database()

    # Get ETH balance and its price.
    eth_balance = get_eth_balance(wallet_address, w3)
    eth_price_data = get_eth_price_sync()

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
            new_prices = await fetch_token_prices(session, missing_tokens)
            for addr, price_data in new_prices.items():
                token_database[addr.lower()] = {
                    "price": price_data["price"],
                    "change_24h": price_data["change_24h"],
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
                asyncio.to_thread(get_token_info_and_balance, wallet_address, addr, w3)
                for addr in held_token_addresses
            ]

            token_infos = await asyncio.gather(*token_info_tasks)

            # Build the final portfolio data structure.
            for token_info in token_infos:
                if token_info["balance"] > 0:
                    addr_lower = token_info["address"].lower()
                    price_data = token_database.get(addr_lower, {"price": 0.0, "change_24h": 0.0, "timestamp": 0})

                    token_info.update({
                        "price": price_data["price"],
                        "change_24h": price_data["change_24h"],
                        "value": token_info["balance"] * price_data["price"]
                    })

                    portfolio["tokens"].append(token_info)
                    portfolio["total_value"] += token_info["value"]

    # Sort tokens by value in descending order.
    portfolio["tokens"].sort(key=lambda x: x["value"], reverse=True)

    logger.info(f"Portfolio analysis complete. Total value: ${portfolio['total_value']:,.2f}")
    return portfolio

# --- Main Execution Block ---
async def main():
    """Main function to run the portfolio tracker and print the results."""
    # Example wallet address to analyze.
    wallet_address = "0x0E6766293E15552Deed3Eaf8505f3640E29f4949"

    logger.info("Starting portfolio analysis...")
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid Ethereum address provided.")
        return

    # Call the main portfolio data function.
    portfolio = await get_portfolio_data(wallet_address)

    # Print the formatted portfolio summary.
    print("\n" + "="*50)
    print(f"Portfolio Summary for {portfolio['wallet_address']}")
    print("="*50)
    print(f"ETH Balance: {portfolio['eth_balance']:.4f} ETH")
    print(f"ETH Price: ${portfolio['eth_price']:,.2f} ({portfolio['eth_change_24h']:+.2f}%)")
    print(f"ETH Value: ${portfolio['eth_value']:,.2f}")
    print(f"Total Portfolio: ${portfolio['total_value']:,.2f}")
    print(f"Number of Tokens: {len(portfolio['tokens'])}")

    print(f"\nTop 10 Token Holdings:")
    print("-" * 80)
    print(f"{'Token':<20} {'Balance':<15} {'Price':<15} {'Value':<12} {'24h Change':<10}")
    print("-" * 80)

    for token in portfolio['tokens'][:10]:
        balance_str = f"{token['balance']:.4f}"
        price_str = f"${token['price']:,.8f}" if token['price'] > 0 and token['price'] < 0.01 else f"${token['price']:,.4f}" if token['price'] > 0 else "N/A"
        value_str = f"${token['value']:,.2f}"
        change_str = f"{token['change_24h']:+.2f}%" if token['change_24h'] != 0 else "N/A"

        print(f"{token['symbol']:<20} {balance_str:<15} {price_str:<15} {value_str:<12} {change_str:<10}")

if __name__ == "__main__":
    asyncio.run(main())