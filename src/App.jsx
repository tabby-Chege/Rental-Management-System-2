import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Auth/Login";
import Register from "./pages/Auth/Register";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import SearchPage from "./pages/SearchPage/SearchPage";
import PropertyDetailsPage from "./pages/PropertyDetailsPage/PropertyDetailsPage";
import TenantsPage from "./pages/TenantsPage/TenantsPage";
import UnitsPage from "./pages/UnitsPage/UnitsPage";
import LeasesPage from "./pages/LeasesPage/LeasesPage";
import ManagePropertiesPage from "./pages/ManagePropertiesPage/ManagePropertiesPage";
import ManageTenantsPage from "./pages/ManageTenantsPage/ManageTenantsPage";
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
          <NavLink
            to="/manage/properties"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            My properties
          </NavLink>
          <NavLink
            to="/manage/tenants"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            My tenants
          </NavLink>
          <NavLink
            to="/tenants"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Tenants
          </NavLink>
          <NavLink
            to="/units"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Units
          </NavLink>
          <NavLink
            to="/leases"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Leases
          </NavLink>
          <NavLink
            to="/login"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Login
          </NavLink>
          <NavLink
            to="/register"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Register
          </NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/properties" replace />} />
          <Route path="/properties" element={<SearchPage />} />
          <Route path="/properties/:id" element={<PropertyDetailsPage />} />
          <Route path="/tenants" element={<TenantsPage />} />
          <Route path="/units" element={<UnitsPage />} />
          <Route path="/leases" element={<LeasesPage />} />
          
          <Route element={<ProtectedRoute />}>
            <Route path="/manage/properties" element={<ManagePropertiesPage />} />
            <Route path="/manage/tenants" element={<ManageTenantsPage />} />
          </Route>

          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="app-footer">
        <span>Manage your rental portfolio in one place.</span>
        <span>Property and tenant records are private to your account.</span>
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