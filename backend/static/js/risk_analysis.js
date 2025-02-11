// static/js/risk_analysis.js

let compositionChart = null;
const portfolioId = new URLSearchParams(window.location.search).get('portfolio_id');

document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const portfolioId = urlParams.get('portfolio_id');
    
    try {
        const response = await fetch(`/analytics/portfolio/${portfolioId}/risk`);
        const data = await response.json();
        console.log("Risk Data API Response:", data);
        if (!response.ok) throw new Error(data.error || 'Failed to fetch risk data');
        
        renderRiskDashboard(data);
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to load risk analysis');
    }
});

function renderRiskDashboard(data) {
    // Render top metrics
    document.getElementById('totalValue').textContent = formatCurrency(data.total_value);
    document.getElementById('portfolioBeta').textContent = data.beta.toFixed(2);
    document.getElementById('portfolioVar').textContent = formatCurrency(Math.abs(data.var_metrics.var_normal));

    // Render VaR distribution chart
    renderVarChart(data.var_metrics);
    
    // Render component risk heatmap
    renderRiskHeatmap(data.var_components);
    
    // Render regime distribution donut
    renderRegimeChart(data.var_metrics.regime_distribution);
}

function renderVarChart(varData) {
    const ctx = document.getElementById('varChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Normal VaR', 'Stress VaR', 'Expected Shortfall'],
            datasets: [{
                data: [
                    Math.abs(varData.var_normal),
                    Math.abs(varData.var_stress),
                    Math.abs(varData.cvar)
                ],
                backgroundColor: ['#3498db', '#e74c3c', '#9b59b6'],
                borderRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => formatCurrency(context.raw)
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: (value) => formatCurrency(value)
                    }
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    showVarDetails(elements[0].index, varData);
                }
            }
        }
    });
}

function renderRiskHeatmap(components) {
    const ctx = document.getElementById('riskHeatmap').getContext('2d');
    const maxContribution = Math.max(...components.map(c => Math.abs(c.var_contribution)));
    
    new Chart(ctx, {
        type: 'bubble',
        data: {
            datasets: [{
                data: components.map(c => ({
                    x: c.volatility,
                    y: Math.abs(c.var_contribution),
                    r: (c.weight / maxContribution) * 20,
                    ticker: c.ticker
                })),
                backgroundColor: components.map(c => 
                    `rgba(52, 152, 219, ${Math.abs(c.var_contribution) / maxContribution})`
                )
            }]
        },
        options: {
            responsive: true,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const data = context.raw;
                            return [
                                `Ticker: ${data.ticker}`,
                                `VaR Contribution: ${formatCurrency(data.y)}`,
                                `Volatility: ${data.x.toFixed(2)}%`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Volatility (%)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'VaR Contribution ($)'
                    },
                    ticks: {
                        callback: (value) => formatCurrency(value)
                    }
                }
            }
        }
    });
}

function renderRegimeChart(regimeData) {
    const ctx = document.getElementById('regimeChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Normal Market', 'Stress Market'],
            datasets: [{
                data: [
                    regimeData.normal * 100,
                    regimeData.stress * 100
                ],
                backgroundColor: ['#2ecc71', '#e74c3c']
            }]
        },
        options: {
            responsive: true,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.label}: ${context.raw.toFixed(1)}%`
                    }
                }
            }
        }
    });
}

function showVarDetails(index, varData) {
    const modalContent = document.getElementById('varDetailsContent');
    const types = ['Normal Market', 'Stress Market', 'Expected Shortfall'];
    const values = [varData.var_normal, varData.var_stress, varData.cvar];
    
    modalContent.innerHTML = `
        <h3>${types[index]} Details</h3>
        <div class="details-grid">
            <div class="detail-item">
                <span class="label">Value at Risk</span>
                <span class="value">${formatCurrency(Math.abs(values[index]))}</span>
            </div>
            <div class="detail-item">
                <span class="label">Confidence Level</span>
                <span class="value">95%</span>
            </div>
            <div class="detail-item">
                <span class="label">Time Horizon</span>
                <span class="value">10 Days</span>
            </div>
        </div>
    `;
    
    document.getElementById('varDetailsModal').style.display = 'block';
}

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    document.querySelector('.risk-analysis-container').prepend(errorDiv);
}

async function initializeCompositionChart() {
    try {
        console.log('Initializing composition chart for portfolio:', portfolioId);  // Debug log

        // First check if the canvas element exists
        const canvas = document.getElementById('compositionDonut');
        if (!canvas) {
            console.error('Composition donut canvas not found');
            return;
        }

        // Get the portfolio ID from the URL
        if (!portfolioId) {
            console.error('No portfolio ID found in URL');
            return;
        }

        // Fetch initial composition data
        const response = await fetch(`/auth/api/portfolio-composition/sector?portfolio_id=${portfolioId}`);
        console.log('API Response status:', response.status);  // Debug log

        if (!response.ok) {
            const text = await response.text();
            console.error('API Error response:', text);  // Debug log
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Composition data:', data);  // Debug log

        // Create the chart
        const ctx = canvas.getContext('2d');
        compositionChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels || [],
                datasets: [{
                    data: data.values || [],
                    backgroundColor: [
                        '#2c3e50', '#34495e', '#6C7D93', '#95a5a6',
                        '#3498db', '#2980b9', '#1abc9c', '#16a085',
                        '#27ae60', '#2ecc71', '#f1c40f', '#f39c12'
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                return `${label}: ${value.toFixed(2)}%`;
                            }
                        }
                    }
                }
            }
        });

        // Update legend
        updateLegend(data);

    } catch (error) {
        console.error('Failed to initialize composition chart:', error);
    }
}

// Update the legend
function updateLegend(data) {
    const legend = document.getElementById('compositionLegend');
    if (!legend) return;

    legend.innerHTML = data.labels.map((label, index) => `
        <div class="legend-item">
            <span class="color-box" style="background-color: ${compositionChart.data.datasets[0].backgroundColor[index]}"></span>
            <span class="label">${label}</span>
            <span class="value">${data.values[index].toFixed(2)}%</span>
        </div>
    `).join('');
}

// Handle view changes
function setupViewSelector() {
    const selector = document.getElementById('compositionView');
    if (!selector) return;

    selector.addEventListener('change', async (e) => {
        const viewType = e.target.value;
        try {
            const response = await fetch(`/api/portfolio-composition/${viewType}?portfolio_id=${portfolioId}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Update chart data
            compositionChart.data.labels = data.labels;
            compositionChart.data.datasets[0].data = data.values;
            compositionChart.update();

            // Update legend
            updateLegend(data);
        } catch (error) {
            console.error('Failed to update composition view:', error);
        }
    });
}

// Initialize everything when the document is ready
document.addEventListener('DOMContentLoaded', () => {
    initializeCompositionChart();
    setupViewSelector();
});