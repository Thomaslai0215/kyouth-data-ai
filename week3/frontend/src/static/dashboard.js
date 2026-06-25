const totalJobs = document.getElementById("total-jobs");
const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const searchStatus = document.getElementById("search-status");
const searchResults = document.getElementById("search-results");

const chartColors = [
  "#8f84c8",
  "#6f9fd8",
  "#7bc8a4",
  "#e8a87c",
  "#d47b9e",
  "#9aa0a6",
  "#c4b5fd",
  "#60a5fa",
  "#94a3b8",
];

function makeChart(canvasId, type, labels, values) {
  const canvas = document.getElementById(canvasId);
  return new Chart(canvas, {
    type,
    data: {
      labels,
      datasets: [
        {
          label: "Jobs",
          data: values,
          backgroundColor: chartColors.slice(0, values.length),
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: type === "pie" ? "right" : "top",
        },
        tooltip: {
          callbacks: {
            title: (items) => items[0]?.label || "",
            label: (item) => `${item.parsed.y ?? item.parsed} job(s)`,
          },
        },
      },
      scales:
        type === "bar"
          ? {
              y: {
                beginAtZero: true,
                ticks: { stepSize: 1 },
              },
            }
          : {},
    },
  });
}

function renderResults(rows, total, queryLabel) {
  searchResults.innerHTML = "";
  if (!rows.length) {
    searchStatus.textContent = "No jobs matched your search.";
    return;
  }

  if (total > rows.length) {
    searchStatus.textContent = `Showing ${rows.length} of ${total} jobs for "${queryLabel}".`;
  } else {
    searchStatus.textContent = `${total} job(s) found for "${queryLabel}".`;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.job_title)}</td>
      <td>${escapeHtml(row.company)}</td>
      <td>${escapeHtml(row.description)}</td>
    `;
    searchResults.appendChild(tr);
  }
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function runSearch(query) {
  const searchQuery = (query ?? searchInput.value).trim();
  if (!searchQuery) {
    searchStatus.textContent = "Enter a keyword to search.";
    searchResults.innerHTML = "";
    return;
  }

  searchInput.value = searchQuery;
  searchStatus.textContent = "Searching...";
  const response = await fetch(`/api/jobs/search?q=${encodeURIComponent(searchQuery)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    searchStatus.textContent = error.detail || "Search failed.";
    return;
  }

  const data = await response.json();
  renderResults(data.results, data.total, searchQuery);
}

async function loadStats() {
  const response = await fetch("/api/jobs/stats");
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Could not load job stats.");
  }

  const data = await response.json();
  totalJobs.textContent = `${data.total} jobs in the database`;

  const companyLabels = data.companies.map((row) => row.label);
  const companyValues = data.companies.map((row) => row.count);

  const companyChart = makeChart("company-chart", "pie", companyLabels, companyValues);
  companyChart.options.onClick = (_event, elements) => {
    if (!elements.length) {
      return;
    }
    const slice = data.companies[elements[0].index];
    if (slice.group === "other") {
      runSearch("other");
    } else {
      runSearch(slice.label);
    }
  };

  makeChart(
    "title-chart",
    "bar",
    data.titles.map((row) => row.label),
    data.titles.map((row) => row.count)
  );
}

searchBtn.addEventListener("click", () => runSearch());
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runSearch();
  }
});

loadStats().catch((error) => {
  totalJobs.textContent = error.message;
});
