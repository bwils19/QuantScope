// static/js/risk_analysis.js

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