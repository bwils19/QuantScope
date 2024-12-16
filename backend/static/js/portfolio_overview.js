document.addEventListener("DOMContentLoaded", async () => {
    const portfolioList = document.getElementById("portfolio-list");
    const newPortfolioModal = document.getElementById("newPortfolioModal");
    const manualPortfolioTable = document.getElementById("manualPortfolioTable").querySelector("tbody");
    const searchStockInput = document.getElementById("searchStockInput");
    const searchSuggestions = document.createElement("ul");
    searchSuggestions.className = "search-suggestions hidden";
    searchStockInput.parentNode.appendChild(searchSuggestions);

    const manualPortfolio = [];
    let securitiesData = [];

    const symbolsJsonPath = "/static/data/symbols.json";

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

    // Populate suggestions based on user input
    searchStockInput.addEventListener("input", () => {
        const query = searchStockInput.value.trim().toLowerCase();
        searchSuggestions.innerHTML = ""; // Clear previous suggestions

        if (query.length === 0) {
            searchSuggestions.classList.add("hidden");
            return;
        }

        // Filter and sort securities alphabetically
        const filteredSecurities = securitiesData
            .filter((security) =>
                security.symbol.toLowerCase().includes(query) ||
                security.name.toLowerCase().includes(query)
            )
            .sort((a, b) => {
                const aName = a.name.toLowerCase();
                const bName = b.name.toLowerCase();
                const aSymbol = a.symbol.toLowerCase();
                const bSymbol = b.symbol.toLowerCase();

                // Sort by symbol first, then name
                if (aSymbol.startsWith(query) && !bSymbol.startsWith(query)) return -1;
                if (bSymbol.startsWith(query) && !aSymbol.startsWith(query)) return 1;
                if (aName.startsWith(query) && !bName.startsWith(query)) return -1;
                if (bName.startsWith(query) && !aName.startsWith(query)) return 1;

                // Fall back to alphabetical order
                return aName.localeCompare(bName);
            });

        if (filteredSecurities.length === 0) {
            searchSuggestions.classList.add("hidden");
            return;
        }

        // Populate the dropdown with sorted securities
        filteredSecurities.forEach((security) => {
            const li = document.createElement("li");
            li.textContent = `${security.symbol} - ${security.name}`;
            li.addEventListener("click", () => selectSecurity(security));
            searchSuggestions.appendChild(li);
        });

        searchSuggestions.classList.remove("hidden");
    });


    // Select a security and populate the row
    function selectSecurity(security) {
        searchStockInput.value = `${security.symbol} - ${security.name}`;
        searchSuggestions.classList.add("hidden");

        // Add the selected security to the table
        addStockRow({
            ticker: security.symbol,
            name: security.name,
            exchange: security.exchange,
            assetType: security.assetType,
        });
    }

    // Add selected stock to the table
    function addStockRow(stock) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${stock.ticker}</td>
            <td>${stock.name}</td>
            <td>${stock.exchange}</td>
            <td>${stock.assetType}</td>
            <td><input type="number" class="amount-owned" placeholder="Enter amount"></td>
            <td>-</td>
            <td>-</td>
            <td>
                <button class="remove-stock-btn">Delete</button>
            </td>
        `;
        manualPortfolioTable.appendChild(row);

        // Add delete functionality
        row.querySelector(".remove-stock-btn").addEventListener("click", () => {
            const index = manualPortfolio.findIndex((item) => item.ticker === stock.ticker);
            if (index !== -1) manualPortfolio.splice(index, 1);
            row.remove();
        });
    }

    // Fetch and display portfolios
    async function fetchPortfolios() {
        try {
            const response = await fetch("/auth/portfolio-overview", {
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include", // Include cookies
            });

            if (response.ok) {
                const portfolios = await response.json();
                displayPortfolios(portfolios);
            } else {
                portfolioList.innerHTML = "<p>Error loading portfolios.</p>";
            }
        } catch (error) {
            console.error("Error fetching portfolios:", error);
            portfolioList.innerHTML = "<p>Error loading portfolios.</p>";
        }
    }

    // Display portfolios in the portfolio list
    function displayPortfolios(portfolios) {
        portfolioList.innerHTML = ""; // Clear existing portfolios
        if (portfolios.length === 0) {
            portfolioList.innerHTML = "<p>Create a portfolio to get started.</p>";
        } else {
            portfolios.forEach((portfolio) => {
                const div = document.createElement("div");
                div.className = "portfolio-card";
                div.innerHTML = `
                    <h3>${portfolio.name}</h3>
                    <p>Created: ${portfolio.created_at}</p>
                    <button onclick="viewPortfolio(${portfolio.id})">View Portfolio</button>
                    <button onclick="deletePortfolio(${portfolio.id})">Delete</button>
                `;
                portfolioList.appendChild(div);
            });
        }
    }

    // Create a portfolio
    document.getElementById("finishManualPortfolioBtn").addEventListener("click", async () => {
        try {
            const portfolioName = prompt("Enter a name for your portfolio:");
            if (!portfolioName) return alert("Portfolio name is required.");

            const rows = document.querySelectorAll("#manualPortfolioTable tbody tr");
            const stocks = Array.from(rows).map(row => ({
                ticker: row.children[0].innerText,
                name: row.children[1].innerText,
                exchange: row.children[2].innerText,
                assetType: row.children[3].innerText,
                amount: parseFloat(row.querySelector(".amount-owned").value),
            }));

            const response = await fetch("/auth/create-portfolio", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ name: portfolioName, stocks }),
            });

            if (response.ok) {
                alert("Portfolio created successfully!");
                await fetchPortfolios();
                newPortfolioModal.style.display = "none";
                resetModal();
            } else {
                const error = await response.json();
                alert(`Error creating portfolio: ${error.message}`);
            }
        } catch (error) {
            console.error("Error creating portfolio:", error);
            alert("An unexpected error occurred.");
        }
    });

    // Handle "New Portfolio" button click
    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        if (!newPortfolioModal) {
            console.error("Modal with ID 'newPortfolioModal' not found.");
            return;
        }

        // Show the modal
        newPortfolioModal.style.display = "block";

        // Ensure manual section is visible
        const manualPortfolioSection = document.getElementById("manualPortfolioSection");
        const uploadPortfolioSection = document.getElementById("uploadPortfolioSection");

        manualPortfolioSection.classList.remove("hidden");
        uploadPortfolioSection.classList.add("hidden");
    });

    // Handle "Close" button click
    document.getElementById("closeModal").addEventListener("click", () => {
        if (!newPortfolioModal) {
            console.error("Modal with ID 'newPortfolioModal' not found.");
            return;
        }

        // Hide the modal
        newPortfolioModal.style.display = "none";

        // Reset modal state
        resetModal();
    });

    function resetModal() {
        manualPortfolioTable.innerHTML = "";
        searchStockInput.value = "";
        manualPortfolio.length = 0;
    }

    // Load securities and fetch portfolios on page load
    await loadSecurities();
    await fetchPortfolios();
});
