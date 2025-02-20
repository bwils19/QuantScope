let compositionChart = null;
let betaChart = null;
let varChart = null;
let riskHeatmapChart = null;
let regimeChart = null;
let loadingTimeout = null;
const portfolioId = new URLSearchParams(window.location.search).get('portfolio_id');

document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const portfolioId = urlParams.get('portfolio_id');
    const chartCard = document.querySelector('.chart-card');
    let loadingTimeout;

    if (!chartCard) {
        console.error('Chart card container not found');
        return;
    }

    try {
        loadingTimeout = await showLoading(chartCard, 'Loading Portfolio Risk Analysis...', 0);

        const response = await fetch(`/analytics/portfolio/${portfolioId}/risk`);
        const data = await response.json();
        console.log("Risk Data API Response:", data);

        if (!response.ok) {
            throw new Error(data.error || 'Failed to fetch risk data');
        }

        // Render the dashboard
        await renderRiskDashboard(data);

    } catch (error) {
        console.error('Error:', error);
        showError('Failed to load risk analysis');
    } finally {
        // Always ensure loading state is removed
        hideLoading(chartCard, loadingTimeout);
    }
});

function showLoading(container, message = 'Loading...', delay = 300) {
    let loadingTimeout = null;

    return new Promise((resolve) => {
        loadingTimeout = setTimeout(() => {
            container.classList.add('loading');
            const loadingState = document.createElement('div');
            loadingState.className = 'loading-state';
            loadingState.innerHTML = `
                <div class="loading-spinner"></div>
                <div class="loading-text">${message}</div>
            `;
            container.appendChild(loadingState);
        }, delay);

        resolve(loadingTimeout);
    });
}

function hideLoading(container, timeout) {
    console.log('Hiding loading state...');
    if (timeout) {
        console.log('Clearing timeout...');
        clearTimeout(timeout);
    }
    console.log('Removing loading class...');
    container.classList.remove('loading');
    const loadingState = container.querySelector('.loading-state');
    if (loadingState) {
        console.log('Removing loading state element...');
        loadingState.remove();
    }
    console.log('Loading state removed.');
}

async function renderRiskDashboard(data) {
    console.log('Starting dashboard render with data:', data);
    console.log('Full API Response:', data);
    console.log('Beta data:', data.beta);

    try {
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
        if (data.var_metrics) {
            document.getElementById('portfolioVar').textContent = formatCurrency(Math.abs(data.var_metrics.var_normal));
            const varPercent = (Math.abs(data.var_metrics.var_normal) / data.total_value * 100).toFixed(2);
            document.getElementById('varPercent').textContent = `${varPercent}%`;
            renderVarChart(data.var_metrics);
        } else {
            console.error('Missing VaR metrics data');
        }

        // Stress VaR with confidence level
        if (data.var_metrics) {
            document.getElementById('stressVar').textContent = formatCurrency(Math.abs(data.var_metrics.var_stress));
            document.getElementById('stressConfidence').textContent = '99%';
        }

        // Portfolio Beta with rolling period
        if (data.beta && typeof data.beta === 'object') {
            console.log('Rendering beta chart with data:', data.beta);
            document.getElementById('portfolioBeta').textContent = data.beta.beta.toFixed(2);
            renderBetaChart(data.beta);
        } else {
            console.error('Invalid or missing beta data:', data.beta);
        }

        // Render other charts with validation
        if (data.var_components) {
            renderRiskHeatmap(data.var_components);
        } else {
            console.error('Missing risk components data');
        }

        if (data.var_metrics?.regime_distribution) {
            renderRegimeChart(data.var_metrics.regime_distribution);
        } else {
            console.error('Missing regime distribution data');
        }

        await initializeCompositionChart();
        setupViewSelector();

        console.log('Dashboard render complete.');

    } catch (error) {
        console.error('Error rendering dashboard:', error);
    }
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
    const canvas = document.getElementById('varChart');
    if (!canvas) return;

    if (varChart) {
        varChart.destroy();
        varChart = null;
    }
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
    const canvas = document.getElementById('riskHeatmap');
    if (!canvas) return;

    if (riskHeatmapChart) {
        riskHeatmapChart.destroy();
        riskHeatmapChart = null;
    }
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
    const canvas = document.getElementById('regimeChart');
    if (!canvas) return;

    if (regimeChart) {
        regimeChart.destroy();
        regimeChart = null;
    }
    const ctx = document.getElementById('regimeChart').getContext('2d');
    
    regimeChart = new Chart(ctx, {
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

function renderBetaChart(betaData) {
    console.log('Beta data received:', betaData);
    console.log('Rolling betas:', betaData.rolling_betas);
    console.log('Confidence intervals:', betaData.confidence);

    if (betaChart) {
        betaChart.destroy();
        betaChart = null;
    }
    const ctx = document.getElementById('betaChart').getContext('2d');

    // Create gradient for confidence interval
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(52, 152, 219, 0.1)');
    gradient.addColorStop(1, 'rgba(52, 152, 219, 0.02)');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array(betaData.rolling_betas.length).fill('').map((_, i) =>
                `Day ${i + 1}`
            ),
            datasets: [{
                label: 'Rolling Beta',
                data: betaData.rolling_betas,
                borderColor: chartPalette.primary.navy,
                borderWidth: 2,
                fill: false,
                tension: 0.4
            }, {
                label: 'Confidence Interval',
                data: Array(betaData.rolling_betas.length).fill(betaData.confidence.high),
                borderColor: 'rgba(52, 152, 219, 0.3)',
                borderWidth: 1,
                fill: '+1',
                tension: 0.4
            }, {
                label: 'Confidence Interval',
                data: Array(betaData.rolling_betas.length).fill(betaData.confidence.low),
                borderColor: 'rgba(52, 152, 219, 0.3)',
                borderWidth: 1,
                fill: false,
                tension: 0.4,
                backgroundColor: gradient
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
                        label: (context) => `Beta: ${context.raw.toFixed(2)}`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        drawBorder: false,
                        color: '#e2e8f0'
                    },
                    ticks: {
                        callback: value => value.toFixed(2),
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
                        display: false
                    }
                }
            }
        }
    });

    // Update beta metrics card
    document.getElementById('portfolioBeta').textContent = betaData.beta.toFixed(2);

    // Add additional beta metrics to the card
    const betaContext = document.querySelector('.beta-metrics');
    if (betaContext) {
        betaContext.innerHTML = `
                <div class="beta-metric">
                    <span class="label">R²:</span>
                    <span class="value">${(betaData.r_squared * 100).toFixed(1)}%</span>
                </div>
                <div class="beta-metric">
                    <span class="label">Downside β:</span>
                    <span class="value">${betaData.downside_beta.toFixed(2)}</span>
                </div>
            `;
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

async function initializeCompositionChart() {
    try {
        console.log('Initializing composition chart for portfolio:', portfolioId);

        const canvas = document.getElementById('compositionDonut');
        if (!canvas) {
            console.error('Composition donut canvas not found');
            return;
        }

        if (!portfolioId) {
            console.error('No portfolio ID found in URL');
            return;
        }

        // Destroy existing chart if it exists
        if (compositionChart) {
            console.log('Destroying existing chart...');
            compositionChart.destroy();
            compositionChart = null;
        }

        // Get initial view type from select element
        const viewSelector = document.getElementById('compositionView');
        const initialViewType = viewSelector ? viewSelector.value : 'sector';

        const response = await fetch(`/analytics/portfolio/${portfolioId}/composition/${initialViewType}`);
        console.log('API Response status:', response.status);

        if (!response.ok) {
            const text = await response.text();
            console.error('API Error response:', text);
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Composition data:', data);

        const ctx = canvas.getContext('2d');
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
        showError('Failed to load portfolio composition data');
        // Make sure to clean up if initialization fails
        if (compositionChart) {
            compositionChart.destroy();
            compositionChart = null;
        }
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

    legend.innerHTML = data.labels.map((label, index) => {
        const value = data.values[index];
        const backgroundColor = compositionChart.data.datasets[0].backgroundColor[index];

        return `
            <div class="legend-item">
                <span class="color-box" style="background-color: ${backgroundColor}"></span>
                <div class="legend-text">
                    <span class="label">${label || 'Unknown'}</span>
                    <span class="value">${value.toFixed(2)}%</span>
                </div>
            </div>
        `;
    }).join('');
}


// Handle view changes
function setupViewSelector() {
    const selector = document.getElementById('compositionView');
    if (!selector) return;

    selector.addEventListener('change', async (e) => {
        const viewType = e.target.value;
        const chartCard = document.querySelector('.chart-card');
        let loadingTimeout;

        try {
            const message = `Loading ${viewType === 'risk' ? 'Risk Distribution' : 
                           viewType.charAt(0).toUpperCase() + viewType.slice(1) + ' Distribution'}...`;

            loadingTimeout = await showLoading(chartCard, message);

            const response = await fetch(`/analytics/portfolio/${portfolioId}/composition/${viewType}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Update chart data
            compositionChart.data.labels = data.labels;
            compositionChart.data.datasets[0].data = data.values;
            compositionChart.data.datasets[0].backgroundColor = chartPalette.blues.slice(0, data.labels.length);
            compositionChart.update();

            // Update legend
            updateLegend(data);
        } catch (error) {
            console.error('Failed to update composition view:', error);
            showError('Failed to update portfolio composition view');
        } finally {
            hideLoading(chartCard, loadingTimeout);
        }
    });
}

function showError(message) {
    const errorContainer = document.createElement('div');
    errorContainer.className = 'error-message';
    errorContainer.textContent = message;

    const chartCard = document.querySelector('.chart-card');
    if (chartCard) {
        // Remove any existing error messages
        const existingError = chartCard.querySelector('.error-message');
        if (existingError) {
            existingError.remove();
        }
        // Add new error message after the section header
        const sectionHeader = chartCard.querySelector('.section-header');
        if (sectionHeader) {
            sectionHeader.insertAdjacentElement('afterend', errorContainer);
        }
    }
}

// Initialize everything when the document is ready
document.addEventListener('DOMContentLoaded', () => {
    initializeCompositionChart();
    setupViewSelector();
});