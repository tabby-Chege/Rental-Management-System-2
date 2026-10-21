import { useEffect, useState } from "react";
import { getPortfolioReport } from "../../api/landlordToolsApi";
import "../manage.css";
import "./ReportsPage.css";

const COLUMNS = [
  ["property_name", "Property"],
  ["city", "City"],
  ["currency", "Currency"],
  ["rent_income", "Rent income"],
  ["rent_arrears", "Rent arrears"],
  ["total_units", "Total units"],
  ["occupied_units", "Occupied"],
  ["reserved_units", "Reserved"],
  ["vacant_units", "Vacant"],
];

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function ReportsPage() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    getPortfolioReport()
      .then((result) => {
        if (!ignore) setReport(result);
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  function downloadCsv() {
    const rows = [
      COLUMNS.map(([, label]) => label),
      ...(report?.properties ?? []).map((row) =>
        COLUMNS.map(([key]) => row[key]),
      ),
    ];
    const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "rental-portfolio-report.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="manage-page reports-page">
      <header className="reports-header">
        <div>
          <h1>Portfolio reports</h1>
          <p className="manage-status">
            Income, rent arrears, and occupancy by property.
            {report?.generated_at ? ` Generated ${report.generated_at}.` : ""}
          </p>
        </div>
        {!loading && report && (
          <div className="manage-actions reports-actions">
            <button className="manage-button" type="button" onClick={downloadCsv}>
              Export CSV
            </button>
            <button
              className="manage-button is-secondary"
              type="button"
              onClick={() => window.print()}
            >
              Print / Save as PDF
            </button>
          </div>
        )}
      </header>
      {error && <p className="manage-error" role="alert">{error}</p>}
      {loading ? (
        <p className="manage-status">Building your report…</p>
      ) : report?.properties?.length ? (
        <div className="reports-table-wrap">
          <table className="reports-table">
            <thead>
              <tr>{COLUMNS.map(([, label]) => <th key={label}>{label}</th>)}</tr>
            </thead>
            <tbody>
              {report.properties.map((row) => (
                <tr key={row.property_id}>
                  {COLUMNS.map(([key]) => (
                    <td key={key}>
                      {["rent_income", "rent_arrears"].includes(key)
                        ? `${row.currency} ${Number(row[key]).toLocaleString()}`
                        : row[key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        !error && <p className="manage-status">No property data is available yet.</p>
      )}
    </section>
  );
}

export default ReportsPage;
