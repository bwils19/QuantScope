const manualPortfolio = [];
let selectedSecurity = null;
const stockDataCache = {};
let securitiesData = [];
let searchType = "ticker";
let activeIndex = -1;
let currentPortfolioId = null;

let currentPortfolio = null;
let editedSecurities = new Map();
let selectedEditSecurity = null;

let editedPreviewData = [];
const MAX_NAME_SIMILARITY = 0.8;

let watchlistItems = [];
let watchlistStockData = {};

// Cache DOM elements
const elements = {
    portfolioList: document.getElementById("portfolio-list"),
    newPortfolioModal: document.getElementById("newPortfolioModal"),
    manualPortfolioTable: document.getElementById("manualPortfolioTable").querySelector("tbody"),
    tableHeader: document.querySelector("#manualPortfolioTable thead"),
    searchStockInput: document.getElementById("searchStockInput"),
    amountInput: document.getElementById("amountInput"),
    datePurchasedInput: document.getElementById("datePurchasedInput"),
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
    closePortfolioDetailsModal: document.getElementById('closePortfolioDetailsModal'),

    securitiesTableBody: document.getElementById("securitiesTableBody"),
    portfolioFileInput: document.getElementById('portfolioFileInput'),
    uploadPortfolioBtn: document.querySelector('.upload-portfolio-btn'),
    uploadPortfolioSection: document.getElementById('uploadPortfolioSection'),
    dropZone: document.getElementById('dropZone'),
    validationResults: document.getElementById('validationResults'),
    manualPortfolioSection: document.getElementById("manualPortfolioSection"),

    filePortfolioNameModal: document.getElementById('filePortfolioNameModal'),
    filePortfolioNameInput: document.getElementById('filePortfolioNameInput'),
    filePortfolioNameSaveBtn: document.getElementById('filePortfolioNameSaveBtn'),
    filePortfolioNameCancelBtn: document.getElementById('filePortfolioNameCancelBtn'),
    closeFilePortfolioNameModal: document.getElementById('closeFilePortfolioNameModal'),

    editPortfolioBtn: document.getElementById('editPortfolioBtn'),
    editModeControls: document.getElementById('editModeControls'),
    editSearchStockInput: document.getElementById('editSearchStockInput'),
    editSearchSuggestions: document.getElementById('editSearchSuggestions'),
    editAmountInput: document.getElementById('editAmountInput'),
    editAddSecurityBtn: document.getElementById('editAddSecurityBtn'),
    savePortfolioChangesBtn: document.getElementById('savePortfolioChangesBtn'),
    cancelEditModeBtn: document.getElementById('cancelEditModeBtn'),

    // watchlist
    watchlistSearchInput: document.getElementById('watchlistSearchInput'),
    watchlistSearchSuggestions: document.getElementById('watchlistSearchSuggestions'),
    watchlistSearchContainer: document.getElementById('watchlistSearchContainer'),
    watchlistSecurities: document.querySelector('.watchlist-securities'),
    addToWatchlistBtn: document.querySelector('.add-to-watchlist-btn'),

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
    try {
        // First check database cache, don't wanna be hitting that api a ton of times...
        const cacheResponse = await fetch(`/auth/stock-cache/${symbol}`, {
            credentials: 'include'  // Add this
        });
        const cacheData = await cacheResponse.json();

        if (cacheData.data && !isCacheExpired(cacheData.date)) {
            console.log(`Using cached data for ${symbol}`);
            return cacheData.data;
        }

        // If no cache or expired, fetch from API
        const apiKey = await getApiKey();
        if (!apiKey) {
            throw new Error('API key not available');
        }

        const response = await fetch(
            `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${apiKey}`
        );
        const data = await response.json();

        if (data['Global Quote']) {
            const quote = data['Global Quote'];
            const stockInfo = {
                currentPrice: parseFloat(quote['05. price']),
                previousClose: parseFloat(quote['08. previous close']),
                changePercent: parseFloat(quote['10. change percent']),
                latestTradingDay: quote['07. latest trading day']
            };

            const csrfToken = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrf_access_token='))
                ?.split('=')[1];

            // Save to database cache
            await fetch('/auth/stock-cache', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': csrfToken
                },
                body: JSON.stringify({
                    symbol: symbol,
                    data: stockInfo
                }),
                credentials: 'include'
            });

            return stockInfo;
        }
        throw new Error('Invalid API response');
    } catch (error) {
        console.error(`Error fetching data for ${symbol}:`, error);
        throw error;
    }
}
    function isCacheExpired(cacheDate) {
    const cache = new Date(cacheDate);
    const now = new Date();
    // Expire cache if it's from a previous day
    return cache.getDate() !== now.getDate() ||
           cache.getMonth() !== now.getMonth() ||
           cache.getFullYear() !== now.getFullYear();
}

function setupPortfolioActions() {
    document.querySelectorAll('.portfolio-dropdown-toggle').forEach(toggle => {
        toggle.addEventListener('click', function (e) {
            e.stopPropagation();
            const menu = this.nextElementSibling;

            // Toggle dropdown visibility
            const isVisible = menu.style.display === 'block';
            document.querySelectorAll('.portfolio-dropdown-menu').forEach(otherMenu => {
                otherMenu.style.display = 'none'; // Close other menus
            });
            menu.style.display = isVisible ? 'none' : 'block'; // Toggle this menu
        });
    });

    // Hide dropdown if clicking anywhere else
    document.addEventListener('click', () => {
        document.querySelectorAll('.portfolio-dropdown-menu').forEach(menu => {
            menu.style.display = 'none';
        });
    });

    // Prevent dropdown from closing when clicking inside it
    document.querySelectorAll('.portfolio-dropdown-menu').forEach(menu => {
        menu.addEventListener('click', e => {
            e.stopPropagation();
        });
    });

    // Close the dropdown when mouse leaves the container
    document.querySelectorAll('.portfolio-dropdown-container').forEach(container => {
        const menu = container.querySelector('.portfolio-dropdown-menu');
        container.addEventListener('mouseleave', () => {
            menu.style.display = 'none';
        });
    });

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
            const csrfToken = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrf_access_token='))
                ?.split('=')[1];

            const response = await fetch(`/auth/portfolio/${currentPortfolioId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': csrfToken
                },
                credentials: 'include'
            });

            if (response.ok) {
                elements.deleteConfirmModal.style.display = "none";
                const portfolioCard = document.querySelector(`.portfolio-item[data-id="${currentPortfolioId}"]`);
                if (portfolioCard) {
                    portfolioCard.remove();
                }
                elements.successMessage.textContent = "Portfolio deleted successfully";
                elements.successModal.style.display = "block";

                setTimeout(() => {
                    location.reload();
                }, 1500);
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

    // Setup rename functionality
    document.querySelectorAll('.rename-portfolio-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const portfolioId = e.target.dataset.id;
            const portfolioCard = e.target.closest('.portfolio-item');
            const titleElement = portfolioCard.querySelector('h4');
            const currentName = titleElement.textContent;

            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentName;
            input.className = 'rename-input';

            const saveBtn = document.createElement('button');
            saveBtn.textContent = 'Save';
            saveBtn.className = 'rename-save-btn';

            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = 'Cancel';
            cancelBtn.className = 'rename-cancel-btn';

            const container = document.createElement('div');
            container.className = 'rename-container';
            container.appendChild(input);
            container.appendChild(saveBtn);
            container.appendChild(cancelBtn);

            titleElement.replaceWith(container);
            input.focus();
            input.select();

            saveBtn.addEventListener('click', async () => {
                const newName = input.value.trim();
                if (newName && newName !== currentName) {
                    try {
                        await renamePortfolio(portfolioId, newName);
                        titleElement.textContent = newName;
                        container.replaceWith(titleElement);
                        showSuccess('Portfolio renamed successfully');
                    } catch (error) {
                        showError('Failed to rename portfolio: ' + error.message);
                    }
                } else {
                    container.replaceWith(titleElement);
                }
            });

            cancelBtn.addEventListener('click', () => {
                container.replaceWith(titleElement);
            });

            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    saveBtn.click();
                }
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    cancelBtn.click();
                }
            });
        });
    });
}

async function renamePortfolio(portfolioId, newName) {
    const csrfToken = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrf_access_token='))
        ?.split('=')[1];

    const response = await fetch(`/auth/portfolio/${portfolioId}/rename`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': csrfToken
        },
        body: JSON.stringify({ name: newName }),
        credentials: 'include'
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to rename portfolio');
    }

    return response.json();
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
        currentPortfolio = portfolioId;  // Set  current portfolio ID

        data.securities.forEach(security => {
            const row = document.createElement('tr');
            row.dataset.securityId = security.id;  // add security ID to the row

            // Format percentages with null checks
            const valueChangePct = security.value_change_pct != null
                ? `(${security.value_change_pct.toFixed(2)}%)`
                : '(0.00%)';

            // commenting this out for now because i want to get rid of the unrealised G/L in the view
            // const totalGainPct = security.total_gain_pct != null
            //     ? `(${security.total_gain_pct.toFixed(2)}%)`
            //     : '(0.00%)';

            row.innerHTML = `
                <td>${security.name} (${security.ticker})</td>
                <td>${security.amount_owned}</td>
                <td>${formatCurrency(security.current_price || 0)}</td>
                <td>${formatCurrency(security.total_value || 0)}</td>
                <td class="${(security.value_change || 0) >= 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(security.value_change || 0)}
                    ${valueChangePct}
                </td>
                <td>${formatCurrency(security.latest_close || 0)}</td>
                <td>${security.latest_close_date || 'N/A'}</td>
                <td class="action-buttons hidden"></td>
            `;
            elements.securitiesTableBody.appendChild(row);
        });

        // Reset edit mode
        elements.editModeControls.classList.add('hidden');
        document.querySelector('.edit-column').classList.add('hidden');
        elements.editPortfolioBtn.textContent = 'Edit Portfolio';
        editedSecurities.clear();

        const modalContent = elements.portfolioDetailsModal.querySelector('.modal-content');
        const existingTimestamp = modalContent.querySelector('.data-timestamp');
        if (existingTimestamp) {
            existingTimestamp.remove();
        }

        if (data.latest_update) {
            const timestamp = document.createElement('div');
            timestamp.className = 'data-timestamp';
            timestamp.textContent = `Latest Update: ${data.latest_update}`;
            modalContent.appendChild(timestamp);
        }

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
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

function findMatchingTicker(companyName) {
    if (!companyName) return null;

    // Convert to lowercase for comparison
    const searchName = companyName.toLowerCase();

    const matches = securitiesData
        .map(security => ({
            symbol: security.symbol,
            name: security.name,
            similarity: stringSimilarity(security.name.toLowerCase(), searchName)
        }))
        .filter(match => match.similarity > MAX_NAME_SIMILARITY)
        .sort((a, b) => b.similarity - a.similarity);

    return matches.length > 0 ? matches[0] : null;
}

function stringSimilarity(str1, str2) {
    const maxLength = Math.max(str1.length, str2.length);
    if (maxLength === 0) return 1.0;

    const distance = levenshteinDistance(str1, str2);
    return 1 - distance / maxLength;
}

function levenshteinDistance(str1, str2) {
    const dp = Array(str1.length + 1).fill(null)
        .map(() => Array(str2.length + 1).fill(0));

    for (let i = 0; i <= str1.length; i++) dp[i][0] = i;
    for (let j = 0; j <= str2.length; j++) dp[0][j] = j;

    for (let i = 1; i <= str1.length; i++) {
        for (let j = 1; j <= str2.length; j++) {
            dp[i][j] = Math.min(
                dp[i-1][j] + 1,
                dp[i][j-1] + 1,
                dp[i-1][j-1] + (str1[i-1] === str2[j-1] ? 0 : 1)
            );
        }
    }
    return dp[str1.length][str2.length];
}

function formatPercentage(value) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value) + '%';
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
        showError("Please select a security first.", "newPortfolioModal");
        return;
    }

    const amount = parseFloat(elements.amountInput.value.trim());
    if (!amount || amount <= 0) {
        showError("Please enter a valid amount.", "newPortfolioModal");
        return;
    }

    const purchaseDate = elements.datePurchasedInput.value.trim();
    if (!purchaseDate) {
        showError("Please select a purchase date.");
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
        purchase_date: purchaseDate,
        valueChange: dailyChange,
        totalValue: totalValue,
    });

    elements.searchStockInput.value = "";
    elements.amountInput.value = "";
    selectedSecurity = null;
    elements.datePurchasedInput.value = "";
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
        <td class="purchase-date">${stock.purchase_date || "Not Provided"}</td>
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

    // Get CSRF token
    const csrfToken = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrf_access_token='))
        ?.split('=')[1];

    const stocks = manualPortfolio.map(stock => ({
        ticker: stock.equityDetails.split(":")[0],
        name: stock.equityName,
        exchange: stock.equityDetails.split(":")[1],
        date_purchased: stock.datePurchased,
        amount: stock.amount,

        valueChange: parseFloat(stock.valueChange),
        totalValue: parseFloat(stock.totalValue)
    }));

    const response = await fetch("/auth/create-portfolio", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-TOKEN": csrfToken
        },
        body: JSON.stringify({name: portfolioName, stocks}),
        credentials: 'include'
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create portfolio');
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

function setupFileUploadHandlers() {
    if (elements.uploadPortfolioBtn) {
        elements.uploadPortfolioBtn.addEventListener('click', () => {
            if (elements.manualPortfolioSection) {
                elements.manualPortfolioSection.classList.add('hidden');
            }
            if (elements.uploadPortfolioSection) {
                elements.uploadPortfolioSection.classList.remove('hidden');
            }
        });
    }

    if (elements.portfolioFileInput) {
        elements.portfolioFileInput.addEventListener('change', handleFileUpload);
    }

    if (elements.dropZone) {
        elements.dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            elements.dropZone.classList.add('drag-over');
        });

        elements.dropZone.addEventListener('dragleave', () => {
            elements.dropZone.classList.remove('drag-over');
        });

        elements.dropZone.addEventListener('drop', handleFileDrop);
    }
}

function setupFilePortfolioHandlers() {
    console.log('Setting up file portfolio handlers');

    // Handle the "Create Portfolio" button click from the preview
    document.getElementById('createPortfolioBtn').addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        console.log('Create portfolio button clicked');
        elements.filePortfolioNameInput.value = ''; // Clear any previous input
        elements.filePortfolioNameModal.style.display = 'block';
    });

    // Handle portfolio name save
    elements.filePortfolioNameSaveBtn.addEventListener('click', async (e) => {
        console.log('Save button clicked');
        e.preventDefault();
        const portfolioName = elements.filePortfolioNameInput.value.trim();

        if (!portfolioName) {
            showError('Please enter a portfolio name');
            return;
        }

        console.log('Creating portfolio with name:', portfolioName);
        await handlePortfolioCreation(portfolioName);
        elements.filePortfolioNameModal.style.display = 'none';
    });

    // Handle modal close buttons
    elements.closeFilePortfolioNameModal.addEventListener('click', () => {
        elements.filePortfolioNameModal.style.display = 'none';
    });

    elements.filePortfolioNameCancelBtn.addEventListener('click', () => {
        elements.filePortfolioNameModal.style.display = 'none';
    });

    // Close modal on outside click
    window.addEventListener('click', (event) => {
        if (event.target === elements.filePortfolioNameModal) {
            elements.filePortfolioNameModal.style.display = 'none';
        }
    });
}

async function addNewSecurity() {
    console.log('Starting addNewSecurity...');

    if (!selectedEditSecurity) {
        showError("Please select a security first","portfolioDetailsModal");
        return;
    }

    const amount = parseFloat(elements.editAmountInput.value);
    if (!amount || amount <= 0) {
        showError("Please enter a valid amount", "portfolioDetailsModal");
        return;
    }

    // Check for existing security with same ticker
    const existingRows = elements.securitiesTableBody.querySelectorAll('tr');
    for (const row of existingRows) {
        const tickerCell = row.querySelector('td:nth-child(1)');
        if (!tickerCell) continue;

        const match = tickerCell.textContent.match(/\((.*?)\)/);
        if (match && match[1] === selectedEditSecurity.symbol) {
            showError(`${selectedEditSecurity.symbol} is already in this portfolio`, "portfolioDetailsModal");
            elements.editSearchStockInput.value = '';
            elements.editAmountInput.value = '';
            selectedEditSecurity = null;
            return;
        }
    }

    try {
        const stockData = await fetchStockData(selectedEditSecurity.symbol);
        if (!stockData) {
            throw new Error(`Could not fetch data for ${selectedEditSecurity.symbol}`);
        }

        const newSecurity = {
            ticker: selectedEditSecurity.symbol,
            name: selectedEditSecurity.name,
            amount: amount,
            current_price: stockData.currentPrice,
            total_value: amount * stockData.currentPrice,
            value_change: amount * (stockData.currentPrice - stockData.previousClose),
            value_change_pct: ((stockData.currentPrice - stockData.previousClose) / stockData.previousClose) * 100,
            total_gain: 0,
            total_gain_pct: 0
        };

        // Add new row to table
        const row = document.createElement('tr');
        row.dataset.securityId = 'new_' + Date.now(); // Temporary ID for new securities

        row.innerHTML = `
            <td>${newSecurity.name} (${newSecurity.ticker})</td>
            <td>${newSecurity.amount}</td>
            <td>${formatCurrency(newSecurity.current_price)}</td>
            <td>${formatCurrency(newSecurity.total_value)}</td>
            <td class="${newSecurity.value_change >= 0 ? 'positive' : 'negative'}">
                ${formatCurrency(newSecurity.value_change)}
                (${newSecurity.value_change_pct.toFixed(2)}%)
            </td>
            <td>N/A</td>
            <td class="action-buttons">
                <button class="delete-btn" onclick="removeNewSecurity(this)">Remove</button>
            </td>
        `;

        elements.securitiesTableBody.appendChild(row);
        editedSecurities.set(row.dataset.securityId, { new: true, ...newSecurity });

        // Clear inputs
        elements.editSearchStockInput.value = '';
        elements.editAmountInput.value = '';
        selectedEditSecurity = null;

    } catch (error) {
        showError(error.message);
    }
}

function removeNewSecurity(button) {
    const row = button.closest('tr');
    const securityId = row.dataset.securityId;
    editedSecurities.delete(securityId);
    row.remove();
}

function handleEditSearchInput() {
    const query = elements.editSearchStockInput.value.trim().toLowerCase();
    elements.editSearchSuggestions.innerHTML = '';

    if (query.length === 0) {
        elements.editSearchSuggestions.classList.add('hidden');
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
        .slice(0, 10);  // Limit to 10 suggestions

    if (filteredSecurities.length === 0) {
        elements.editSearchSuggestions.classList.add('hidden');
        return;
    }

    filteredSecurities.forEach(security => {
        const li = document.createElement('li');
        li.textContent = `${security.symbol} - ${security.name}`;
        li.addEventListener('click', () => {
            selectedEditSecurity = security;
            elements.editSearchStockInput.value = `${security.symbol} - ${security.name}`;
            elements.editSearchSuggestions.classList.add('hidden');
            elements.editAmountInput.focus();
        });
        elements.editSearchSuggestions.appendChild(li);
    });

    elements.editSearchSuggestions.classList.remove('hidden');
}

function handleEditSearchKeydown(e) {
    const suggestions = elements.editSearchSuggestions.querySelectorAll('li');
    if (suggestions.length === 0) return;

    if (e.key === 'Enter' && suggestions.length === 1) {
        e.preventDefault();
        suggestions[0].click();
    }
}

async function createPortfolioFromFile(portfolioName) {
    try {
        const createBtn = document.getElementById('createPortfolioBtn');
        const fileId = createBtn.dataset.fileId;

        if (!fileId) {
            throw new Error('No file ID found. Please try uploading the file again.');
        }

        console.log('Creating portfolio:', {
            fileId,
            portfolioName
        });

        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_access_token='))
            ?.split('=')[1];

        const response = await fetch(`/auth/create-portfolio-from-file/${fileId}`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': csrfToken
            },
            body: JSON.stringify({
                portfolio_name: portfolioName
            }),
            credentials: 'include'
        });

        console.log('Response status:', response.status);

        const responseText = await response.text();
        console.log('Response text:', responseText);

        let data;
        try {
            data = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response:', e);
            throw new Error('Invalid server response');
        }

        if (!response.ok) {
            throw new Error(data.message || 'Failed to create portfolio');
        }

        showSuccess("Portfolio created successfully!");
        setTimeout(() => {
            location.reload();
        }, 1500);

    } catch (error) {
        console.error('Error creating portfolio:', error);
        showError(error.message || "Failed to create portfolio. Please try again.");
    }
}

async function handlePortfolioCreation(portfolioName) {
    console.log('Edited Preview Data:', editedPreviewData);
    try {
        if (!portfolioName || portfolioName.trim() === '') {
            elements.filePortfolioNameModal.style.display = 'block';
            return;
        }
        const createBtn = document.getElementById('createPortfolioBtn');
        const fileId = createBtn.dataset.fileId;

        if (!fileId) {
            throw new Error('No file ID found. Please try uploading the file again.');
        }

        // Debug logs
        console.log('=== Portfolio Creation Request ===');
        console.log('File ID:', fileId);
        console.log('Portfolio Name:', portfolioName);

        const requestData = {
            portfolio_name: portfolioName,
            preview_data: editedPreviewData  // Send edited data
        };
        console.log('Request Data:', requestData);

        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_access_token='))
            ?.split('=')[1];

        const response = await fetch(`/auth/create-portfolio-from-file/${fileId}`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': csrfToken
            },
            body: JSON.stringify(requestData),
            credentials: 'include'
        });

        console.log('Response Status:', response.status);
        const responseText = await response.text();
        console.log('Response Text:', responseText);

        let responseData;
        try {
            responseData = JSON.parse(responseText);
            console.log('Parsed Response:', responseData);
        } catch (e) {
            console.error('Failed to parse response:', e);
            throw new Error('Invalid response format from server');
        }

        if (!response.ok) {
            throw new Error(responseData.message || 'Failed to create portfolio');
        }

        showSuccess("Portfolio created successfully!");
        setTimeout(() => {
            location.reload();
        }, 1500);

    } catch (error) {
        console.error('Portfolio Creation Error:', error);
        showError(error.message || "Failed to create portfolio. Please try again.");
    }
}


async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const validTypes = ['.csv', '.xlsx', '.xls', '.txt'];
    const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));

    if (!validTypes.includes(fileExtension)) {
        showError("Invalid file type. Please upload CSV, Excel, or text file.");
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_access_token='))
            ?.split('=')[1];

        const response = await fetch('/auth/preview-portfolio-file', {
            method: 'POST',
            headers: {
                'X-CSRF-TOKEN': csrfToken
            },
            body: formData,
            credentials: 'include'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to process file');
        }

        const result = await response.json();

        // Store file ID in a data attribute
        document.getElementById('createPortfolioBtn').dataset.fileId = result.file_id;

        displayFilePreview(result);

    } catch (error) {
        showError(error.message || "Failed to process file");
    }
}

function displayFilePreview(data) {
   document.getElementById('totalRows').textContent = data.summary.total_rows;
   document.getElementById('validRows').textContent = data.summary.valid_rows;
   document.getElementById('invalidRows').textContent = data.summary.invalid_rows;
   document.getElementById('totalAmount').textContent = new Intl.NumberFormat('en-US').format(data.summary.total_amount);

   editedPreviewData = [...data.preview_data];

   const tableBody = document.querySelector('#previewTable tbody');
   tableBody.innerHTML = '';

   data.preview_data.forEach((row, rowIndex) => {
       const tr = document.createElement('tr');
       tr.className = row.validation_status;
       tr.dataset.rowIndex = rowIndex;
       tr.dataset.originalData = JSON.stringify(row);

       const cells = [
           { field: 'ticker', value: row.ticker, required: true, validate: validateTicker },
           { field: 'amount', value: row.amount, required: true, validate: validateAmount },
           { field: 'purchase_date', value: row.purchase_date, required: true, validate: validateDate },
           { field: 'purchase_price', value: row.purchase_price, required: false, validate: validatePrice },
           { field: 'current_price', value: row.current_price, required: false, validate: validatePrice },
           { field: 'sector', value: row.sector, required: false },
           { field: 'notes', value: row.notes, required: false },
           { field: 'validation_status', value: row.validation_status, required: false, readonly: true },
           { field: 'validation_message', value: row.validation_message, required: false, readonly: true }
       ];

       cells.forEach((cell) => {
           const td = document.createElement('td');

           if (!cell.readonly) {
               td.contentEditable = true;
               td.dataset.field = cell.field;
               td.dataset.required = cell.required;

               if (cell.required && !cell.value) {
                   td.classList.add('invalid');
               }
           }

           if (cell.field === 'purchase_price' || cell.field === 'current_price') {
               td.textContent = cell.value ? `$${cell.value.toLocaleString()}` : '';
           } else {
               td.textContent = cell.value || '';
           }

           if (!cell.readonly) {
               td.addEventListener('focus', function() {
                   if (this.textContent.startsWith('$')) {
                       this.textContent = this.textContent.replace('$', '').replace(/,/g, '');
                   }
               });

                td.addEventListener('blur', async function() {
                    const newValue = this.textContent.trim();
                    const field = this.dataset.field;
                    const required = this.dataset.required === 'true';
                    const rowIndex = parseInt(tr.dataset.rowIndex);

                    const validationMessageCell = tr.querySelector('td:nth-child(9)');
                    const validationStatusCell = tr.querySelector('td:nth-child(8)');

                    if (field === 'ticker') {
                        // Get company name if available
                        const companyName = editedPreviewData[rowIndex].company_name || null;

                        const validation = await validateTicker(newValue, required, companyName);

                        if (!validation.isValid) {
                            if (validation.suggestion) {
                                const useSymbol = confirm(validation.message);
                                if (useSymbol) {
                                    this.textContent = validation.suggestion.symbol;
                                    editedPreviewData[rowIndex].ticker = validation.suggestion.symbol;
                                    if (!editedPreviewData[rowIndex].company_name) {
                                        editedPreviewData[rowIndex].company_name = validation.suggestion.name;
                                    }

                                    // Clear validation errors
                                    this.classList.remove('invalid');
                                    tr.classList.remove('invalid');
                                    tr.classList.add('valid');
                                    editedPreviewData[rowIndex].validation_status = 'valid';
                                    editedPreviewData[rowIndex].validation_message = '';
                                    validationMessageCell.textContent = '';
                                    validationStatusCell.textContent = 'valid';
                                    updateRowValidation(tr);
                                    return;
                                }
                            }

                            // Handle invalid case
                            this.classList.add('invalid');
                            tr.classList.remove('valid');
                            tr.classList.add('invalid');
                            editedPreviewData[rowIndex].validation_status = 'invalid';
                            editedPreviewData[rowIndex].validation_message = validation.message;
                            validationMessageCell.textContent = validation.message;
                            validationStatusCell.textContent = 'invalid';
                        } else {
                            // Handle valid case
                            this.classList.remove('invalid');
                            tr.classList.remove('invalid');
                            tr.classList.add('valid');
                            editedPreviewData[rowIndex].ticker = newValue;
                            editedPreviewData[rowIndex].validation_status = 'valid';
                            editedPreviewData[rowIndex].validation_message = '';
                            validationMessageCell.textContent = '';
                            validationStatusCell.textContent = 'valid';
                        }
                    } else {
                        // Handle other fields (same as before)
                        const validation = cell.validate ?
                            await cell.validate(newValue, required) :
                            { isValid: true, message: '' };

                        if (validation.isValid) {
                            this.classList.remove('invalid');
                            tr.classList.remove('invalid');
                            tr.classList.add('valid');
                            if (field === 'purchase_price' || field === 'current_price') {
                                this.textContent = `$${parseFloat(newValue).toLocaleString()}`;
                                editedPreviewData[rowIndex][field] = parseFloat(newValue);
                            } else {
                                editedPreviewData[rowIndex][field] = newValue;
                            }
                            editedPreviewData[rowIndex].validation_status = 'valid';
                            editedPreviewData[rowIndex].validation_message = '';
                            validationMessageCell.textContent = '';
                            validationStatusCell.textContent = 'valid';
                        } else {
                            this.classList.add('invalid');
                            tr.classList.remove('valid');
                            tr.classList.add('invalid');
                            editedPreviewData[rowIndex].validation_status = 'invalid';
                            editedPreviewData[rowIndex].validation_message = validation.message;
                            validationMessageCell.textContent = validation.message;
                            validationStatusCell.textContent = 'invalid';
                        }
                    }
                    updateRowValidation(tr);
                });

               td.addEventListener('keydown', function(e) {
                   if (e.key === 'Enter') {
                       e.preventDefault();
                       this.blur();
                   }
               });
           }

           tr.appendChild(td);
       });

       tableBody.appendChild(tr);
   });

   document.getElementById('filePreviewSection').classList.remove('hidden');
   const createBtn = document.getElementById('createPortfolioBtn');
   createBtn.disabled = data.summary.invalid_rows > 0;

   if (createBtn.disabled) {
       createBtn.title = 'Fix validation errors before creating portfolio';
   } else {
       createBtn.title = 'Create portfolio with validated data';
   }
}

// Validation functions
async function validateTicker(value, required) {
    if (!value && required) return { isValid: false, message: 'Ticker is required' };

    // standardize the ticker format
    const ticker = value.trim().toUpperCase();

    // first check against local securities data - don't want to hit that API a bazillion times...
    const existsLocally = securitiesData.some(security => security.symbol === ticker);
    if (existsLocally) {
        return { isValid: true, message: '' };
    }

    // if not found locally, verify with API
    try {
        const response = await fetch(`/auth/validate-ticker/${ticker}`);
        const data = await response.json();
        return { isValid: data.valid, message: data.message };
    } catch (error) {
        // If API fails, return invalid
        return { isValid: false, message: 'Error validating ticker' };
    }
}

function validateAmount(value, required) {
    if (!value && required) return { isValid: false, message: 'Amount is required' };
    const amount = parseFloat(value);
    return {
        isValid: !isNaN(amount) && amount > 0,
        message: 'Amount must be a positive number'
    };
}

function validateDate(value, required) {
    if (!value && required) return { isValid: false, message: 'Date is required' };
    const date = new Date(value);
    return {
        isValid: !isNaN(date.getTime()),
        message: 'Invalid date format'
    };
}

function validatePrice(value, required) {
    if (!value && !required) return { isValid: true, message: '' };
    const price = parseFloat(value);
    return {
        isValid: !isNaN(price) && price >= 0,
        message: 'Price must be a non-negative number'
    };
}

function updateRowValidation(row) {
    const invalidCells = row.querySelectorAll('td.invalid');
    if (invalidCells.length > 0) {
        row.className = 'invalid';
    } else {
        row.className = 'valid';
    }
    updateCreateButtonState();
}

function updateCreateButtonState() {
    const createBtn = document.getElementById('createPortfolioBtn');
    const invalidRows = document.querySelectorAll('#previewTable tbody tr.invalid');
    createBtn.disabled = invalidRows.length > 0;

    if (createBtn.disabled) {
        createBtn.title = 'Fix validation errors before creating portfolio';
    } else {
        createBtn.title = 'Create portfolio with validated data';
    }
}


function setupPreviewHandlers() {
    document.getElementById('cancelPreviewBtn').addEventListener('click', () => {
        document.getElementById('filePreviewSection').classList.add('hidden');
        document.getElementById('portfolioFileInput').value = '';
    });

    document.getElementById('createPortfolioBtn').addEventListener('click', () => {
        handlePortfolioCreation();
    });
}

function handleFileDrop(e) {
    e.preventDefault();
    elements.dropZone.classList.remove('drag-over');

    const file = e.dataTransfer.files[0];
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    elements.portfolioFileInput.files = dataTransfer.files;
    elements.portfolioFileInput.dispatchEvent(new Event('change'));
}

function toggleEditMode(portfolioId) {
    console.log('Toggling edit mode for portfolio:', portfolioId);

    const editColumn = document.querySelector('.edit-column');
    const isEditMode = elements.editModeControls.classList.contains('hidden');

    console.log('Current edit mode state:', !isEditMode);

    if (!editColumn) {
        console.error('Edit column not found');
        return;
    }

    elements.editModeControls.classList.toggle('hidden');
    editColumn.classList.toggle('hidden');
    elements.editPortfolioBtn.textContent = isEditMode ? 'Cancel Edit' : 'Edit Portfolio';

    if (isEditMode) {
        // Entering edit mode
        currentPortfolio = portfolioId;
        console.log('Entering edit mode for portfolio:', currentPortfolio);
        refreshPortfolioView(true);
    } else {
        // Exiting edit mode
        console.log('Exiting edit mode');
        editedSecurities.clear();
        refreshPortfolioView(false);
    }
}

function refreshPortfolioView(isEditMode) {
    const securities = elements.securitiesTableBody.querySelectorAll('tr');
    securities.forEach(row => {
        const securityId = row.dataset.securityId;
        if (isEditMode) {
            // Add edit and delete buttons
            const actionsCell = document.createElement('td');
            actionsCell.className = 'action-buttons';
            actionsCell.innerHTML = `
                <button class="edit-btn" onclick="editSecurity('${securityId}')">Edit</button>
                <button class="delete-btn" onclick="deleteSecurity('${securityId}')">Delete</button>
            `;
            row.appendChild(actionsCell);
        } else {
            // Remove action column
            const actionsCell = row.querySelector('.action-buttons');
            if (actionsCell) {
                actionsCell.remove();
            }
        }
    });

document.addEventListener('click', (event) => {
    if (!elements.editSearchStockInput?.contains(event.target) &&
        !elements.editSearchSuggestions?.contains(event.target)) {
        elements.editSearchSuggestions?.classList.add('hidden');
    }
});
}

async function editSecurity(securityId) {
    const row = document.querySelector(`tr[data-security-id="${securityId}"]`);
    const amountCell = row.querySelector('td:nth-child(2)');
    const currentPriceCell = row.querySelector('td:nth-child(3)');
    const totalValueCell = row.querySelector('td:nth-child(4)');
    const valueChangeCell = row.querySelector('td:nth-child(5)');
    const totalGainCell = row.querySelector('td:nth-child(6)');

    const currentAmount = parseFloat(amountCell.textContent);
    const currentPrice = parseFloat(currentPriceCell.textContent.replace(/[^0-9.-]+/g, ''));

    const input = document.createElement('input');
    input.type = 'number';
    input.value = currentAmount;
    input.className = 'edit-amount-input';

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.className = 'edit-btn';
    saveBtn.onclick = async () => {
        const newAmount = parseFloat(input.value);
        if (newAmount > 0) {
            try {
                // Get the ticker from the first cell
                const ticker = row.querySelector('td:nth-child(1)').textContent.match(/\((.*?)\)/)[1];
                const stockData = await fetchStockData(ticker);

                if (stockData) {
                    const newTotalValue = newAmount * stockData.currentPrice;
                    const newValueChange = newAmount * (stockData.currentPrice - stockData.previousClose);
                    const valueChangePct = ((stockData.currentPrice - stockData.previousClose) / stockData.previousClose) * 100;

                    // Update amount
                    amountCell.textContent = newAmount;

                    // Update total value
                    totalValueCell.textContent = formatCurrency(newTotalValue);

                    // Update value change with percentage
                    valueChangeCell.textContent = `${formatCurrency(newValueChange)} (${valueChangePct.toFixed(2)}%)`;
                    valueChangeCell.className = newValueChange >= 0 ? 'positive' : 'negative';

                    // Store the changes for saving
                    editedSecurities.set(securityId, {
                        amount: newAmount,
                        total_value: newTotalValue,
                        value_change: newValueChange,
                        value_change_pct: valueChangePct
                    });

                    row.querySelector('.action-buttons').style.display = 'flex';
                }
            } catch (error) {
                showError('Failed to update security: ' + error.message);
            }
        } else {
            showError('Please enter a valid amount greater than 0');
        }
    };

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'delete-btn';
    cancelBtn.onclick = () => {
        amountCell.textContent = currentAmount;
        row.querySelector('.action-buttons').style.display = 'flex';
    };

    amountCell.textContent = '';
    amountCell.appendChild(input);
    amountCell.appendChild(saveBtn);
    amountCell.appendChild(cancelBtn);
    row.querySelector('.action-buttons').style.display = 'none';
}

async function deleteSecurity(securityId) {
    if (confirm('Are you sure you want to remove this security from the portfolio?')) {
        editedSecurities.set(securityId, { deleted: true });
        const row = document.querySelector(`tr[data-security-id="${securityId}"]`);
        row.style.display = 'none';
    }
}

function refreshPrices(portfolioId = null) {
    // Show loading indicator
    const loadingToast = showToast('Refreshing prices...', 'info');

    // Update UI to show loading state
    if (portfolioId) {
        // Find and update the specific portfolio refresh button
        const refreshBtn = document.querySelector(`.refresh-portfolio-btn[data-id="${portfolioId}"]`);
        if (refreshBtn) {
            refreshBtn.classList.add('loading');
            refreshBtn.disabled = true;
        }
    } else {
        // Global refresh - update all buttons
        const globalRefreshBtn = document.getElementById('refreshAllPricesBtn');
        if (globalRefreshBtn) {
            globalRefreshBtn.classList.add('loading');
            globalRefreshBtn.disabled = true;
        }

        // Disable all individual refresh buttons
        document.querySelectorAll('.refresh-portfolio-btn').forEach(btn => {
            btn.classList.add('loading');
            btn.disabled = true;
        });
    }

    // Determine the endpoint - refresh all or just one portfolio
    const endpoint = portfolioId
        ? `/auth/portfolio/${portfolioId}/update-prices`
        : '/auth/update-all-prices';

    // Get CSRF token
    const csrfToken = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrf_access_token='))
        ?.split('=')[1];

    // Make the request
    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': csrfToken
        },
        credentials: 'include'
    })
    .then(response => {
        if (!response.ok) {
            if (response.status === 401) {
                // Session expired
                showToast('Your session has expired. Please log in again.', 'error');
                setTimeout(() => {
                    window.location.href = '/auth/login';
                }, 2000);
                return null;
            }
            return response.json().then(data => {
                throw new Error(data.message || 'Failed to refresh prices');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data) {
            // Hide loading indicator
            loadingToast.hide();

            // Update the timestamp in the UI
            if (data.timestamp) {
                updateLastRefreshTimestamp(data.timestamp, data.portfolio_id);
            }

            // Show success message
            showToast(`Successfully updated ${data.updated_count} securities`, 'success');
            
            // Log the updated metrics for debugging
            console.log("Price update complete with metrics:", data);
            
            // Update the UI with the new values instead of reloading the page
            if (data.portfolio_id) {
                // Update the specific portfolio card
                const portfolioCard = document.querySelector(`.portfolio-item[data-id="${data.portfolio_id}"]`);
                if (portfolioCard) {
                    // Update total return value
                    const totalReturnElement = portfolioCard.querySelector('.metric-item:nth-child(5) .metric-value');
                    if (totalReturnElement && data.total_return !== undefined) {
                        const totalReturnClass = data.total_return > 0 ? 'positive' : (data.total_return < 0 ? 'negative' : '');
                        totalReturnElement.className = `metric-value ${totalReturnClass}`;
                        totalReturnElement.innerHTML = `
                            $${parseFloat(data.total_return).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                            (${parseFloat(data.total_return_pct).toFixed(2)}%)
                        `;
                    }
                    
                    // Also update other metrics
                    const totalValueElement = portfolioCard.querySelector('.metric-item:nth-child(2) .metric-value');
                    if (totalValueElement && data.total_value !== undefined) {
                        totalValueElement.textContent = `$${parseFloat(data.total_value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    }
                    
                    const dayChangeElement = portfolioCard.querySelector('.metric-item:nth-child(3) .metric-value');
                    if (dayChangeElement && data.day_change !== undefined) {
                        const dayChangeClass = data.day_change > 0 ? 'positive' : (data.day_change < 0 ? 'negative' : '');
                        dayChangeElement.className = `metric-value ${dayChangeClass}`;
                        dayChangeElement.innerHTML = `
                            $${parseFloat(data.day_change).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                            (${parseFloat(data.day_change_pct).toFixed(2)}%)
                        `;
                    }
                    
                    const totalGainElement = portfolioCard.querySelector('.metric-item:nth-child(4) .metric-value');
                    if (totalGainElement && data.total_gain !== undefined) {
                        const totalGainClass = data.total_gain > 0 ? 'positive' : (data.total_gain < 0 ? 'negative' : '');
                        totalGainElement.className = `metric-value ${totalGainClass}`;
                        totalGainElement.innerHTML = `
                            $${parseFloat(data.total_gain).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                            (${parseFloat(data.total_gain_pct).toFixed(2)}%)
                        `;
                    }
                }
            } else if (data.portfolios) {
                // Update all portfolios
                data.portfolios.forEach(portfolio => {
                    const portfolioCard = document.querySelector(`.portfolio-item[data-id="${portfolio.id}"]`);
                    if (portfolioCard) {
                        // Update total return value
                        const totalReturnElement = portfolioCard.querySelector('.metric-item:nth-child(5) .metric-value');
                        if (totalReturnElement) {
                            const totalReturnClass = portfolio.total_return > 0 ? 'positive' : (portfolio.total_return < 0 ? 'negative' : '');
                            totalReturnElement.className = `metric-value ${totalReturnClass}`;
                            totalReturnElement.innerHTML = `
                                $${parseFloat(portfolio.total_return).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                                (${parseFloat(portfolio.total_return_pct).toFixed(2)}%)
                            `;
                        }
                        
                        // Also update other metrics
                        const totalValueElement = portfolioCard.querySelector('.metric-item:nth-child(2) .metric-value');
                        if (totalValueElement) {
                            totalValueElement.textContent = `$${parseFloat(portfolio.total_value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                        }
                        
                        const dayChangeElement = portfolioCard.querySelector('.metric-item:nth-child(3) .metric-value');
                        if (dayChangeElement) {
                            const dayChangeClass = portfolio.day_change > 0 ? 'positive' : (portfolio.day_change < 0 ? 'negative' : '');
                            dayChangeElement.className = `metric-value ${dayChangeClass}`;
                            dayChangeElement.innerHTML = `
                                $${parseFloat(portfolio.day_change).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                                (${parseFloat(portfolio.day_change_pct).toFixed(2)}%)
                            `;
                        }
                        
                        const totalGainElement = portfolioCard.querySelector('.metric-item:nth-child(4) .metric-value');
                        if (totalGainElement) {
                            const totalGainClass = portfolio.total_gain > 0 ? 'positive' : (portfolio.total_gain < 0 ? 'negative' : '');
                            totalGainElement.className = `metric-value ${totalGainClass}`;
                            totalGainElement.innerHTML = `
                                $${parseFloat(portfolio.total_gain).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                                (${parseFloat(portfolio.total_gain_pct).toFixed(2)}%)
                            `;
                        }
                    }
                });
            }
        }
    })
    .catch(error => {
        // Hide loading indicator
        loadingToast.hide();

        // Show error
        showToast(`Error: ${error.message}`, 'error');
        console.error('Price refresh error:', error);
    })
    .finally(() => {
        // Reset UI state regardless of outcome
        if (portfolioId) {
            // Reset specific portfolio button
            const refreshBtn = document.querySelector(`.refresh-portfolio-btn[data-id="${portfolioId}"]`);
            if (refreshBtn) {
                refreshBtn.classList.remove('loading');
                refreshBtn.disabled = false;
            }
        } else {
            // Reset global refresh button
            const globalRefreshBtn = document.getElementById('refreshAllPricesBtn');
            if (globalRefreshBtn) {
                globalRefreshBtn.classList.remove('loading');
                globalRefreshBtn.disabled = false;
            }

            // Reset all individual portfolio buttons
            document.querySelectorAll('.refresh-portfolio-btn').forEach(btn => {
                btn.classList.remove('loading');
                btn.disabled = false;
            });
        }
    });
}

// Helper function to update timestamp elements
function updateLastRefreshTimestamp(timestamp, portfolioId) {
    if (portfolioId) {
        // Update timestamp for specific portfolio
        const timestampElement = document.querySelector(`.portfolio-item[data-id="${portfolioId}"] .portfolio-timestamp`);
        if (timestampElement) {
            timestampElement.textContent = `Last Updated: ${timestamp}`;
        }
    } else {
        // Update global timestamp
        const pageTimestamp = document.getElementById('pageTimestamp');
        if (pageTimestamp) {
            pageTimestamp.textContent = `Data as of: ${timestamp}`;
        }

        // Also update all individual portfolio timestamps
        document.querySelectorAll('.portfolio-timestamp').forEach(element => {
            element.textContent = `Last Updated: ${timestamp}`;
        });
    }
}

// Helper function to show toast notifications
function showToast(message, type = 'info') {
    // Check if we need to create the toast container
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);

        // Add some basic styling if not already added
        if (!document.querySelector('#toast-styles')) {
            const style = document.createElement('style');
            style.id = 'toast-styles';
            style.textContent = `
            .toast-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 1000;
                max-width: 300px;
            }
            
            .toast {
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                padding: 16px;
                margin-bottom: 10px;
                transition: all 0.3s ease;
                opacity: 0;
                transform: translateY(-10px);
                display: flex;
                align-items: center;
            }
            
            .toast.show {
                opacity: 1;
                transform: translateY(0);
            }
            
            .toast.info {
                border-left: 4px solid #3498db;
            }
            
            .toast.success {
                border-left: 4px solid #2ecc71;
            }
            
            .toast.error {
                border-left: 4px solid #e74c3c;
            }
            
            .toast-message {
                flex-grow: 1;
                font-size: 14px;
                color: #333;
            }
            
            .toast-progress {
                position: absolute;
                bottom: 0;
                left: 0;
                height: 3px;
                width: 100%;
                background-color: rgba(0, 0, 0, 0.1);
            }
            
            .toast-progress-bar {
                height: 100%;
                width: 100%;
                transform-origin: left;
                animation: progress 5s linear forwards;
            }
            
            .toast.info .toast-progress-bar {
                background-color: #3498db;
            }
            
            .toast.success .toast-progress-bar {
                background-color: #2ecc71;
            }
            
            .toast.error .toast-progress-bar {
                background-color: #e74c3c;
            }
            
            @keyframes progress {
                0% {
                    transform: scaleX(1);
                }
                100% {
                    transform: scaleX(0);
                }
            }`;
            document.head.appendChild(style);
        }
    }

    // Create the toast element
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    // Create the toast content
    toast.innerHTML = `
        <div class="toast-message">${message}</div>
        <div class="toast-progress">
            <div class="toast-progress-bar"></div>
        </div>
    `;

    // Add the toast to the container
    toastContainer.appendChild(toast);

    // Show the toast (after a small delay to allow for animation)
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    // Remove after 5 seconds (matches the CSS animation)
    const timeout = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300); // Wait for fade out animation
    }, 5000);

    // Return an object that allows hiding the toast programmatically
    return {
        hide: () => {
            clearTimeout(timeout);
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }
    };
}

async function savePortfolioChanges() {
    try {
        const changes = {
            portfolio_id: currentPortfolio,
            changes: Array.from(editedSecurities.entries()).map(([id, change]) => ({
                security_id: id,
                ...change
            }))
        };

        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_access_token='))
            ?.split('=')[1];

        const response = await fetch(`/auth/portfolio/${currentPortfolio}/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': csrfToken
            },
            body: JSON.stringify(changes),
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to save changes');
        }
        elements.portfolioDetailsModal.style.display = "none";
        showSuccess('Portfolio updated successfully');
        setTimeout(() => {
            window.location.href = window.location.href.split('#')[0];
        }, 2000);

    } catch (error) {
        console.error('Save error:', error);
        showError('Failed to save changes: ' + error.message);
    }
}

    function setupPortfolioEditHandlers() {
        if (elements.editPortfolioBtn) {
            elements.editPortfolioBtn.addEventListener('click', () => {
                toggleEditMode(currentPortfolio);
            });
        } else {
            console.error('Edit portfolio button not found');
        }

        if (elements.cancelEditModeBtn) {
            elements.cancelEditModeBtn.addEventListener('click', () => {
                toggleEditMode(currentPortfolio);
            });
        }

        if (elements.savePortfolioChangesBtn) {
            elements.savePortfolioChangesBtn.addEventListener('click', () => {
                savePortfolioChanges();
            });
        }

        if (elements.editAddSecurityBtn && elements.editSearchStockInput) {
            elements.editAddSecurityBtn.addEventListener('click', addNewSecurity);
            elements.editSearchStockInput.addEventListener('input', handleEditSearchInput);
            elements.editSearchStockInput.addEventListener('keydown', handleEditSearchKeydown);
        }
    }

    function addErrorDisplay() {
        const manualSection = document.getElementById('manualPortfolioSection');
        if (!manualSection.querySelector('.modal-error')) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'modal-error hidden';
            manualSection.insertBefore(errorDiv, manualSection.firstChild);
        }

        // Add to portfolio details modal
        const portfolioDetails = document.getElementById('portfolioDetailsModal');
        if (!portfolioDetails.querySelector('.modal-error')) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'modal-error hidden';
            const modalContent = portfolioDetails.querySelector('.modal-content');
            modalContent.insertBefore(errorDiv, modalContent.firstChild);
        }
    }


    function showError(message, modalId = null) {
        console.log('Showing error:', {message, modalId});

        if (modalId) {
            const modalError = document.getElementById('portfolioModalError');
            if (modalError) {
                modalError.textContent = message;
                modalError.classList.remove('hidden');
                // Hide the error after 3 seconds
                setTimeout(() => {
                    modalError.classList.add('hidden');
                }, 3000);
                return;
            }
        }

        // Fallback to regular error modal
        elements.errorMessage.textContent = message;
        elements.errorModal.style.display = "block";
    }

    function showSuccess(message) {
        elements.successMessage.textContent = message;
        elements.successModal.style.display = "block";
    }

    function setupEventListeners() {
        // Search input handlers
        elements.searchStockInput.addEventListener("input", handleSearchInput);
        elements.searchStockInput.addEventListener("keydown", handleSearchKeydown);
        elements.searchStockInput.addEventListener("blur", () => {
            setTimeout(() => searchSuggestions.classList.add("hidden"), 200);
        });
        setupPortfolioActions();
        setupFileUploadHandlers();
        setupPreviewHandlers();
        setupFilePortfolioHandlers();
        setupPortfolioEditHandlers();


        // Search type radio buttons
        document.querySelectorAll('input[name="searchType"]').forEach(radio => {
            radio.addEventListener("change", (e) => {
                searchType = e.target.value;
            });
        });

        if (elements.closePortfolioDetailsModal) {
            elements.closePortfolioDetailsModal.addEventListener('click', () => {
                elements.portfolioDetailsModal.style.display = 'none';
            });
        }
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                if (elements.portfolioDetailsModal.style.display === 'block') {
                    elements.portfolioDetailsModal.style.display = 'none';
                }
            }
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

function navigateToRiskAnalysis(portfolioId) {
  window.location.href = `/risk-analysis?portfolio_id=${portfolioId}`;
}


// watchlist
function setupWatchlistHandlers() {
    const addToWatchlistBtn = document.querySelector('.add-to-watchlist-btn');
    const watchlistContainer = document.querySelector('.watchlist-securities');
    const watchlistSearchContainer = document.getElementById('watchlistSearchContainer');

    if (addToWatchlistBtn) {
        addToWatchlistBtn.addEventListener('click', () => {
            watchlistSearchContainer.classList.remove('hidden');
        });
    }

    // Setup search input handlers
    const watchlistSearchInput = document.getElementById('watchlistSearchInput');
    const watchlistSearchSuggestions = document.getElementById('watchlistSearchSuggestions');

    if (watchlistSearchInput) {
        watchlistSearchInput.addEventListener('input', handleWatchlistSearch);
        watchlistSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                watchlistSearchContainer.classList.add('hidden');
            }
        });
    }

    // Close search when clicking outside
    document.addEventListener('click', (e) => {
        if (!watchlistSearchContainer.contains(e.target) &&
            !addToWatchlistBtn.contains(e.target)) {
            watchlistSearchContainer.classList.add('hidden');
        }
    });
}

async function handleWatchlistSearch(event) {
    const query = event.target.value.trim();
    const suggestionsList = document.getElementById('watchlistSearchSuggestions');

    if (query.length < 2) {
        suggestionsList.innerHTML = '';
        suggestionsList.classList.add('hidden');
        return;
    }

    try {
        const response = await fetch(`/stocks/suggestions?query=${encodeURIComponent(query)}`);
        const suggestions = await response.json();

        suggestionsList.innerHTML = '';
        suggestions.forEach(security => {
            if (!watchlistItems.some(item => item.symbol === security.symbol)) {
                const li = document.createElement('li');
                li.className = 'watchlist-suggestion-item';
                li.innerHTML = `${security.symbol} - ${security.name}`;
                li.addEventListener('click', () => addToWatchlist(security));
                suggestionsList.appendChild(li);
            }
        });

        suggestionsList.classList.toggle('hidden', suggestions.length === 0);
    } catch (error) {
        console.error('Error fetching suggestions:', error);
    }
}

async function addToWatchlist(security) {
    try {
        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_access_token='))
            ?.split('=')[1];

        const response = await fetch('/auth/watchlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                ticker: security.symbol,
                name: security.name,
                exchange: security.exchange
            })
        });

        if (!response.ok) {
            throw new Error('Failed to add to watchlist');
        }

        const watchlistData = await response.json();

        // Get historical data from SecurityHistoricalData
        const historicalResponse = await fetch(`/auth/security-historical/${security.symbol}`, {
            credentials: 'include'
        });

        let priceData;
        if (historicalResponse.ok) {
            priceData = await historicalResponse.json();
        } else {
            // Only if no historical data exists, fetch from AV
            const stockDataResponse = await fetch('/stocks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: security.symbol })
            });
            priceData = await stockDataResponse.json();
        }

        // Store stock data for charts
        watchlistStockData[security.symbol] = {
            dates: priceData.dates.slice(-90),
            prices: priceData.prices.slice(-90)
        };

        // Add to watchlist with correct property names
        watchlistItems.push({
            id: watchlistData.id,
            ticker: security.symbol,
            name: security.name,
            exchange: security.exchange,
            current_price: priceData.prices[priceData.prices.length - 1],
            previous_close: priceData.prices[priceData.prices.length - 2],
            day_change: (priceData.prices[priceData.prices.length - 1] - priceData.prices[priceData.prices.length - 2]),
            day_change_pct: ((priceData.prices[priceData.prices.length - 1] - priceData.prices[priceData.prices.length - 2]) /
                priceData.prices[priceData.prices.length - 2] * 100)
        });

        renderWatchlistItems();

        // Clear and hide search
        elements.watchlistSearchInput.value = '';
        elements.watchlistSearchContainer.classList.add('hidden');
        elements.watchlistSearchSuggestions.classList.add('hidden');

    } catch (error) {
        console.error('Error adding to watchlist:', error);
        showError('Failed to add security to watchlist');
    }
}

function renderWatchlistItems(data = null) {
    if (data) {
        watchlistItems = data;
    }

    const watchlistContainer = document.querySelector('.watchlist-securities');
    watchlistContainer.innerHTML = '';

    if (watchlistItems.length === 0) {
        watchlistContainer.innerHTML = '<div class="empty-watchlist">No securities in watchlist</div>';
        return;
    }

    watchlistItems.forEach(item => {
        const card = document.createElement('div');
        card.className = 'watchlist-card';

        const dayChangeClass = item.day_change >= 0 ? 'positive' : 'negative';

        card.innerHTML = `
        <div class="watchlist-card-header">
            <div class="security-info">
                <h4 class="security-symbol">${item.ticker}</h4>
                <p class="security-name">${item.name}</p>
                <p class="security-exchange">${item.exchange || 'NYSE'}</p>
            </div>
            <div class="security-prices">
                <p class="current-price">${formatCurrency(item.current_price || 0)}</p>
                <span class="day-change ${item.day_change >= 0 ? 'positive' : 'negative'}">
                    ${item.day_change >= 0 ? '+' : ''}${formatCurrency(item.day_change || 0)}
                    (${(item.day_change_pct || 0).toFixed(2)}%)
                </span>
            </div>
        </div>
        <div class="watchlist-card-actions">
            <button class="toggle-chart-btn" data-symbol="${item.ticker}">
                <img src="/static/images/chevron-down.svg" alt="Toggle chart" class="chevron-icon">
            </button>
            <button class="remove-security-btn" data-symbol="${item.ticker}">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="chart-container hidden" id="chart-${item.ticker}"></div>
    `;

        watchlistContainer.appendChild(card);

        // Add event listeners
        const toggleBtn = card.querySelector('.toggle-chart-btn');
        const removeBtn = card.querySelector('.remove-security-btn');
        const chartContainer = card.querySelector('.chart-container');

        toggleBtn.addEventListener('click', () => {
            const chevron = toggleBtn.querySelector('.chevron-icon');
            chartContainer.classList.toggle('hidden');
            chevron.style.transform = chartContainer.classList.contains('hidden') ?
                'rotate(0deg)' : 'rotate(180deg)';

            if (!chartContainer.classList.contains('hidden')) {
                renderWatchlistChart(item.ticker, chartContainer);
            }
        });

        removeBtn.addEventListener('click', async () => {
            try {

                const csrfToken = document.cookie
                    .split('; ')
                    .find(row => row.startsWith('csrf_access_token='))
                    ?.split('=')[1];

                const response = await fetch(`/auth/watchlist/${item.id}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': csrfToken
                    },
                    credentials: 'include'
                });

                if (response.ok) {
                    watchlistItems = watchlistItems.filter(security => security.id !== item.id);
                    renderWatchlistItems();
                } else {
                    throw new Error('Failed to remove from watchlist');
                }
            } catch (error) {
                showError('Failed to remove from watchlist');
            }
        });
    });
}

async function renderWatchlistChart(symbol, container) {
    try {
        // If we don't have the data already stored in the hist table, fetch it from AV
        if (!watchlistStockData[symbol]) {
            const historicalResponse = await fetch(`/auth/security-historical/${symbol}`, {
                credentials: 'include'
            });

            if (historicalResponse.ok) {
                const priceData = await historicalResponse.json();
                watchlistStockData[symbol] = {
                    dates: priceData.dates,
                    prices: priceData.prices
                };
            } else {
                throw new Error('Failed to fetch historical data');
            }
        }

        const data = watchlistStockData[symbol];
        if (!data) return;

        const chartConfig = {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{
                    label: `${symbol} Closing Prices`,
                    data: data.prices,
                    borderColor: 'rgba(108, 125, 147, 1)',
                    borderWidth: 2,
                    fill: true,
                    backgroundColor: function(context) {
                        const chart = context.chart;
                        const { ctx, chartArea } = chart;
                        if (!chartArea) return null;

                        const gradient = ctx.createLinearGradient(
                            0,
                            chart.scales.y.getPixelForValue(Math.max(...data.prices)),
                            0,
                            chart.chartArea.bottom
                        );
                        gradient.addColorStop(0, 'rgba(108, 125, 147, 0.8)');
                        gradient.addColorStop(1, 'rgba(108, 125, 147, 0.1)');
                        return gradient;
                    },
                    pointRadius: 2,
                    pointHoverRadius: 4,
                    pointBackgroundColor: 'rgba(108, 125, 147, 1)',
                    tension: 0.2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        intersect: false,
                        mode: 'index',
                    },
                },
                scales: {
                    x: { title: { display: true, text: 'Date' } },
                    y: { title: { display: true, text: 'Price (USD)' } }
                },
                interaction: {
                    intersect: false,
                    mode: 'nearest'
                }
            }
        };

        const canvas = document.createElement('canvas');
        canvas.style.height = '250px';
        container.innerHTML = '';
        container.appendChild(canvas);

        new Chart(canvas, chartConfig);
    } catch (error) {
        console.error('Error rendering watchlist chart:', error);
        container.innerHTML = '<div class="chart-error">Failed to load chart data</div>';
    }
}


// Initialize
    async function init() {
        try {
            // Load securities data
            const response = await fetch("/static/data/symbols.json");
            if (!response.ok) throw new Error("Failed to load securities data");
            securitiesData = await response.json();

            // Get watchlist data from the embedded script
            const watchlistDataElement = document.getElementById('watchlist-data');
            if (watchlistDataElement) {
                try {
                    const watchlistData = JSON.parse(watchlistDataElement.textContent);
                    console.log("Initial watchlist data:", watchlistData);
                    renderWatchlistItems(watchlistData);
                } catch (e) {
                    console.error('Error parsing watchlist data:', e);
                    renderWatchlistItems([]);
                }
            } else {
                console.log("No watchlist data element found");
                renderWatchlistItems([]);
            }


            // Setup all event handlers
            setupEventListeners();
            setupWatchlistHandlers();
            elements.tableHeader.style.display = "none";

        } catch (error) {
            console.error("Initialization error:", error);
            elements.errorMessage.textContent = "Failed to initialize application";
            elements.errorModal.style.display = "block";
        }
    }

// Metrics are now automatically recalculated when prices are updated
// No separate recalculation function is needed

// Start the application when DOM is ready
    // document.addEventListener("DOMContentLoaded", init);

document.addEventListener("DOMContentLoaded", () => {
    init().catch(error => {
        console.error("Error during initialization:", error);
        elements.errorMessage.textContent = "Failed to initialize application";
        elements.errorModal.style.display = "block";
    });
    
    // Metrics are now automatically recalculated when prices are updated
});