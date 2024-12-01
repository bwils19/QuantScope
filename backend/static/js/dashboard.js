document.getElementById('stockForm').addEventListener('submit', async (event) => {
    event.preventDefault();

    const stockTicker = document.getElementById('stockTicker').value.trim();
    if (!stockTicker) {
        alert('Please enter a stock ticker');
        return;
    }

    try {
        const response = await fetch('/stocks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ symbol: stockTicker }),
        });

        const data = await response.json();
        console.log('Data received for rendering chart:', data);

        if (data.message) {
            alert(data.message);
        } else {
            renderChart(data);
        }
    } catch (error) {
        console.error('Error fetching stock data:', error);
    }
});

function renderChart(stockData) {
    const labels = stockData.dates;
    const values = stockData.prices;

    const container = document.getElementById('stockChartContainer');
    container.innerHTML = ''; // Clear existing chart
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');

    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `${stockData.symbol} Closing Prices`,
                data: values,
                borderColor: 'rgba(108, 125, 147, 1)',
                borderWidth: 2,
                fill: true, // Enable the fill for the gradient
                backgroundColor: function(context) {
                    const chart = context.chart;
                    const { ctx, chartArea } = chart;
                    if (!chartArea) {
                        return null;
                    }

                    const gradient = ctx.createLinearGradient(
                        0,
                        chart.scales.y.getPixelForValue(Math.max(...values)),
                        0,
                        chart.chartArea.bottom
                    );

                    // gradient.addColorStop(0, 'rgba(75, 192, 192, 0.8)'); // Darker at the line
                    // gradient.addColorStop(1, 'rgba(75, 192, 192, 0.1)'); // Fainter near x-axis

                    gradient.addColorStop(0, 'rgba(108, 125, 147, 0.8)'); // Darker at the line
                    gradient.addColorStop(1, 'rgba(108, 125, 147, 0.1)'); // Fainter near x-axis
                    return gradient;
                }
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { title: { display: true, text: 'Date' } },
                y: { title: { display: true, text: 'Price (USD)' } },
            },
        },
    });
}





document.getElementById('timeFrameButtons').addEventListener('click', (event) => {
    const button = event.target;
    const timeFrame = button.getAttribute('data-timeframe');

    if (!timeFrame) return;

    // Fetch and filter data based on the selected time frame
    const stockTicker = document.getElementById('stockTicker').value.trim();
    if (!stockTicker) {
        alert('Please enter a stock ticker first');
        return;
    }

    fetch('/stocks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: stockTicker }),
    })
        .then((response) => response.json())
        .then((data) => {
            const filteredData = filterDataByTimeFrame(data, timeFrame);
            renderChart(filteredData);
        })
        .catch((error) => console.error('Error fetching stock data:', error));
});

function filterDataByTimeFrame(stockData, timeFrame) {
    const { dates, prices } = stockData;

    let filteredDates, filteredPrices;
    switch (timeFrame) {
        case '1D':
            filteredDates = dates.slice(-1);
            filteredPrices = prices.slice(-1);
            break;
        case '1W':
            filteredDates = dates.slice(-7);
            filteredPrices = prices.slice(-7);
            break;
        case '10D':
            filteredDates = dates.slice(-10);
            filteredPrices = prices.slice(-10);
            break;
        case '1M':
            filteredDates = dates.slice(-30);
            filteredPrices = prices.slice(-30);
            break;
        case '3M':
            filteredDates = dates.slice(-90);
            filteredPrices = prices.slice(-90);
            break;
        case '6M':
            filteredDates = dates.slice(-180);
            filteredPrices = prices.slice(-180);
            break;
        case '1Y':
            filteredDates = dates.slice(-365);
            filteredPrices = prices.slice(-365);
            break;
        default:
            filteredDates = dates;
            filteredPrices = prices;
    }

    return {
        symbol: stockData.symbol,
        dates: filteredDates,
        prices: filteredPrices,
    };
}



