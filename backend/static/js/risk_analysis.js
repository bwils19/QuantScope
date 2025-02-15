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
    // Portfolio Value with 24h change
    document.getElementById('totalValue').textContent = formatCurrency(data.total_value);
    const changeValue = document.querySelector('.change-value');
    if (data.value_change_24h) {
        const changePercent = data.value_change_24h.toFixed(2);
        changeValue.textContent = `${changePercent > 0 ? '+' : ''}${changePercent}%`;
        changeValue.classList.add(changePercent > 0 ? 'positive' : 'negative');
    }

    // add the timestamp to the portfolio value card
    if (data.latest_update) {
        document.getElementById('portfolioTimestamp').textContent =
            `Latest Update: ${data.latest_update}`;
    }

    // Add timestamp to page footer
    if (data.latest_update) {
        document.getElementById('pageTimestamp').textContent =
            `Data as of: ${data.latest_update}`;
    }

    // VaR with percentage context
    document.getElementById('portfolioVar').textContent = formatCurrency(Math.abs(data.var_metrics.var_normal));
    const varPercent = (Math.abs(data.var_metrics.var_normal) / data.total_value * 100).toFixed(2);
    document.getElementById('varPercent').textContent = `${varPercent}%`;

    // Stress VaR with confidence level
    document.getElementById('stressVar').textContent = formatCurrency(Math.abs(data.var_metrics.var_stress));
    document.getElementById('stressConfidence').textContent = '99%';  // Or fetch from data if variable

    // Portfolio Beta with rolling period
    document.getElementById('portfolioBeta').textContent = data.beta.toFixed(2);

    // Render existing charts
    renderVarChart(data.var_metrics);
    renderRiskHeatmap(data.var_components);
    renderRegimeChart(data.var_metrics.regime_distribution);
}

const chartPalette = {
    // Core blues for main visualizations
     blues: [
        '#264653',  // Dark slate
        '#2A6F97',  // Deep blue
        '#2E8BC0',  // Ocean blue
        '#3498DB',  // Bright blue
        '#5B63B7',  // Blue violet
        '#826FBA',  // Purple blue
        '#A17EB3',  // Light purple
        '#C490AC'   // Pale rose
    ],

    // Primary colors for main data visualization
    primary: {
        navy: '#2c3e50',      // Dark navy - primary
        blue: '#34495e',      // Medium blue
        grey: '#6C7D93',      // Professional grey
        lightGrey: '#95a5a6'  // Light grey
    },

    // Secondary colors for contrasting data points
    secondary: {
        deepBlue: '#2980b9',    // Deep blue for important metrics
        teal: '#1abc9c',        // Teal for secondary metrics
        slate: '#7f8c8d',       // Slate for tertiary data
        charcoal: '#2c3e50'     // Charcoal for text/labels
    },

    // Risk-specific colors
    risk: {
        normal: '#3498db',      // Primary blue for normal VaR
        stress: '#2C3E50',      // Dark navy for stress VaR
        expected: '#4B77BE'     // Medium blue for expected shortfall
    },

    // market regime data
    regime: {
        normal: '#3498db',      // Primary blue for normal market
        stress: '#6C7D93'       // Blue grey for stress market
    },

    // Accent colors
    accent: {
        highlight: '#4b7bec',   // Bright blue for highlights
        warning: '#fed330',     // Muted yellow for warnings
        danger: '#fc5c65'       // Controlled red for danger (keep for actual warnings)
    },

    // Background colors
    background: {
        card: '#ffffff',        // White for card backgrounds
        main: '#f5f6fa',       // Light grey for main background
        hover: '#fafbfc'       // Slight grey for hover states
    }
};

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
                backgroundColor: [
                    chartPalette.risk.normal,
                    chartPalette.risk.stress,
                    chartPalette.risk.expected
                ],
                borderRadius: 5,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    titleColor: '#2c3e50',
                    bodyColor: '#2c3e50',
                    borderColor: '#e2e8f0',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: (context) => formatCurrency(context.raw)
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        drawBorder: false,
                        color: '#e2e8f0'
                    },
                    ticks: {
                        callback: (value) => formatCurrency(value),
                        font: {
                            family: 'Arial',
                            size: 12
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        font: {
                            family: 'Arial',
                            size: 12
                        }
                    }
                }
            }
        }
    });
}

function renderRiskHeatmap(components) {
    const ctx = document.getElementById('riskHeatmap');
    if (!ctx) {
        console.error('Risk heatmap canvas not found');
        return;
    }

    // Get the context and ensure it exists
    const context = ctx.getContext('2d');
    if (!context) {
        console.error('Could not get 2d context for risk heatmap');
        return;
    }

    // Calculate max values for scaling
    const maxContribution = Math.max(...components.map(c => Math.abs(c.var_contribution)));

    new Chart(context, {
        type: 'bubble',
        data: {
            datasets: [{
                data: components.map(c => ({
                    x: c.volatility,
                    y: Math.abs(c.var_contribution),
                    r: (c.weight * 50) + 5, // Scale the radius, min size 5
                    ticker: c.ticker
                })),
                backgroundColor: components.map(c =>
                    `rgba(52, 152, 219, ${Math.abs(c.var_contribution) / maxContribution})`
                ),
                borderColor: 'rgba(52, 152, 219, 0.8)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Volatility (%)',
                        font: {
                            size: 12,
                            weight: 'bold'
                        }
                    },
                    ticks: {
                        callback: value => value.toFixed(2) + '%'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'VaR Contribution ($)',
                        font: {
                            size: 12,
                            weight: 'bold'
                        }
                    },
                    ticks: {
                        callback: value => formatCurrency(value)
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const data = context.raw;
                            return [
                                `Ticker: ${data.ticker}`,
                                `VaR Contribution: ${formatCurrency(data.y)}`,
                                `Volatility: ${data.x.toFixed(2)}%`,
                                `Portfolio Weight: ${(data.r / 50 * 100).toFixed(2)}%`
                            ];
                        }
                    }
                },
                legend: {
                    display: false
                }
            }
        }
    });
}

function renderRegimeChart(regimeData) {
    const ctx = document.getElementById('regimeChart').getContext('2d');
    
    const regimeChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Normal Market', 'Stress Market'],
            datasets: [{
                data: [
                    regimeData.normal * 100,
                    regimeData.stress * 100
                ],
                backgroundColor: [
                    '#2c3e50',  // Dark navy for normal market
                    '#6C7D93'   // Professional grey for stress market
                ],
                borderWidth: 0,
                cutout: '70%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    titleColor: '#2c3e50',
                    bodyColor: '#2c3e50',
                    borderColor: '#e2e8f0',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: (context) => `${context.label}: ${context.raw.toFixed(1)}%`
                    }
                }
            }
        }
    });

    // Create custom legend to match portfolio composition style
    const legendContainer = document.getElementById('regimeLegend');
    if (legendContainer) {
        legendContainer.innerHTML = regimeChart.data.labels.map((label, index) => `
            <div class="legend-item">
                <span class="color-box" style="background-color: ${regimeChart.data.datasets[0].backgroundColor[index]}"></span>
                <div class="legend-text">
                    <span class="label">${label}</span>
                    <span class="value">${regimeChart.data.datasets[0].data[index].toFixed(1)}%</span>
                </div>
            </div>
        `).join('');
    }
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
        console.log('API Response status:', response.status);

        if (!response.ok) {
            const text = await response.text();
            console.error('API Error response:', text);
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Composition data:', data);

        const ctx = document.getElementById('compositionDonut').getContext('2d');
        compositionChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: chartPalette.blues.slice(0, data.labels.length),
                    borderWidth: 0,
                    cutout: '70%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: chartPalette.background.card,
                        titleColor: chartPalette.primary.navy,
                        bodyColor: chartPalette.primary.navy,
                        borderColor: chartPalette.primary.lightGrey,
                        borderWidth: 1,
                        padding: 10,
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

// i want to keep these color palettes here in case is start to hate the one i chose haha

// const sectorColors = [
//     '#264653',  // Dark slate
//     '#2A6F97',  // Deep blue
//     '#2E8BC0',  // Ocean blue
//     '#3498DB',  // Bright blue
//     '#5B63B7',  // Blue violet
//     '#826FBA',  // Purple blue
//     '#A17EB3',  // Light purple
//     '#C490AC'   // Pale rose
// ];

// const sectorColors = [
//     '#1F4788',  // Deep navy
//     '#2E5EA6',  // Royal blue
//     '#3E75C4',  // Medium blue
//     '#4E8BE2',  // Bright blue
//     '#6BA3E8',  // Light blue
//     '#88BCED',  // Pale blue
//     '#A5D5F2',  // Ice blue
//     '#C2E1F5'   // Very light blue
// ];
//
// const sectorColors = [
//     '#2C7FB8',  // Deep blue
//     '#4BA4D1',  // Bright blue
//     '#7FCDBB',  // Blue-green
//     '#A6DBA0',  // Light teal
//     '#D9F0D3',  // Pale teal
//     '#1B4F72',  // Navy
//     '#5499C7',  // Medium blue
//     '#85C1E9'   // Light blue
// ];

// Update the legend
function updateLegend(data) {
    const legend = document.getElementById('compositionLegend');
    if (!legend) return;

    legend.innerHTML = data.labels.map((label, index) => `
        <div class="legend-item">
            <span class="color-box" style="background-color: ${compositionChart.data.datasets[0].backgroundColor[index]}"></span>
            <div class="legend-text">
                <span class="label">${label}</span>
                <span class="value">${data.values[index].toFixed(2)}%</span>
            </div>
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