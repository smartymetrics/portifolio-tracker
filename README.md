# 🔍 Crypto Portfolio Tracker

A beautiful and intuitive web application for tracking Ethereum wallet portfolios using Streamlit.

## ✨ Features

- 📊 Real-time portfolio tracking
- 💰 ETH balance and value calculation
- 🪙 ERC-20 token detection and valuation
- 📈 Interactive portfolio composition charts
- 💹 24-hour price change indicators
- 🔄 Data caching for better performance
- 📱 Responsive design

## 🚀 Quick Start

### 1. Setup Project Structure
```
crypto-portfolio-tracker/
├── backend/
│   ├── portfolio_tracker.ipynb    # Learning notebook
│   ├── api_functions.py           # API helper functions
│   └── .env                       # Your API keys
├── frontend/
│   └── streamlit_app.py           # Main web app
├── requirements.txt               # Dependencies
├── .gitignore                     # Git ignore file
└── README.md                      # This file
```

### 2. Get API Keys
- **Etherscan API**: [Get free API key](https://etherscan.io/apis)
- **CoinGecko Pro API**: [Get free API key](https://www.coingecko.com/en/api)

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Create a `.env` file in the `backend` folder:
```
ETHERSCAN_API_KEY=your_etherscan_api_key_here
COINGECKO_API_KEY=your_coingecko_api_key_here
```

### 5. Run the Application
```bash
# Navigate to frontend folder
cd frontend

# Run Streamlit app
streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`

## 🎓 Learning Path

### Step 1: Understand the APIs
- Open `portfolio_tracker.ipynb` in Jupyter to learn how the APIs work
- Run each cell to see live data and understand the code

### Step 2: Explore the Functions
- Check out `api_functions.py` to see how data is processed
- Each function is well-documented and reusable

### Step 3: Customize the App
- Modify `streamlit_app.py` to add new features
- Add more charts, filters, or data analysis

## 📊 Sample Wallets for Testing

- **Ethereum Foundation**: `0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe`
- **Vitalik Buterin**: `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`
- **Sample Wallet**: `0x742d35Cc6634C0532925a3b8D6Ac0532eb0F400e`

## 🔧 How It Works

1. **Input Validation**: Checks if Ethereum address is valid format
2. **ETH Balance**: Uses Etherscan API to get ETH balance
3. **Token Detection**: Finds ERC-20 tokens from transaction history
4. **Price Data**: Gets real-time prices from CoinGecko
5. **Portfolio Calculation**: Combines all data to show total portfolio value
6. **Visualization**: Creates interactive charts and metrics

## 📈 Future Features

- [ ] Historical portfolio tracking
- [ ] Multiple wallet comparison
- [ ] DeFi position tracking (Uniswap LP, Aave lending)
- [ ] Transaction history analysis
- [ ] Portfolio export to CSV
- [ ] Mobile app version
- [ ] Alert system for price changes

## 🛠️ Tech Stack

- **Frontend**: Streamlit (Python web framework)
- **Data**: Pandas for data processing
- **Charts**: Plotly for interactive visualizations
- **APIs**: Etherscan & CoinGecko APIs
- **Learning**: Jupyter notebooks for experimentation

## 🤝 Contributing

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ⚠️ Important Notes

- Keep your `.env` file private (never commit API keys!)
- API keys have rate limits - be mindful of usage
- Some token prices may not be available on CoinGecko
- This is for educational purposes - verify important data independently

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

**Built with ❤️ for learning blockchain development and data analysis**