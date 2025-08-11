# --- Simplified Portfolio Tracker - Only 2 APIs ---
# Uses: Etherscan API + CoinGecko API (no Web3/RPC needed)

import os
from dotenv import load_dotenv
from typing import Dict, List, Optional
import time
import asyncio
import aiohttp
import joblib
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env file
load_dotenv()

def get_secret(key):
    """Universal secret getter for environment variables."""
    return os.getenv(key)

COINGECKO_API_KEY = get_secret("COINGECKO_API_KEY")
ETHERSCAN_API_KEY = get_secret("ETHERSCAN_API_KEY")

# Validation
if not ETHERSCAN_API_KEY:
    print("ERROR: Missing ETHERSCAN_API_KEY environment variable")
    print("Get one for free at: https://etherscan.io/apis")
    exit(1)

if not COINGECKO_API_KEY:
    print("⚠️ COINGECKO_API_KEY not found. Using basic pricing only.")
    logger.warning("No CoinGecko API key found, limited pricing available")

# Database Cache settings
DATABASE_FOLDER = 'database'
TOKEN_DATABASE_CACHE = os.path.join(DATABASE_FOLDER, 'token_price_database.joblib')
CACHE_EXPIRATION_TIME = 30 * 60  # 30 minutes
MAX_TOKEN_PRICE = 200000.0

def validate_ethereum_address(address: str) -> bool:
    """Basic Ethereum address validation."""
    if not address or not isinstance(address, str):
        return False
    
    # Basic format check: starts with 0x and is 42 characters long
    if len(address) == 42 and address.lower().startswith('0x'):
        try:
            # Check if it's valid hex
            int(address, 16)
            return True
        except ValueError:
            return False
    return False

def check_api_keys() -> Dict[str, bool]:
    """Check API keys without initializing connections that might cause recursion."""
    return {
        "web3": bool(WEB3_PROVIDER_URL),  # Just check if URL exists
        "coingecko": bool(COINGECKO_API_KEY),
        "etherscan": bool(ETHERSCAN_API_KEY)
    }

# --- Etherscan API Functions ---

async def get_eth_balance_etherscan(wallet_address: str, session: aiohttp.ClientSession) -> float:
    """Get ETH balance using Etherscan API."""
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid wallet address")
        return 0.0
    
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "balance",
        "address": wallet_address,
        "tag": "latest",
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        async with session.get(url, params=params, timeout=15) as response:
            response.raise_for_status()
            data = await response.json()
            
            if data.get("status") == "1" and "result" in data:
                balance_wei = int(data["result"])
                balance_eth = balance_wei / (10 ** 18)  # Convert Wei to ETH
                logger.info(f"ETH balance from Etherscan: {balance_eth:.4f} ETH")
                return balance_eth
            else:
                logger.error(f"Etherscan balance error: {data.get('message')}")
                return 0.0
                
    except Exception as e:
        logger.error(f"Error getting ETH balance from Etherscan: {e}")
        return 0.0

async def get_token_balance_etherscan(wallet_address: str, contract_address: str, session: aiohttp.ClientSession) -> int:
    """Get token balance using Etherscan API."""
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokenbalance",
        "contractaddress": contract_address,
        "address": wallet_address,
        "tag": "latest",
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        async with session.get(url, params=params, timeout=15) as response:
            response.raise_for_status()
            data = await response.json()
            
            if data.get("status") == "1" and "result" in data:
                return int(data["result"])
            else:
                logger.debug(f"No balance for {contract_address}: {data.get('message')}")
                return 0
                
    except Exception as e:
        logger.error(f"Error getting token balance from Etherscan: {e}")
        return 0

async def get_token_info_etherscan(contract_address: str, session: aiohttp.ClientSession) -> Dict:
    """Get token info using Etherscan API."""
    
    # Use a different approach - get token info from CoinGecko
    # since Etherscan doesn't have a direct token info endpoint
    
    # For now, return basic info and we'll enhance with known tokens
    known_tokens = {
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18},
        "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "name": "Tether USD", "decimals": 6},
        "0xa0b86a33e6dd835b44f4164b67c7dd14c4c7f5cf": {"symbol": "USDC", "name": "USD Coin", "decimals": 6},
        "0x6b175474e89094c44da98b954eedeac495271d0f": {"symbol": "DAI", "name": "Dai Stablecoin", "decimals": 18},
        "0x514910771af9ca656af840dff83e8264ecf986ca": {"symbol": "LINK", "name": "ChainLink Token", "decimals": 18},
        "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": {"symbol": "UNI", "name": "Uniswap", "decimals": 18},
        "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": {"symbol": "MATIC", "name": "Matic Token", "decimals": 18},
        "0xa0b73e1ff0b80914ab6fe0444e65848c4c34450b": {"symbol": "CRO", "name": "Crypto.com Coin", "decimals": 8},
    }
    
    contract_lower = contract_address.lower()
    if contract_lower in known_tokens:
        return known_tokens[contract_lower]
    
    # Default fallback
    return {"symbol": "UNKNOWN", "name": "Unknown Token", "decimals": 18}

async def get_held_tokens_etherscan(wallet_address: str, session: aiohttp.ClientSession) -> List[str]:
    """Get tokens with balances using Etherscan transaction history."""
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid wallet address")
        return []
    
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokentx",
        "address": wallet_address,
        "page": 1,
        "offset": 100000,  # Get last 100,000 transactions
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY
    }
    
    try:
        async with session.get(url, params=params, timeout=30) as response:
            response.raise_for_status()
            data = await response.json()
            
            token_addresses = set()
            
            if data.get("status") == "1" and "result" in data:
                for tx in data["result"]:
                    contract_address = tx.get("contractAddress", "").lower()
                    if contract_address and validate_ethereum_address(contract_address):
                        token_addresses.add(contract_address)
                        
            # Always include important tokens
            important_tokens = [
                "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
                "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
                "0xa0b86a33e6dd835b44f4164b67c7dd14c4c7f5cf",  # USDC
                "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
                "0x514910771af9ca656af840dff83e8264ecf986ca",  # LINK
                "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",  # UNI
                "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0",  # MATIC
                "0xa0b73e1ff0b80914ab6fe0444e65848c4c34450b",  # CRO
            ]
            
            for token in important_tokens:
                token_addresses.add(token.lower())
            
            logger.info(f"Etherscan found {len(token_addresses)} potential tokens to check")
            return list(token_addresses)
            
    except Exception as e:
        logger.error(f"Error getting token addresses from Etherscan: {e}")
        return []

async def get_eth_price_coingecko(session: aiohttp.ClientSession) -> Dict:
    """Get ETH price from CoinGecko."""
    if not COINGECKO_API_KEY:
        return {"price": 0.0, "change_24h": 0.0, "source": "no_api_key"}
    
    try:
        url = "https://pro-api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        headers = {"x-cg-pro-api-key": COINGECKO_API_KEY}
        
        async with session.get(url, params=params, headers=headers, timeout=15) as response:
            response.raise_for_status()
            data = await response.json()
            
            eth_data = data.get("ethereum", {})
            price = eth_data.get("usd", 0.0)
            change = eth_data.get("usd_24h_change", 0.0)
            
            logger.info(f"Got ETH price from CoinGecko: ${price:.2f}")
            return {"price": price, "change_24h": change, "source": "coingecko"}
            
    except Exception as e:
        logger.error(f"Error getting ETH price from CoinGecko: {e}")
        return {"price": 0.0, "change_24h": 0.0, "source": "failed"}

async def fetch_coingecko_prices(session: aiohttp.ClientSession, tokens: List[str]) -> Dict:
    """Fetch token prices from CoinGecko"""
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
        
        return cleaned_tokens
        
    except FileNotFoundError:
        logger.info("No cache found, starting fresh")
        return {}
    except Exception as e:
        logger.error(f"Cache error: {e}, starting fresh")
        return {}

async def get_portfolio_data(wallet_address: str, debug_mode: bool = False) -> Dict:
    """Main function to get portfolio data using only Etherscan + CoinGecko APIs."""
    logger.info(f"Analyzing portfolio for {wallet_address} using 2 APIs (Etherscan + CoinGecko)")

    token_database = load_or_create_token_database()

    async with aiohttp.ClientSession() as session:
        # Get ETH balance and price concurrently
        eth_balance_task = get_eth_balance_etherscan(wallet_address, session)
        eth_price_task = get_eth_price_coingecko(session)
        
        eth_balance, eth_price_data = await asyncio.gather(eth_balance_task, eth_price_task)

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

        # Get token addresses
        held_token_addresses = await get_held_tokens_etherscan(wallet_address, session)

        if debug_mode:
            portfolio["debug_info"].append(f"Found {len(held_token_addresses)} potential tokens")

        # Check which tokens need price updates
        missing_tokens = []
        for addr in held_token_addresses:
            addr_lower = addr.lower()
            if addr_lower not in token_database or (token_database[addr_lower].get("timestamp", 0) < time.time() - CACHE_EXPIRATION_TIME):
                missing_tokens.append(addr)

        # Fetch missing prices
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

        # Check balances for all tokens
        tokens_with_balance = []
        
        logger.info(f"Checking balances for {len(held_token_addresses)} tokens...")
        
        # Create tasks for concurrent balance checking
        balance_tasks = []
        for addr in held_token_addresses:
            balance_task = get_token_balance_etherscan(wallet_address, addr, session)
            info_task = get_token_info_etherscan(addr, session)
            balance_tasks.append((addr, balance_task, info_task))
        
        # Execute balance checks concurrently (in smaller batches to avoid rate limiting)
        batch_size = 10
        for i in range(0, len(balance_tasks), batch_size):
            batch = balance_tasks[i:i + batch_size]
            
            # Execute batch
            batch_results = []
            for addr, balance_task, info_task in batch:
                balance_wei, token_info = await asyncio.gather(balance_task, info_task)
                batch_results.append((addr, balance_wei, token_info))
            
            # Process batch results
            for addr, balance_wei, token_info in batch_results:
                if balance_wei > 0:
                    # Convert balance using decimals
                    decimals = token_info.get("decimals", 18)
                    balance = balance_wei / (10 ** decimals)
                    
                    addr_lower = addr.lower()
                    price_data = token_database.get(addr_lower, {"price": 0.0, "change_24h": None, "source": "none"})
                    
                    # Special handling for WETH
                    if token_info["symbol"].upper() == "WETH" and price_data["price"] == 0.0:
                        price_data = {
                            "price": eth_price_data["price"],
                            "change_24h": eth_price_data["change_24h"],
                            "source": "eth_price_mirror"
                        }
                    
                    token_data = {
                        "address": addr_lower,
                        "symbol": token_info["symbol"],
                        "name": token_info["name"],
                        "balance": balance,
                        "decimals": decimals,
                        "price": price_data["price"],
                        "change_24h": price_data["change_24h"],
                        "price_source": price_data["source"],
                        "value": balance * price_data["price"]
                    }
                    
                    tokens_with_balance.append(token_data)
                    portfolio["total_value"] += token_data["value"]
                    
                    if debug_mode:
                        portfolio["debug_info"].append(f"✅ {token_info['symbol']}: {balance:.8f} = ${token_data['value']:.2f}")
            
            # Rate limiting between batches
            if i + batch_size < len(balance_tasks):
                await asyncio.sleep(1)

        # Sort by value and add to portfolio
        tokens_with_balance.sort(key=lambda x: x["value"], reverse=True)
        portfolio["tokens"] = tokens_with_balance

    logger.info(f"Portfolio analysis complete. Total value: ${portfolio['total_value']:,.2f}")
    return portfolio

# --- Main Execution ---
async def main():
    """Main execution function."""
    wallet_address = "0x226cc0Bae5251EBb637B9ecF5B1CdB99764abBCD"

    logger.info("Starting 2-API portfolio analysis (Etherscan + CoinGecko)...")
    if not validate_ethereum_address(wallet_address):
        logger.error("Invalid Ethereum address")
        return

    # Get portfolio data
    portfolio = await get_portfolio_data(wallet_address, debug_mode=True)
    
    # Print results
    print("\n" + "="*80)
    print(f"📊 SIMPLIFIED PORTFOLIO TRACKER (2 APIs ONLY)")
    print("="*80)
    print(f"🔗 APIs Used: Etherscan + CoinGecko (No Web3/RPC needed)")
    print(f"📍 Wallet: {portfolio['wallet_address']}")
    print(f"💰 ETH Balance: {portfolio['eth_balance']:.4f} ETH")
    print(f"💲 ETH Price: ${portfolio['eth_price']:,.2f} ({portfolio['eth_change_24h']:+.2f}%)")
    print(f"💵 ETH Value: ${portfolio['eth_value']:,.2f}")
    print(f"🎯 Total Portfolio: ${portfolio['total_value']:,.2f}")
    print(f"🪙 Tokens Found: {len(portfolio['tokens'])}")

    # Show debug info
    if portfolio.get("debug_info"):
        print(f"\n🔍 DEBUG INFO:")
        for info in portfolio["debug_info"][:10]:  # Show first 10
            print(f"  • {info}")

    if portfolio['tokens']:
        print(f"\n🏆 TOKEN HOLDINGS:")
        print("-" * 100)
        print(f"{'Token':<15} {'Balance':<18} {'Price':<15} {'Value':<12} {'24h Change':<12} {'Source':<10}")
        print("-" * 100)

        for token in portfolio['tokens']:
            balance_str = f"{token['balance']:.8f}"
            price_str = f"${token['price']:.6f}" if token['price'] < 0.01 else f"${token['price']:,.4f}"
            value_str = f"${token['value']:,.2f}"
            
            change_24h = token.get('change_24h')
            if change_24h is not None and change_24h != 0:
                change_str = f"{change_24h:+.2f}%"
            else:
                change_str = "N/A"
            
            source_str = token.get('price_source', 'none')[:10]

            # Highlight WETH
            symbol_display = token['symbol']
            if token['symbol'].upper() == "WETH":
                symbol_display = f"🔥 {token['symbol']}"

            print(f"{symbol_display:<15} {balance_str:<18} {price_str:<15} {value_str:<12} {change_str:<12} {source_str:<10}")

    print("\n" + "="*80)
    print("✅ Analysis complete! Now using only 2 APIs.")
    print("🚀 No Web3/RPC connection needed - much simpler!")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())