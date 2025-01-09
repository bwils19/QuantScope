// Global state
const manualPortfolio = [];
let selectedSecurity = null;
const stockDataCache = {};
let securitiesData = [];
let searchType = "ticker"; // Default search type
let activeIndex = -1;
let currentPortfolioId = null;

// Cache DOM elements
const elements = {
    portfolioList: document.getElementById("portfolio-list"),
    newPortfolioModal: document.getElementById("newPortfolioModal"),
    manualPortfolioTable: document.getElementById("manualPortfolioTable").querySelector("tbody"),
    tableHeader: document.querySelector("#manualPortfolioTable thead"),
    searchStockInput: document.getElementById("searchStockInput"),
    amountInput: document.getElementById("amountInput"),
    addStockBtn: document.getElementById("addStockBtn"),
    portfolioNameModal: document.getElementById("portfolioNameModal"),
    portfolioNameInput: document.getElementById("portfolioNameInput"),
    portfolioNameSaveBtn: document.getElementById("portfolioNameSaveBtn"),
    portfolioNameCancelBtn: document.getElementById("portfolioNameCancelBtn"),
    successModal: document.getElementById("successModal"),
    successMessage: document.getElementById("successMessage"),
    successOkBtn: document.getElementById("successOkBtn"),
    errorModal: document.getElementById("errorModal"),
    errorMessage: document.getElementById("errorMessage"),
    deleteConfirmModal: document.getElementById("deleteConfirmModal"),
    portfolioDetailsModal: document.getElementById("portfolioDetailsModal"),
    confirmDeleteBtn: document.getElementById("confirmDeleteBtn"),
    cancelDeleteBtn: document.getElementById("cancelDeleteBtn"),
    securitiesTableBody: document.getElementById("securitiesTableBody"),
};

// Create and append search suggestions element
const searchSuggestions = document.createElement("ul");
searchSuggestions.className = "search-suggestions hidden";
elements.searchStockInput.parentNode.appendChild(searchSuggestions);

// API functions
async function getApiKey() {
    try {
        const response = await fetch('/api/key');
        const data = await response.json();
        return data.apiKey;
    } catch (error) {
        console.error('Failed to fetch API key:', error);
        return null;
    }
}

async function fetchStockData(symbol) {
    if (stockDataCache[symbol]) {
        console.log(`Cache hit for ${symbol}`);
        return stockDataCache[symbol];
    }

    const apiKey = await getApiKey();
    if (!apiKey) {
        alert('API key not available.');
        return null;
    }

    try {
        const response = await fetch(
            `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${apiKey}`
        );
        const data = await response.json();
        console.log(data);

        if (data['Global Quote']) {
            const quote = data['Global Quote'];
            const stockInfo = {
                currentPrice: parseFloat(quote['05. price']),
                previousClose: parseFloat(quote['08. previous close']),
                changePercent: parseFloat(quote['10. change percent'])
            };
            stockDataCache[symbol] = stockInfo;
            return stockInfo;
        }
        console.error('Invalid response:', data);
        return null;
    } catch (error) {
        console.error(`Error fetching data for ${symbol}:`, error);
        return null;
    }
}

function setupPortfolioActions() {
    // Setup delete buttons
    document.querySelectorAll('.delete-portfolio-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            currentPortfolioId = e.target.dataset.id;
            elements.deleteConfirmModal.style.display = "block";
        });
    });

    // Setup view buttons
    document.querySelectorAll('.view-portfolio-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const portfolioId = e.target.dataset.id;
            loadPortfolioDetails(portfolioId);
        });
    });

    // Delete confirmation handlers
    elements.confirmDeleteBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`/auth/portfolio/${currentPortfolioId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include'
            });

            if (response.ok) {
                elements.deleteConfirmModal.style.display = "none";
                // Remove the portfolio card from the UI
                const portfolioCard = document.querySelector(`[data-id="${currentPortfolioId}"]`).closest('.portfolio-item');
                portfolioCard.remove();

                // Show success message
                elements.successMessage.textContent = "Portfolio deleted successfully";
                elements.successModal.style.display = "block";
            } else {
                throw new Error('Failed to delete portfolio');
            }
        } catch (error) {
            console.error('Error deleting portfolio:', error);
            elements.errorMessage.textContent = "Failed to delete portfolio";
            elements.errorModal.style.display = "block";
        }
    });

    elements.cancelDeleteBtn.addEventListener('click', () => {
        elements.deleteConfirmModal.style.display = "none";
    });

    // Close modals when clicking outside
    window.addEventListener('click', (event) => {
        if (event.target === elements.deleteConfirmModal) {
            elements.deleteConfirmModal.style.display = "none";
        }
        if (event.target === elements.portfolioDetailsModal) {
            elements.portfolioDetailsModal.style.display = "none";
        }
    });
}

async function loadPortfolioDetails(portfolioId) {
    try {
        const response = await fetch(`/auth/portfolio/${portfolioId}/securities`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load portfolio details');
        }

        const data = await response.json();
        elements.securitiesTableBody.innerHTML = '';

        data.securities.forEach(security => {
            const row = document.createElement('tr');

            // Format percentages with null checks
            const valueChangePct = security.value_change_pct != null
                ? `(${security.value_change_pct.toFixed(2)}%)`
                : '(0.00%)';

            const unrealizedGainPct = security.unrealized_gain_pct != null
                ? `(${security.unrealized_gain_pct.toFixed(2)}%)`
                : '(0.00%)';

            row.innerHTML = `
                <td>${security.name} (${security.ticker})</td>
                <td>${security.amount_owned}</td>
                <td>${formatCurrency(security.current_price || 0)}</td>
                <td>${formatCurrency(security.total_value || 0)}</td>
                <td class="${(security.value_change || 0) >= 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(security.value_change || 0)}
                    ${valueChangePct}
                </td>
                <td class="${(security.unrealized_gain || 0) >= 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(security.unrealized_gain || 0)}
                    ${unrealizedGainPct}
                </td>
            `;
            elements.securitiesTableBody.appendChild(row);
        });

        elements.portfolioDetailsModal.style.display = "block";
    } catch (error) {
        console.error('Error loading portfolio details:', error);
        elements.errorMessage.textContent = "Failed to load portfolio details";
        elements.errorModal.style.display = "block";
    }
}

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

// Stock handling functions
function selectSecurity(security) {
    selectedSecurity = security;
    elements.searchStockInput.value = `${security.symbol} - ${security.name}`;
    searchSuggestions.classList.add("hidden");
}

function handleSearchInput() {
    const query = elements.searchStockInput.value.trim().toLowerCase();
    searchSuggestions.innerHTML = "";
    activeIndex = -1;

    if (query.length === 0) {
        searchSuggestions.classList.add("hidden");
        return;
    }

    const filteredSecurities = securitiesData
        .filter((security) => {
            if (searchType === "ticker") {
                return security.symbol.toLowerCase().startsWith(query);
            } else {
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

    // Populate suggestions
    filteredSecurities.forEach((security, index) => {
        const li = document.createElement("li");
        li.textContent = `${security.symbol} - ${security.name}`;

        li.addEventListener("click", () => {
            selectSecurity(security);
        });

        if (index === 0) {
            li.classList.add("highlighted");
            activeIndex = 0;
        }

        searchSuggestions.appendChild(li);
    });

    searchSuggestions.classList.remove("hidden");
}

function handleSearchKeydown(e) {
    const items = searchSuggestions.querySelectorAll("li");
    if (items.length === 0) return;

    switch (e.key) {
        case "ArrowDown":
            e.preventDefault();
            if (activeIndex < items.length - 1) {
                if (activeIndex >= 0) items[activeIndex].classList.remove("highlighted");
                activeIndex++;
                items[activeIndex].classList.add("highlighted");
            }
            break;
        case "ArrowUp":
            e.preventDefault();
            if (activeIndex > 0) {
                items[activeIndex].classList.remove("highlighted");
                activeIndex--;
                items[activeIndex].classList.add("highlighted");
            }
            break;
        case "Enter":
            e.preventDefault();
            if (activeIndex >= 0) {
                items[activeIndex].click();
            }
            break;
    }
}

async function addStock() {
    if (!selectedSecurity) {
        alert("Please select a security first.");
        return;
    }

    const amount = parseFloat(elements.amountInput.value.trim());
    if (!amount || amount <= 0) {
        alert("Please enter a valid amount.");
        return;
    }

    const isDuplicate = manualPortfolio.some(
        (stock) => stock.equityDetails === `${selectedSecurity.symbol}:${selectedSecurity.exchange}`
    );

    if (isDuplicate) {
        alert(`${selectedSecurity.name} (${selectedSecurity.symbol}) is already in your portfolio.`);
        return;
    }

    const stockData = await fetchStockData(selectedSecurity.symbol);
    if (!stockData) {
        alert(`Could not fetch data for ${selectedSecurity.name}.`);
        return;
    }

    let totalValue = amount * (stockData.currentPrice || 0);
    let dailyChange = amount * ((stockData.currentPrice || 0) - (stockData.previousClose || 0));

    addStockRow({
        equityName: selectedSecurity.name,
        equityDetails: `${selectedSecurity.symbol}:${selectedSecurity.exchange}`,
        amount: amount,
        valueChange: dailyChange,
        totalValue: totalValue,
    });

    elements.searchStockInput.value = "";
    elements.amountInput.value = "";
    selectedSecurity = null;
    elements.tableHeader.style.display = "table-header-group";
    elements.searchStockInput.focus();
}

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
        <td class="amount-cell">${stock.amount}</td>
        <td class="value-change ${valueChangeClass}">${parseFloat(stock.valueChange).toLocaleString('en-US', {
            style: 'currency', currency: 'USD'
        })}</td>
        <td class="total-value">${parseFloat(stock.totalValue).toLocaleString('en-US', {
            style: 'currency', currency: 'USD'
        })}</td>
    `;

    elements.manualPortfolioTable.appendChild(row);
    manualPortfolio.push(stock);

    setupRowControls(row, stock);
}

function setupRowControls(row, stock) {
    const chevron = row.querySelector(".chevron-icon");
    const dropdownMenu = row.querySelector(".dropdown-menu");
    let isMouseInside = true;

    function hideDropdown() {
        if (!isMouseInside) {
            dropdownMenu.classList.add("hidden");
            removeListeners();
        }
    }

    function removeListeners() {
        dropdownMenu.removeEventListener("mouseleave", onMouseLeave);
        dropdownMenu.removeEventListener("mouseenter", onMouseEnter);
        chevron.removeEventListener("mouseleave", onMouseLeave);
        chevron.removeEventListener("mouseenter", onMouseEnter);
    }

    const onMouseEnter = () => isMouseInside = true;
    const onMouseLeave = () => {
        isMouseInside = false;
        setTimeout(hideDropdown, 200);
    };

    chevron.addEventListener("click", (event) => {
        event.stopPropagation();
        const rect = chevron.getBoundingClientRect();
        dropdownMenu.style.top = `${rect.bottom + window.scrollY + 8}px`;
        dropdownMenu.style.left = `${rect.left + window.scrollX}px`;
        dropdownMenu.classList.toggle("hidden");

        dropdownMenu.addEventListener("mouseenter", onMouseEnter);
        dropdownMenu.addEventListener("mouseleave", onMouseLeave);
        chevron.addEventListener("mouseenter", onMouseEnter);
        chevron.addEventListener("mouseleave", onMouseLeave);
    });

    setupRowButtons(row, stock);
}

function setupRowButtons(row, stock) {
    // Remove stock button
    row.querySelector(".remove-stock-btn").addEventListener("click", () => {
        const index = manualPortfolio.indexOf(stock);
        if (index !== -1) manualPortfolio.splice(index, 1);
        row.remove();
        if (manualPortfolio.length === 0) elements.tableHeader.style.display = "none";
    });

    // Edit stock button
    row.querySelector(".edit-stock-btn").addEventListener("click", async () => {
        const amountCell = row.querySelector(".amount-cell");
        const valueChangeCell = row.querySelector(".value-change");
        const totalValueCell = row.querySelector(".total-value");

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

            stock.amount = newAmount;
            const stockData = await fetchStockData(stock.equityDetails.split(":")[0]);

            const newTotalValue = (newAmount * stockData.currentPrice).toLocaleString('en-US', {
                style: 'currency',
                currency: 'USD'
            });

            const newDailyChange = (newAmount * (stockData.currentPrice - stockData.previousClose))
                .toLocaleString('en-US', {
                    style: 'currency',
                    currency: 'USD'
                });

            amountCell.textContent = newAmount;
            valueChangeCell.textContent = newDailyChange;
            valueChangeCell.classList.remove("positive", "negative");
            valueChangeCell.classList.add(parseFloat(newDailyChange) >= 0 ? "positive" : "negative");
            totalValueCell.textContent = newTotalValue;
        });
    });
}

// Portfolio creation and modal handling
async function createPortfolio(portfolioName) {
    if (!portfolioName.trim()) {
        throw new Error("Portfolio name is required!");
    }

    if (manualPortfolio.length === 0) {
        throw new Error("No securities added!");
    }

    const stocks = manualPortfolio.map(stock => ({
        ticker: stock.equityDetails.split(":")[0],
        name: stock.equityName,
        exchange: stock.equityDetails.split(":")[1],
        amount: stock.amount,
        valueChange: parseFloat(stock.valueChange),
        totalValue: parseFloat(stock.totalValue)
    }));

    // Get CSRF token from cookie
    const csrfToken = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrf_access_token='))
        ?.split('=')[1];

    const response = await fetch("/auth/create-portfolio", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-TOKEN": csrfToken
        },
        body: JSON.stringify({name: portfolioName, stocks}),
        credentials: 'include'  // Include cookies in the request
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || 'Failed to create portfolio');
    }

    const data = await response.json();
    return data.message;
}

function resetModal() {
    elements.manualPortfolioTable.innerHTML = "";
    elements.tableHeader.style.display = "none";
    elements.searchStockInput.value = "";
    elements.amountInput.value = "";
    selectedSecurity = null;
    manualPortfolio.length = 0;
}

function setupEventListeners() {
    // Search input handlers
    elements.searchStockInput.addEventListener("input", handleSearchInput);
    elements.searchStockInput.addEventListener("keydown", handleSearchKeydown);
    elements.searchStockInput.addEventListener("blur", () => {
        setTimeout(() => searchSuggestions.classList.add("hidden"), 200);
    });
    setupPortfolioActions();

    // Search type radio buttons
    document.querySelectorAll('input[name="searchType"]').forEach(radio => {
        radio.addEventListener("change", (e) => {
            searchType = e.target.value;
        });
    });

    // Add stock handlers
    elements.addStockBtn.addEventListener("click", addStock);
    elements.amountInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") addStock();
    });
    elements.amountInput.addEventListener("wheel", (event) => {
        event.preventDefault();
    });

    // Modal handlers
    document.querySelector(".manual-portfolio-btn").addEventListener("click", () => {
        document.getElementById("manualPortfolioSection").classList.remove("hidden");
        document.getElementById("uploadPortfolioSection").classList.add("hidden");
    });

    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        elements.newPortfolioModal.style.display = "block";
        document.body.style.overflow = "hidden";
    });

    document.getElementById("closeModal").addEventListener("click", () => {
        elements.newPortfolioModal.style.display = "none";
        document.body.style.overflow = "";
        resetModal();
    });

    // Portfolio creation handlers
    document.getElementById("finishManualPortfolioBtn").addEventListener("click", () => {
        elements.portfolioNameInput.value = "";
        elements.portfolioNameModal.style.display = "block";
    });

    elements.portfolioNameSaveBtn.addEventListener("click", async () => {
        try {
            const portfolioData = {
                name: elements.portfolioNameInput.value,
                stocks: manualPortfolio
            };
            console.log("Attempting to save portfolio:", portfolioData);

            const result = await createPortfolio(elements.portfolioNameInput.value);
            console.log("Create portfolio result:", result);  // Debug log

            elements.successMessage.textContent = result;
            elements.successModal.style.display = "block";
            elements.portfolioNameModal.style.display = "none";

        } catch (error) {
            console.error("Error creating portfolio:", error);
            if (error.message.includes('<!DOCTYPE')) {
                // If we got HTML back, it's likely an authentication issue
                elements.errorMessage.textContent = "Session expired. Please log in again.";
                setTimeout(() => {
                    window.location.href = '/auth/login';
                }, 2000);
            } else {
                elements.errorMessage.textContent = error.message;
            }
            elements.errorModal.style.display = "block";
        }
    });

    elements.portfolioNameCancelBtn.addEventListener("click", () => {
        elements.portfolioNameModal.style.display = "none";
    });

    // Success/Error modal handlers
    elements.successOkBtn.addEventListener("click", () => {
        elements.successModal.style.display = "none";
        location.reload();
    });

    // Click outside modal handlers
    window.addEventListener("click", (event) => {
        if (event.target === elements.portfolioNameModal) {
            elements.portfolioNameModal.style.display = "none";
        }
        if (event.target === elements.successModal) {
            elements.successModal.style.display = "none";
            location.reload();
        }
        if (event.target === elements.errorModal) {
            elements.errorModal.style.display = "none";
        }
    });

    // Click outside suggestions handler
    document.addEventListener("click", (event) => {
        if (!elements.searchStockInput.contains(event.target) &&
            !searchSuggestions.contains(event.target)) {
            searchSuggestions.classList.add("hidden");
        }
    });
    const fileInput = document.getElementById('fileInput');
    const newFileBtn = document.querySelector('.new-file-btn');

    if (newFileBtn && fileInput) {
        newFileBtn.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', async (event) => {
            const file = event.target.files[0];
            if (!file) return;

            console.log('Attempting to upload file:', file.name);

            // Get CSRF token from cookie
            const csrfToken = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrf_access_token='))
                ?.split('=')[1];

            const formData = new FormData();
            formData.append('file', file);

            try {
                console.log('Sending upload request...');
                const response = await fetch('/auth/upload', {
                    method: 'POST',
                    headers: {
                        'X-CSRF-TOKEN': csrfToken
                    },
                    body: formData,
                    credentials: 'include'
                });

                // Check if response is JSON
                const contentType = response.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    const responseData = await response.json();
                    console.log('Upload response:', responseData);

                    if (response.ok) {
                        elements.successMessage.textContent = responseData.message || "File uploaded successfully!";
                        elements.successModal.style.display = "block";
                        setTimeout(() => {
                            location.reload();
                        }, 1500);
                    } else {
                        throw new Error(responseData.message || 'Upload failed');
                    }
                } else {
                    // If not JSON, might be redirected to login
                    console.log('Non-JSON response received');
                    if (response.status === 401 || response.status === 403) {
                        elements.errorMessage.textContent = "Session expired. Please log in again.";
                        elements.errorModal.style.display = "block";
                        setTimeout(() => {
                            window.location.href = '/auth/login';
                        }, 1500);
                    } else {
                        throw new Error('Unexpected response type');
                    }
                }
            } catch (error) {
                console.error('Error uploading file:', error);
                elements.errorMessage.textContent = "Failed to upload file. Please try logging in again.";
                elements.errorModal.style.display = "block";
            }
        });
    }
}

// Initialize
async function init() {
    try {
        // Load securities data
        const response = await fetch("/static/data/symbols.json");
        if (!response.ok) throw new Error("Failed to load securities data");
        securitiesData = await response.json();

        // Setup all event handlers
        setupEventListeners();

        // Initialize view
        elements.tableHeader.style.display = "none";

    } catch (error) {
        console.error("Initialization error:", error);
        elements.errorMessage.textContent = "Failed to initialize application";
        elements.errorModal.style.display = "block";
    }
}

// Start the application when DOM is ready
document.addEventListener("DOMContentLoaded", init);