document.addEventListener("DOMContentLoaded", async () => {
    const portfolioList = document.getElementById("portfolio-list");
    const newPortfolioModal = document.getElementById("newPortfolioModal");
    const manualPortfolioTable = document.getElementById("manualPortfolioTable").querySelector("tbody");
    const searchStockInput = document.getElementById("searchStockInput");
    const amountInput = document.getElementById("amountInput");
    const addStockBtn = document.getElementById("addStockBtn");
    const searchSuggestions = document.createElement("ul");
    searchSuggestions.className = "search-suggestions hidden";
    searchStockInput.parentNode.appendChild(searchSuggestions);

    const manualPortfolio = [];
    let securitiesData = [];
    let apiKey = "";

    const symbolsJsonPath = "/static/data/symbols.json";

    // Fetch API key securely
    async function fetchApiKey() {
        try {
            const response = await fetch("/auth/get-api-key", {
                method: "GET",
                credentials: "include",
            });
            if (response.ok) {
                const data = await response.json();
                apiKey = data.apiKey;
                console.log("API key retrieved successfully:", apiKey);
            } else {
                console.error("Failed to fetch API key.");
            }
        } catch (error) {
            console.error("Error fetching API key:", error);
        }
    }

    // Load securities from JSON
    async function loadSecurities() {
        try {
            const response = await fetch(symbolsJsonPath);
            if (response.ok) {
                securitiesData = await response.json();
                console.log("Securities data loaded successfully.");
            } else {
                console.error("Failed to load securities data.");
            }
        } catch (error) {
            console.error("Error loading securities data:", error);
        }
    }

    // Populate suggestions dropdown based on user input
    searchStockInput.addEventListener("input", () => {
        const query = searchStockInput.value.trim().toLowerCase();
        searchSuggestions.innerHTML = "";

        if (query.length === 0) {
            searchSuggestions.classList.add("hidden");
            return;
        }

        const filteredSecurities = securitiesData
            .filter((security) =>
                security.symbol.toLowerCase().includes(query) ||
                security.name.toLowerCase().includes(query)
            )
            .sort((a, b) => {
                const aStartsWith = a.symbol.toLowerCase().startsWith(query);
                const bStartsWith = b.symbol.toLowerCase().startsWith(query);
                if (aStartsWith && !bStartsWith) return -1;
                if (!aStartsWith && bStartsWith) return 1;
                return a.symbol.localeCompare(b.symbol);
            });

        if (filteredSecurities.length === 0) {
            searchSuggestions.classList.add("hidden");
            return;
        }

        filteredSecurities.forEach((security) => {
            const li = document.createElement("li");
            li.textContent = `${security.symbol} - ${security.name}`;
            li.addEventListener("click", () => selectSecurity(security));
            searchSuggestions.appendChild(li);
        });

        searchSuggestions.classList.remove("hidden");
    });

    // Select a security and set the add functionality
    function selectSecurity(security) {
        searchStockInput.value = `${security.symbol} - ${security.name}`;
        searchSuggestions.classList.add("hidden");

        addStockBtn.onclick = async () => {
            const amount = parseFloat(amountInput.value.trim());
            if (!amount || amount <= 0) return alert("Please enter a valid amount.");

            const stockData = await fetchStockData(security.symbol);
            addStockRow({
                equityName: security.name,
                equityDetails: `${security.symbol}:${security.exchange}`,
                amount: amount,
                price: stockData.price,
                valueChange: stockData.valueChange,
                totalValue: (stockData.price * amount).toFixed(2),
            });

            searchStockInput.value = "";
            amountInput.value = "";
        };
    }

    // Fetch stock data from Alpha Vantage
    async function fetchStockData(symbol) {
        try {
            const response = await fetch(
                `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${apiKey}`
            );
            const data = await response.json();
            const quote = data["Global Quote"];
            return {
                price: parseFloat(quote["05. price"]) || 0,
                valueChange: parseFloat(quote["09. change"]) || 0,
            };
        } catch (error) {
            console.error("Error fetching stock data:", error);
            return { price: 0, valueChange: 0 };
        }
    }

    // Add stock to the manual portfolio table
    function addStockRow(stock) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>
                <strong style="color: red;">${stock.equityName}</strong><br>
                <span>${stock.equityDetails}</span>
            </td>
            <td>${stock.amount}</td>
            <td>${stock.valueChange}</td>
            <td>${stock.totalValue}</td>
            <td>
                <button class="edit-stock-btn">Edit</button>
                <button class="remove-stock-btn">Delete</button>
            </td>
        `;
        manualPortfolioTable.appendChild(row);
        manualPortfolio.push(stock);

        // Delete functionality
        row.querySelector(".remove-stock-btn").addEventListener("click", () => {
            const index = manualPortfolio.indexOf(stock);
            if (index !== -1) manualPortfolio.splice(index, 1);
            row.remove();
        });

        // Edit functionality
        row.querySelector(".edit-stock-btn").addEventListener("click", () => {
            searchStockInput.value = `${stock.equityName}`;
            amountInput.value = stock.amount;

            addStockBtn.onclick = () => {
                const newAmount = parseFloat(amountInput.value.trim());
                if (!newAmount || newAmount <= 0) return alert("Please enter a valid amount.");
                stock.amount = newAmount;
                stock.totalValue = (newAmount * stock.price).toFixed(2);
                row.children[1].textContent = newAmount;
                row.children[3].textContent = stock.totalValue;
                amountInput.value = "";
            };
        });
    }

    // Initialize modal functionality
    document.querySelector(".manual-portfolio-btn").addEventListener("click", () => {
        document.getElementById("manualPortfolioSection").classList.remove("hidden");
        document.getElementById("uploadPortfolioSection").classList.add("hidden");
    });

    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        newPortfolioModal.style.display = "block";
    });

    document.getElementById("closeModal").addEventListener("click", () => {
        newPortfolioModal.style.display = "none";
        resetModal();
    });

    function resetModal() {
        manualPortfolioTable.innerHTML = "";
        searchStockInput.value = "";
        amountInput.value = "";
        manualPortfolio.length = 0;
    }

    // Initial load
    await fetchApiKey();
    await loadSecurities();
});
