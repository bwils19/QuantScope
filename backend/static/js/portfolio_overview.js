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

    try {
        const response = await fetch("/auth/upload", {
            method: "POST",
            body: formData,
            credentials: "include", // Ensure the JWT cookie is sent
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
