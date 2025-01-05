// Declare manualPortfolio globally
const manualPortfolio = [];

document.addEventListener("DOMContentLoaded", async () => {
    const portfolioList = document.getElementById("portfolio-list");
    const newPortfolioModal = document.getElementById("newPortfolioModal");
    const manualPortfolioTable = document.getElementById("manualPortfolioTable").querySelector("tbody");
    const tableHeader = document.querySelector("#manualPortfolioTable thead");
    const searchStockInput = document.getElementById("searchStockInput");
    const amountInput = document.getElementById("amountInput");
    const addStockBtn = document.getElementById("addStockBtn");
    const searchSuggestions = document.createElement("ul");
    searchSuggestions.className = "search-suggestions hidden";
    searchStockInput.parentNode.appendChild(searchSuggestions);

    let securitiesData = [];
    const symbolsJsonPath = "/static/data/symbols.json";

    document.querySelector(".manual-portfolio-btn").addEventListener("click", () => {
        document.getElementById("manualPortfolioSection").classList.remove("hidden");
        document.getElementById("uploadPortfolioSection").classList.add("hidden");
    });


    // Hide table headers initially
    tableHeader.style.display = "none";

    // Load securities from JSON
    async function loadSecurities() {
        try {
            const response = await fetch(symbolsJsonPath);
            if (response.ok) {
                securitiesData = await response.json();
            } else {
                console.error("Failed to load securities data.");
            }
        } catch (error) {
            console.error("Error loading securities data:", error);
        }
    }

    // Populate suggestions dropdown based on user input
    let searchType = "ticker"; // Default search type
    document.querySelectorAll('input[name="searchType"]').forEach(radio => {
        radio.addEventListener("change", (e) => {
            searchType = e.target.value; // Update the search type
        });
    });

    searchStockInput.addEventListener("input", () => {
        const query = searchStockInput.value.trim().toLowerCase();
        searchSuggestions.innerHTML = "";

        if (query.length === 0) {
            searchSuggestions.classList.add("hidden");
            return;
        }

        const filteredSecurities = securitiesData
            .filter((security) => {
                if (searchType === "ticker") {
                    // Match tickers by prefix
                    return security.symbol.toLowerCase().startsWith(query);
                } else {
                    // Match names containing query
                    return security.name.toLowerCase().includes(query);
                }
            })
            .sort((a, b) => {
                const queryLower = query.toLowerCase();

                // 1. Exact match for tickers (highest priority)
                const aExact = a.symbol.toLowerCase() === queryLower;
                const bExact = b.symbol.toLowerCase() === queryLower;
                if (aExact && !bExact) return -1;
                if (!aExact && bExact) return 1;

                // 2. Prefix matches for names (second priority)
                const aStarts = a.name.toLowerCase().startsWith(queryLower);
                const bStarts = b.name.toLowerCase().startsWith(queryLower);
                if (aStarts && !bStarts) return -1;
                if (!aStarts && bStarts) return 1;

                // 3. Alphabetical order (fallback)
                return a.name.localeCompare(b.name);
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


    // Select a security
    function selectSecurity(security) {
        searchStockInput.value = `${security.symbol} - ${security.name}`;
        searchSuggestions.classList.add("hidden");

        // Shared function to add stock
        async function addStock() {
            const amount = parseFloat(amountInput.value.trim());
            if (!amount || amount <= 0) {
                alert("Please enter a valid amount.");
                return;
            }

            addStockRow({
                equityName: security.name,
                equityDetails: `${security.symbol}:${security.exchange}`,
                amount: amount,
                valueChange: "0",
                totalValue: "0.00",
            });

            searchStockInput.value = "";
            amountInput.value = "";
            tableHeader.style.display = "table-header-group";
        }

        addStockBtn.onclick = addStock;
        amountInput.addEventListener("keypress", (event) => {
            if (event.key === "Enter") addStock();
        });
    }

    // Add stock row to the table
    function addStockRow(stock) {
        const row = document.createElement("tr");
        row.innerHTML = `
                <td class="chevron-cell">
                <div class="chevron-wrapper">
                    <img src="/static/images/chevron-down.svg" alt="Chevron" class="chevron-icon" />
                    <div class="dropdown-menu hidden">
                        <button class="edit-stock-btn">Edit</button>
                        <button class="remove-stock-btn">Delete</button>
                    </div>
                </div>
            </td>
             <td style="text-align: left; width: 40%;">
                <strong style="color: red; font-size: 1.2em;">${stock.equityName}</strong><br>
                <span style="font-size: 0.8em; color: grey;">${stock.equityDetails}</span>
            </td>
            <td>${stock.amount}</td>
            <td>${stock.valueChange}</td>
            <td>${stock.totalValue}</td>
        `;
        manualPortfolioTable.appendChild(row);
        manualPortfolio.push(stock);

        // Remove stock
        row.querySelector(".remove-stock-btn").addEventListener("click", () => {
            const index = manualPortfolio.indexOf(stock);
            if (index !== -1) manualPortfolio.splice(index, 1);
            row.remove();
            if (manualPortfolio.length === 0) tableHeader.style.display = "none";
        });
    }

    // Reset modal
    function resetModal() {
        manualPortfolioTable.innerHTML = "";
        tableHeader.style.display = "none";
        searchStockInput.value = "";
        amountInput.value = "";
        manualPortfolio.length = 0;
    }

    // Initialize modal
    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        newPortfolioModal.style.display = "block";
    });

    document.getElementById("closeModal").addEventListener("click", () => {
        newPortfolioModal.style.display = "none";
        resetModal();
    });

    // Load securities
    await loadSecurities();
});

// Finish and save portfolio
document.getElementById("finishManualPortfolioBtn").addEventListener("click", async () => {
    try {
        const portfolioName = prompt("Enter a name for your portfolio:");
        if (!portfolioName) return alert("Portfolio name is required.");

        const stocks = manualPortfolio.map(stock => ({
            ticker: stock.equityDetails.split(":")[0],
            name: stock.equityName,
            exchange: stock.equityDetails.split(":")[1],
            amount: stock.amount,
            valueChange: parseFloat(stock.valueChange),
            totalValue: parseFloat(stock.totalValue),
        }));

        if (stocks.length === 0) return alert("No securities added!");

        const response = await fetch("/auth/create-portfolio", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: portfolioName, stocks }),
        });

        if (response.ok) {
            alert("Portfolio created successfully!");
            location.reload();
        } else {
            const error = await response.json();
            alert(`Error: ${error.message}`);
        }
    } catch (error) {
        console.error("Error:", error);
        alert("An unexpected error occurred.");
    }
});
