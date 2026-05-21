(function () {
  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        labels: { color: "#8b96a8", font: { family: "'Segoe UI', system-ui, sans-serif" } },
      },
    },
    scales: {
      x: {
        ticks: { color: "#8b96a8", maxRotation: 45 },
        grid: { color: "rgba(42, 52, 68, 0.6)" },
      },
      y: {
        ticks: { color: "#8b96a8" },
        grid: { color: "rgba(42, 52, 68, 0.6)" },
      },
    },
  };

  let historyChart = null;
  let forecastChart = null;

  function showError(el, msg) {
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  function hideError(el) {
    el.classList.add("hidden");
    el.textContent = "";
  }

  async function loadHistory() {
    const status = document.getElementById("historyStatus");
    const canvas = document.getElementById("historyChart");

    try {
      const res = await fetch("/api/history");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load history");

      if (historyChart) historyChart.destroy();

      historyChart = new Chart(canvas, {
        type: "line",
        data: {
          labels: data.dates,
          datasets: [
            {
              label: "Actual (USD/oz)",
              data: data.actual,
              borderColor: "#4f8cff",
              backgroundColor: "rgba(79, 140, 255, 0.1)",
              fill: true,
              tension: 0.25,
              pointRadius: 0,
            },
            {
              label: "Predicted (USD/oz)",
              data: data.predicted,
              borderColor: "#d4a853",
              backgroundColor: "rgba(212, 168, 83, 0.08)",
              fill: true,
              tension: 0.25,
              pointRadius: 0,
            },
          ],
        },
        options: chartDefaults,
      });

      status.textContent = `Showing ${data.dates.length} days where the model had enough history to predict.`;
    } catch (err) {
      status.textContent = "";
      showError(status, err.message);
      status.classList.remove("muted");
      status.classList.add("alert-error");
    }
  }

  function renderForecastNumbers(forecast, inputPrice) {
    const grid = document.getElementById("forecastNumbers");
    grid.innerHTML = `
      <div class="forecast-day">
        <div class="day-label">Your input</div>
        <div class="day-price">$${inputPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
        <div class="day-date">Today</div>
      </div>
    `;
    forecast.forEach((row) => {
      const el = document.createElement("div");
      el.className = "forecast-day";
      el.innerHTML = `
        <div class="day-label">Day ${row.day}</div>
        <div class="day-price">$${row.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
        <div class="day-date">${row.date}</div>
      `;
      grid.appendChild(el);
    });
  }

  function renderForecastChart(chartData) {
    const canvas = document.getElementById("forecastChart");
    if (forecastChart) forecastChart.destroy();

    forecastChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: "Forecast (USD/oz)",
            data: chartData.values,
            borderColor: "#d4a853",
            backgroundColor: "rgba(212, 168, 83, 0.15)",
            fill: true,
            tension: 0.3,
            pointRadius: 5,
            pointBackgroundColor: "#d4a853",
          },
        ],
      },
      options: {
        ...chartDefaults,
        plugins: {
          ...chartDefaults.plugins,
          legend: { display: false },
        },
      },
    });
  }

  document.getElementById("forecastForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("forecastError");
    const results = document.getElementById("forecastResults");
    hideError(errEl);

    const price = parseFloat(document.getElementById("priceInput").value);
    if (!price || price <= 0) {
      showError(errEl, "Please enter a valid gold price.");
      return;
    }

    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "Calculating…";

    try {
      const res = await fetch("/api/forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ price }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Forecast failed");

      results.classList.remove("hidden");
      renderForecastNumbers(data.forecast, data.input_price);
      renderForecastChart(data.chart);
    } catch (err) {
      showError(errEl, err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Get forecast";
    }
  });

  loadHistory();
})();
