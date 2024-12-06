document.addEventListener("DOMContentLoaded", async () => {
    const portfolioList = document.getElementById("portfolio-list");

    try {
        const response = await fetch("/auth/portfolio-overview", {
            method: "GET",
            headers: {
                "Content-Type": "application/json",
            },
        });

        if (response.ok) {
            const portfolios = await response.json();
            if (portfolios.length === 0) {
                portfolioList.innerHTML = "<p>You have no portfolios yet.</p>";
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
        } else {
            portfolioList.innerHTML = "<p>Error loading portfolios.</p>";
        }
    } catch (error) {
        console.error("Error fetching portfolios:", error);
        portfolioList.innerHTML = "<p>Error loading portfolios.</p>";
    }
});

async function deletePortfolio(portfolioId) {
    try {
        const response = await fetch(`/auth/portfolio/${portfolioId}`, {
            method: "DELETE",
        });

        if (response.ok) {
            alert("Portfolio deleted successfully.");
            location.reload(); // Refresh the page
        } else {
            alert("Error deleting portfolio.");
        }
    } catch (error) {
        console.error("Error deleting portfolio:", error);
    }
}

function viewPortfolio(portfolioId) {
    // Redirect to the dashboard with the selected portfolio
    window.location.href = `/auth/dashboard?portfolioId=${portfolioId}`;
}

document.addEventListener("click", (event) => {
    const target = event.target;

    // Handle delete button click
    if (target.classList.contains("delete-file-btn")) {
        const fileId = target.dataset.fileId;
        if (confirm("Are you sure you want to delete this file?")) {
            fetch(`/auth/delete-file/${fileId}`, {
                method: "POST",
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.message) {
                        alert(data.message);
                        location.reload(); // Refresh the page
                    }
                })
                .catch((error) => {
                    console.error("Error deleting file:", error);
                    alert("An unexpected error occurred. Please try again.");
                });
        }
    }

    // Handle edit button click
    if (target.classList.contains("edit-file-btn")) {
        const fileId = target.dataset.fileId;
        alert(`Edit functionality for file ID: ${fileId} is not implemented yet.`);
    }
});

// File upload logic
document.querySelector(".new-file-btn").addEventListener("click", () => {
    const fileInput = document.getElementById("fileInput");
    fileInput.click(); // Simulate file input click
});

document.getElementById("fileInput").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) {
        alert("No file selected.");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    const csrfToken = document.cookie
        .split("; ")
        .find((row) => row.startsWith("csrf_access_token="))
        ?.split("=")[1];

    if (!csrfToken) {
        console.error("CSRF token not found in cookies");
        alert("An error occurred. Please log in again.");
        return;
}

    try {
        const response = await fetch("/auth/upload", {
            method: "POST",
            body: formData,
            credentials: "include", // Ensure the JWT cookie is sent
            headers: {
                "X-CSRF-TOKEN": csrfToken, // Add CSRF token to the header
            },
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message); // Notify the user
            location.reload(); // Refresh to show uploaded files
        } else {
            const error = await response.json();
            console.error("Error uploading file:", error);
            alert(`Error uploading file: ${error.message}`);
        }
    } catch (error) {
        console.error("Error uploading file:", error);
        alert("An unexpected error occurred. Please try again.");
    }
});

document.addEventListener("DOMContentLoaded", () => {
    const newPortfolioModal = document.getElementById("newPortfolioModal");
    const closeModal = document.getElementById("closeModal");
    const manualPortfolioSection = document.getElementById("manualPortfolioSection");
    const uploadPortfolioSection = document.getElementById("uploadPortfolioSection");
    const manualPortfolioTable = document.getElementById("manualPortfolioTable").querySelector("tbody");
    const searchStockInput = document.getElementById("searchStockInput");

    const manualPortfolio = [];

    // Open modal
    document.querySelector(".new-portfolio-btn").addEventListener("click", () => {
        newPortfolioModal.style.display = "block";
    });

    // Close modal
    closeModal.addEventListener("click", () => {
        newPortfolioModal.style.display = "none";
        resetModal();
    });

    // Show manual section
    document.querySelector(".manual-portfolio-btn").addEventListener("click", () => {
        manualPortfolioSection.classList.remove("hidden");
        uploadPortfolioSection.classList.add("hidden");
    });

    // Show upload section
    document.querySelector(".upload-portfolio-btn").addEventListener("click", () => {
        uploadPortfolioSection.classList.remove("hidden");
        manualPortfolioSection.classList.add("hidden");
    });

    // Search and add stock
    document.getElementById("addStockBtn").addEventListener("click", async () => {
        const ticker = searchStockInput.value.trim();
        if (!ticker) return alert("Please enter a stock ticker.");

        try {
            const response = await fetch(`/auth/stock-data?ticker=${ticker}`);
            if (response.ok) {
                const stockData = await response.json();
                addStockToTable(stockData);
            } else {
                alert("Stock not found. Please try again.");
            }
        } catch (error) {
            console.error("Error fetching stock data:", error);
            alert("An error occurred. Please try again.");
        }
    });

    // Add stock to table
    function addStockToTable(stock) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${stock.ticker}</td>
            <td>${stock.name}</td>
            <td>${stock.industry}</td>
            <td><input type="number" class="amount-owned" placeholder="0"></td>
            <td>${stock.valueChangeDay}</td>
            <td>${stock.totalGainLoss1Y}</td>
            <td><button class="remove-stock-btn">Remove</button></td>
        `;
        manualPortfolioTable.appendChild(row);

        row.querySelector(".remove-stock-btn").addEventListener("click", () => {
            row.remove();
        });

        // Add stock to portfolio array
        manualPortfolio.push(stock);
    }

    // Finish manual portfolio creation
    document.getElementById("finishManualPortfolioBtn").addEventListener("click", async () => {
        try {
            const portfolioName = prompt("Enter a name for your portfolio:");
            if (!portfolioName) return alert("Portfolio name is required.");

            const data = {
                name: portfolioName,
                stocks: manualPortfolio.map((stock, index) => ({
                    ticker: stock.ticker,
                    name: stock.name,
                    industry: stock.industry,
                    amount: parseFloat(
                        manualPortfolioTable.rows[index].querySelector(".amount-owned").value
                    ) || 0,
                })),
            };

            const response = await fetch("/auth/create-portfolio", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(data),
            });

            if (response.ok) {
                alert("Portfolio created successfully!");
                location.reload(); // Refresh to show new portfolio
            } else {
                const error = await response.json();
                alert(`Error creating portfolio: ${error.message}`);
            }
        } catch (error) {
            console.error("Error creating portfolio:", error);
            alert("An unexpected error occurred.");
        }
    });

    // Reset modal
    function resetModal() {
        manualPortfolioTable.innerHTML = ""; // Clear manual portfolio table
        searchStockInput.value = ""; // Clear search input
        manualPortfolio.length = 0; // Clear portfolio array
    }
});


