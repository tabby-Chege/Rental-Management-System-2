import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import SearchPage from "./pages/SearchPage/SearchPage";
import PropertyDetailsPage from "./pages/PropertyDetailsPage/PropertyDetails";
import "./App.css";

function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="app-brand" aria-label="Property Finder home">
          <span className="app-brand-mark" aria-hidden="true">P</span>
          <span className="app-brand-name">
            <strong>Property Finder</strong>
            <small>PROPERTY RECORDS</small>
          </span>
        </Link>
        <nav className="app-navigation" aria-label="Main navigation">
          <NavLink
            to="/properties"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Search properties
          </NavLink>
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/properties" replace />} />
          <Route path="/properties" element={<SearchPage />} />
          <Route path="/properties/:id" element={<PropertyDetailsPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer className="app-footer">
        <span>Property records provided by RentCast.</span>
        <span>Records do not confirm current rental availability.</span>
      </footer>
    </div>
  );
}

function NotFound() {
  return (
    <section className="not-found">
      <p className="not-found-code">404</p>
      <h1>Page not found</h1>
      <Link to="/properties">Back to property search</Link>
    </section>
  );
}

export default App;
