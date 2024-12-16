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

    const symbolsJsonPath = "/static/data/symbols.json";

    // Load securities data
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

    // Populate suggestions dropdown and sort alphabetically
    searchStockInput.addEventListener("input", () => {
        const query = searchStockInput.value.trim().toLowerCase();
        searchSuggestions.innerHTML = ""; // Clear previous suggestions

        if (query.length === 0) {
            searchSuggestions.classList.add("hidden");
            return;
        }

        const filteredSecurities = securitiesData
            .filter((sec) =>
                sec.symbol.toLowerCase().includes(query) ||
                sec.name.toLowerCase().includes(query)
            )
            .sort((a, b) => {
                const aStartsWith = a.symbol.toLowerCase().startsWith(query);
                const bStartsWith = b.symbol.toLowerCase().startsWith(query);

                if (aStartsWith && !bStartsWith) return -1; // Prioritize startsWith matches
                if (!aStartsWith && bStartsWith) return 1;

                return a.symbol.localeCompare(b.symbol); // Alphabetical order
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

    // Select a security and enable "Add" functionality
    function selectSecurity(security) {
        searchStockInput.value = `${security.symbol} - ${security.name}`;
        searchSuggestions.classList.add("hidden");

        addStockBtn.onclick = () => {
            const amount = parseFloat(amountInput.value.trim());
            if (!amount || amount <= 0) return alert("Please enter a valid amount.");

            addStockRow({
                ticker: security.symbol,
                name: security.name,
                exchange: security.exchange,
                assetType: security.assetType,
                amount: amount,
            });

            searchStockInput.value = "";
            amountInput.value = "";
        };
    }

    // Add stock to the manual portfolio table
    function addStockRow(stock) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${stock.ticker}</td>
            <td>${stock.name}</td>
            <td>${stock.exchange}</td>
            <td>${stock.assetType}</td>
            <td>${stock.amount}</td>
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
            searchStockInput.value = `${stock.ticker} - ${stock.name}`;
            amountInput.value = stock.amount;

            addStockBtn.onclick = () => {
                const newAmount = parseFloat(amountInput.value.trim());
                if (!newAmount || newAmount <= 0) return alert("Please enter a valid amount.");

                stock.amount = newAmount;
                row.children[4].textContent = newAmount;
                amountInput.value = "";
            };
        });
    }

    // Modal Controls
    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        newPortfolioModal.style.display = "block";
    });

    document.querySelector(".manual-portfolio-btn").addEventListener("click", () => {
        const manualPortfolioSection = document.getElementById("manualPortfolioSection");
        const uploadPortfolioSection = document.getElementById("uploadPortfolioSection");

        manualPortfolioSection.classList.remove("hidden");
        uploadPortfolioSection.classList.add("hidden");
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

    // Initial Load
    await loadSecurities();
});
