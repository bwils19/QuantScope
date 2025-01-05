// Declare manualPortfolio globally
const manualPortfolio = [];
let selectedSecurity = null;

document.addEventListener("DOMContentLoaded", async () => {
    const portfolioList = document.getElementById("portfolio-list");
    const newPortfolioModal = document.getElementById("newPortfolioModal");
    const manualPortfolioTable = document.getElementById("manualPortfolioTable").querySelector("tbody");
    const tableHeader = document.querySelector("#manualPortfolioTable thead");
    const searchStockInput = document.getElementById("searchStockInput");
    searchStockInput.addEventListener("blur", () => {
        setTimeout(() => searchSuggestions.classList.add("hidden"), 200); // Delay to allow clicks
    });
    const amountInput = document.getElementById("amountInput");
    amountInput.addEventListener("wheel", (event) => {
        event.preventDefault();
    });
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

    document.addEventListener("click", (event) => {
        if (
            !searchStockInput.contains(event.target) && // If not clicking inside the input box
            !searchSuggestions.contains(event.target) // If not clicking inside suggestions
        ) {
            searchSuggestions.classList.add("hidden");
        }
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

    let activeIndex = -1;

    searchStockInput.addEventListener("input", () => {
        const query = searchStockInput.value.trim().toLowerCase();
        searchSuggestions.innerHTML = "";
        activeIndex = -1;

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
        // populate suggested securities
        filteredSecurities.forEach((security, index) => {
            const li = document.createElement("li");
            li.textContent = `${security.symbol} - ${security.name}`;

            li.addEventListener("click", () => {
                selectSecurity(security);
            });

            // Highlight the first item initially
            if (index === 0) {
                li.classList.add("highlighted");
                activeIndex = 0; // Default to the first suggestion
            }

            searchSuggestions.appendChild(li);
        });

        searchSuggestions.classList.remove("hidden");
    });
    searchStockInput.addEventListener("keydown", (e) => {
        const items = searchSuggestions.querySelectorAll("li");
        if (items.length === 0) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            if (activeIndex < items.length - 1) {
                if (activeIndex >= 0) items[activeIndex].classList.remove("highlighted");
                activeIndex++;
                items[activeIndex].classList.add("highlighted");
            }
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            if (activeIndex > 0) {
                items[activeIndex].classList.remove("highlighted");
                activeIndex--;
                items[activeIndex].classList.add("highlighted");
            }
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (activeIndex >= 0) {
                items[activeIndex].click(); // Simulate a click event
            }
        }
    });


    function selectSecurity(security) {
        selectedSecurity = security; // Update the selected security
        searchStockInput.value = `${security.symbol} - ${security.name}`;
        searchSuggestions.classList.add("hidden");
    }

    // Add stock to the table
    function addStock() {
        // Ensure a security is selected
        if (!selectedSecurity) {
            alert("Please select a security first.");
            return;
        }

        const amount = parseFloat(amountInput.value.trim());
        if (!amount || amount <= 0) {
            alert("Please enter a valid amount.");
            return;
        }

        // Ensure the user can't add duplicate securities
        const isDuplicate = manualPortfolio.some(
            (stock) => stock.equityDetails === `${selectedSecurity.symbol}:${selectedSecurity.exchange}`
        );

        if (isDuplicate) {
            alert(`${selectedSecurity.name} (${selectedSecurity.symbol}) is already in your portfolio.`);
            return; // Stop further processing
        }

        addStockRow({
            equityName: selectedSecurity.name,
            equityDetails: `${selectedSecurity.symbol}:${selectedSecurity.exchange}`,
            amount: amount,
            valueChange: "0",
            totalValue: "0.00",
        });

        // Reset input fields and selected security
        searchStockInput.value = "";
        amountInput.value = "";
        selectedSecurity = null;
        tableHeader.style.display = "table-header-group";

        searchStockInput.focus();
    }

    addStockBtn.addEventListener("click", addStock);

    amountInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") addStock();
    });

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
            <td>
                <strong style="color: red; font-size: 1.2em;">${stock.equityName}</strong><br>
                <span style="font-size: 0.8em; color: grey;">${stock.equityDetails}</span>
            </td>
            <td>${stock.amount}</td>
            <td>${stock.valueChange}</td>
            <td>${stock.totalValue}</td>
        `;
        manualPortfolioTable.appendChild(row);
        manualPortfolio.push(stock);

        const chevron = row.querySelector(".chevron-icon");
        const dropdownMenu = row.querySelector(".dropdown-menu");

        chevron.addEventListener("click", (event) => {
            event.stopPropagation(); // Prevent closing due to body click event
            const rect = chevron.getBoundingClientRect();

            // Set dropdown position relative to chevron
            dropdownMenu.style.top = `${rect.bottom + window.scrollY + 8}px`; // Add 8px gap
            dropdownMenu.style.left = `${rect.left + window.scrollX}px`;
            dropdownMenu.classList.toggle("hidden"); // Toggle visibility

        // Remove stock
        row.querySelector(".remove-stock-btn").addEventListener("click", () => {
            const index = manualPortfolio.indexOf(stock);
            if (index !== -1) manualPortfolio.splice(index, 1);
            row.remove();
            if (manualPortfolio.length === 0) tableHeader.style.display = "none";
        });
            document.addEventListener("click", (event) => {
                if (!dropdownMenu.contains(event.target) && !chevron.contains(event.target)) {
                    dropdownMenu.classList.add("hidden");
                }
            });
        });
    }

    // Reset modal - THIS IS NOW RESTORED
    function resetModal() {
        manualPortfolioTable.innerHTML = "";
        tableHeader.style.display = "none";
        searchStockInput.value = "";
        amountInput.value = "";
        selectedSecurity = null; // Clear selected security
        manualPortfolio.length = 0; // Clear the portfolio array
    }

    // Initialize modal
    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        newPortfolioModal.style.display = "block";
        document.body.style.overflow = "hidden";
    });

    document.getElementById("closeModal").addEventListener("click", () => {
        newPortfolioModal.style.display = "none";
        document.body.style.overflow = "";
        resetModal(); // Reset modal when closed
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
