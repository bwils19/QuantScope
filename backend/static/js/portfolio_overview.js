// Declare manualPortfolio globally
const manualPortfolio = [];
let selectedSecurity = null;
const stockDataCache = {};

async function getApiKey() {
    try {
        const response = await fetch('/api/key'); // Call the backend route
        const data = await response.json();
        return data.apiKey;
    } catch (error) {
        console.error('Failed to fetch API key:', error);
        return null;
    }
}

async function fetchStockData(symbol) {
    // Check cache to see if we've hit the api for that security yet or not
    if (stockDataCache[symbol]) {
        console.log(`Cache hit for ${symbol}`); // Debugging
        return stockDataCache[symbol]; // Return cached data
    }

    const apiKey = await getApiKey();
    if (!apiKey) {
        alert('API key not available.');
        return null;
    }

    const url = `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${apiKey}`;
    try {
        const response = await fetch(url);
        const data = await response.json();
        console.log(data);

        if (data['Global Quote']) {
            const quote = data['Global Quote'];
            // Save the fetched data in the cache
            const stockInfo = {
                currentPrice: parseFloat(quote['05. price']),
                previousClose: parseFloat(quote['08. previous close']),
                changePercent: parseFloat(quote['10. change percent']),
            };

            stockDataCache[symbol] = stockInfo; // Store in cache
            return stockInfo; // Return the data
        } else {
            console.error('Invalid response:', data);
            return null;
        }
    } catch (error) {
        console.error(`Error fetching data for ${symbol}:`, error);
        return null;
    }
}

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

    const portfolioNameModal = document.getElementById("portfolioNameModal");
    const portfolioNameInput = document.getElementById("portfolioNameInput");
    const portfolioNameSaveBtn = document.getElementById("portfolioNameSaveBtn");
    const portfolioNameCancelBtn = document.getElementById("portfolioNameCancelBtn");
    const successModal = document.getElementById("successModal");
    const successMessage = document.getElementById("successMessage");
    const successOkBtn = document.getElementById("successOkBtn");
    const closeSuccessModal = document.getElementById("closeSuccessModal");

    const errorModal = document.getElementById("errorModal");
    const errorMessage = document.getElementById("errorMessage");
    const closeErrorModal = document.getElementById("closeErrorModal");
    // Close modals when clicking outside them
    window.addEventListener("click", (event) => {
        if (event.target === portfolioNameModal) {
            portfolioNameModal.style.display = "none";
        }
        if (event.target === successModal) {
            successModal.style.display = "none";
        }
        if (event.target === errorModal) {
            errorModal.style.display = "none";
        }
    });

    // Close success modal
    closeSuccessModal.addEventListener("click", () => {
        successModal.style.display = "none";
        location.reload();
    });

    // Close error modal
    closeErrorModal.addEventListener("click", () => {
        errorModal.style.display = "none";
    });

    // Open portfolio name modal
    document.getElementById("finishManualPortfolioBtn").addEventListener("click", () => {
        portfolioNameInput.value = ""; // Clear input
        portfolioNameModal.style.display = "block";
    });

    // Cancel portfolio creation
    portfolioNameCancelBtn.addEventListener("click", () => {
        portfolioNameModal.style.display = "none";
    });

    // Save portfolio name
    portfolioNameSaveBtn.addEventListener("click", async () => {
        const portfolioName = portfolioNameInput.value.trim();
         if (!portfolioName) {
            errorMessage.textContent = "Portfolio name is required!";
            errorModal.style.display = "block"; // Show error modal
            return;
        }

        const stocks = manualPortfolio.map(stock => ({
            ticker: stock.equityDetails.split(":")[0],
            name: stock.equityName,
            exchange: stock.equityDetails.split(":")[1],
            amount: stock.amount,
            valueChange: parseFloat(stock.valueChange),
            totalValue: parseFloat(stock.totalValue),
        }));

        if (stocks.length === 0) {
            errorMessage.textContent = "No securities added!";
            errorModal.style.display = "block";
            return;
        }

        try {
            const response = await fetch("/auth/create-portfolio", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: portfolioName, stocks }),
            });

           if (response.ok) {
                successMessage.textContent = "Portfolio created successfully!";
                successModal.style.display = "block";

                // Close modal and reload page after saving
                successModal.addEventListener("click", () => {
                    successModal.style.display = "none";
                    location.reload(); // Reload
                });
            } else {
                const error = await response.json();
                errorMessage.textContent = `Error: ${error.message}`;
                errorModal.style.display = "block";
            }
        } catch (error) {
            console.error("Error:", error);
            errorMessage.textContent = "An unexpected error occurred.";
            errorModal.style.display = "block";
        }
    });

    // Close success modal
    successOkBtn.addEventListener("click", () => {
        successModal.style.display = "none";
        location.reload(); // Reload the page
    });

    // Close modals when clicking outside
    window.addEventListener("click", (event) => {
        if (event.target === portfolioNameModal) {
            portfolioNameModal.style.display = "none";
        }
        if (event.target === successModal) {
            successModal.style.display = "none";
        }
    });

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
    async function addStock() {
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

            // Fetch stock data from API
        const stockData = await fetchStockData(selectedSecurity.symbol);
        console.log("Stock Data:", stockData);
        if (!stockData) {
            alert(`Could not fetch data for ${selectedSecurity.name}.`);
            return;
        }

        // Calculate values
        // const totalValue = amount * stockData.currentPrice;
        // const dailyChange = amount * (stockData.currentPrice - stockData.previousClose);

        console.log("Raw Values - Total:", amount * stockData.currentPrice);
        console.log("Raw Values - Change:", amount * (stockData.currentPrice - stockData.previousClose));


        let totalValue = amount * (stockData.currentPrice || 0);
        let dailyChange = amount * ((stockData.currentPrice || 0) - (stockData.previousClose || 0));

        console.log("Raw Total (Before Formatting):", totalValue);
        console.log("Raw Change (Before Formatting):", dailyChange);
        console.log("Type of Total Value:", typeof totalValue);
        console.log("Type of Daily Change:", typeof dailyChange);

        addStockRow({
            equityName: selectedSecurity.name,
            equityDetails: `${selectedSecurity.symbol}:${selectedSecurity.exchange}`,
            amount: amount,
            valueChange: dailyChange,
            totalValue: totalValue,
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
        const valueChangeClass = parseFloat(stock.valueChange) >= 0 ? 'positive' : 'negative';

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
            <td class="amount-cell">${stock.amount}</td> <!-- Added amount-cell class -->
            <td class="value-change ${valueChangeClass}">${parseFloat(stock.valueChange).toLocaleString('en-US', {
                style: 'currency', currency: 'USD'
            })}</td>
            <td class="total-value">${parseFloat(stock.totalValue).toLocaleString('en-US', {
                style: 'currency', currency: 'USD'
            })}</td>
        `;
        manualPortfolioTable.appendChild(row);
        manualPortfolio.push(stock);

        const chevron = row.querySelector(".chevron-icon");
        const dropdownMenu = row.querySelector(".dropdown-menu");

     // Toggle dropdown visibility
        chevron.addEventListener("click", (event) => {
            event.stopPropagation(); // Prevent immediate closing
            const rect = chevron.getBoundingClientRect();

            // Position dropdown relative to chevron
            dropdownMenu.style.top = `${rect.bottom + window.scrollY + 8}px`; // 8px gap below chevron
            dropdownMenu.style.left = `${rect.left + window.scrollX}px`;
            dropdownMenu.classList.toggle("hidden"); // Show/hide dropdown

            // Track mouse leave state
            let isMouseInside = true; // Flag to track if mouse is inside dropdown or chevron

            const hideDropdown = () => {
                if (!isMouseInside) { // Hide dropdown only if mouse is outside
                    dropdownMenu.classList.add("hidden");
                    removeListeners(); // Clean up event listeners
                }
            };

            const removeListeners = () => {
                dropdownMenu.removeEventListener("mouseleave", onMouseLeave);
                dropdownMenu.removeEventListener("mouseenter", onMouseEnter);
                chevron.removeEventListener("mouseleave", onMouseLeave);
                chevron.removeEventListener("mouseenter", onMouseEnter);
            };

            const onMouseEnter = () => isMouseInside = true; // Mouse is inside
            const onMouseLeave = () => {
                isMouseInside = false; // Mouse left
                setTimeout(hideDropdown, 200); // Delay hiding to allow movement
            };

            // Attach listeners to track mouse movement
            dropdownMenu.addEventListener("mouseenter", onMouseEnter);
            dropdownMenu.addEventListener("mouseleave", onMouseLeave);
            chevron.addEventListener("mouseenter", onMouseEnter);
            chevron.addEventListener("mouseleave", onMouseLeave);
        });


        // Remove stock
        row.querySelector(".remove-stock-btn").addEventListener("click", () => {
            const index = manualPortfolio.indexOf(stock);
            if (index !== -1) manualPortfolio.splice(index, 1);
            row.remove();
            if (manualPortfolio.length === 0) tableHeader.style.display = "none";
        });

        // edit the stock amount
        row.querySelector(".edit-stock-btn").addEventListener("click", async () => {
            const amountCell = row.querySelector(".amount-cell");
            const valueChangeCell = row.querySelector(".value-change");
            const totalValueCell = row.querySelector(".total-value");

            // Replace cell content with input and save button
            const input = document.createElement("input");
            input.type = "number";
            input.value = stock.amount;
            input.classList.add("edit-input");
            const saveButton = document.createElement("button");
            saveButton.textContent = "Save";
            saveButton.classList.add("save-btn");

            amountCell.innerHTML = "";
            amountCell.appendChild(input);
            amountCell.appendChild(saveButton);

            saveButton.addEventListener("click", async () => {
                const newAmount = parseFloat(input.value.trim());
                if (isNaN(newAmount) || newAmount <= 0) {
                    alert("Please enter a valid amount.");
                    return;
                }

                // Update stock data
                stock.amount = newAmount;

                // Recalculate total value and daily change
                const stockData = await fetchStockData(stock.equityDetails.split(":")[0]);
                const newTotalValue = (newAmount * stockData.currentPrice).toLocaleString('en-US', {
                    style: 'currency',
                    currency: 'USD',
                });

                const newDailyChange = (newAmount * (stockData.currentPrice - stockData.previousClose)).toLocaleString('en-US', {
                    style: 'currency',
                    currency: 'USD',
                });

                // Update UI
                amountCell.textContent = newAmount;
                valueChangeCell.textContent = newDailyChange;
                valueChangeCell.classList.remove("positive", "negative");
                valueChangeCell.classList.add(parseFloat(newDailyChange) >= 0 ? "positive" : "negative");
                totalValueCell.textContent = newTotalValue;

                // Remove save button
                saveButton.remove();
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

            // Finish and save portfolio
            document.getElementById("finishManualPortfolioBtn").addEventListener("click", async () => {
                try {
                    const portfolioName = document.getElementById("portfolioNameInput").value.trim(); // Get input value
                    if (!portfolioName) {
                        errorMessage.textContent = "Portfolio name is required.";
                        errorModal.style.display = "block";
                        return;
                    }

                    const stocks = manualPortfolio.map(stock => ({
                        ticker: stock.equityDetails.split(":")[0],
                        name: stock.equityName,
                        exchange: stock.equityDetails.split(":")[1],
                        amount: stock.amount,
                        valueChange: parseFloat(stock.valueChange),
                        totalValue: parseFloat(stock.totalValue),
                    }));

                    if (stocks.length === 0) {
                        errorMessage.textContent = "No securities added!";
                        errorModal.style.display = "block";
                        return;
                    }

                    const response = await fetch("/auth/create-portfolio", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({name: portfolioName, stocks}),
                    });

                    if (response.ok) {
                        successMessage.textContent = "Portfolio created successfully!";
                        successModal.style.display = "block";

                        // Reload page after closing modal
                        successModal.addEventListener("click", () => {
                            successModal.style.display = "none";
                            location.reload();
                        });
                    } else {
                        const error = await response.json();
                        errorMessage.textContent = `Error: ${error.message}`;
                        errorModal.style.display = "block";
                    }
                } catch (error) {
                    console.error("Error:", error);
                    errorMessage.textContent = "An unexpected error occurred.";
                    errorModal.style.display = "block";
                }
            });

        });
