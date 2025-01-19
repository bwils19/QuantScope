document.addEventListener("DOMContentLoaded", async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const portfolioId = urlParams.get("portfolio_id");

    if (!portfolioId) {
        alert("Portfolio ID not provided!");
        return;
    }

    try {
        // Fetch portfolio data
        const response = await fetch(`/auth/api/portfolio/${portfolioId}/risk`);
        if (!response.ok) throw new Error("Failed to fetch portfolio data");

        const portfolioData = await response.json();
        populatePage(portfolioData);
    } catch (error) {
        console.error("Error loading risk analysis:", error);
    }
});

function populatePage(data) {
    // Populate metrics
    document.getElementById("totalValue").textContent = `$${data.total_value.toFixed(2)}`;
    document.getElementById("varValue").textContent = `${data.var.toFixed(2)}%`;
    document.getElementById("betaValue").textContent = `${data.beta.toFixed(2)}`;

    // Render charts (placeholder for now)
    const chartsContainer = document.getElementById("charts-container");
    chartsContainer.innerHTML = `<p>Charts will be displayed here.</p>`;
}
