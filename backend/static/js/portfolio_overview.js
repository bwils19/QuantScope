document.addEventListener("DOMContentLoaded", async () => {
    const portfolioList = document.getElementById("portfolio-list");

    try {
        const response = await fetch("/auth/portfolio-overview", {
            method: "GET",
            headers: {
                "Content-Type": "application/json",
            },
        });

        if (response.status === 200) {
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

        if (response.status === 200) {
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
