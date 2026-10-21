import { useEffect, useState } from "react";
import ProtectedRoute from "./Components/ProtectedRoute";
import Login from "./pages/Auth/Login";
import Register from "./pages/Auth/Register";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import SearchPage from "./pages/SearchPage/SearchPage";
import PropertyDetailsPage from "./pages/PropertyDetailsPage/PropertyDetails";
import UnitsPage from "./pages/UnitsPage/UnitsPage";
import LeasesPage from "./pages/LeasesPage/LeasesPage";
import ManagePropertiesPage from "./pages/ManagePropertiesPage/ManageProperties";
import ManageTenantsPage from "./pages/ManageTenantsPage/ManageTenants";
import ManageApplicationsPage from "./pages/ManageApplicationsPage/ManageApplicationsPage";
import TenantDetailsPage from "./pages/TenantDetailsPage/TenantDetailsPage";
import TenantApplicationsPage from "./pages/TenantApplicationsPage/TenantApplicationsPage";
import MessagesPage from "./pages/MessagesPage/MessagesPage";
import PaymentsPage from "./pages/PaymentsPage/PaymentsPage";
import SecuritySettingsPage from "./pages/SecuritySettingsPage";
import { getCurrentUser, getToken, logoutUser } from "./api/authAPI";
import "./App.css";

function AppShellNav() {
  const [user, setUser] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const token = getToken();

  useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }

    getCurrentUser()
      .then(({ user: currentUser }) => setUser(currentUser))
      .catch(() => setUser(null));
  }, [token, location.pathname]);

  const handleLogout = async () => {
    try {
      await logoutUser();
    } catch (error) {
      console.error("Server sign-out could not revoke the refresh token.", error);
    } finally {
      setUser(null);
      navigate("/login", { replace: true });
    }
  };

  const isLandlord = user?.role === "landlord" || user?.role === "admin";
  const isTenant = user?.role === "tenant";

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="app-brand" aria-label="Property Finder home">
          <span className="app-brand-mark" aria-hidden="true">P</span>
          <span className="app-brand-name">
            <strong>Property Finder</strong>
            <small>{user ? `${user.role} account` : "PROPERTY RECORDS"}</small>
          </span>
        </Link>
        <nav className="app-navigation" aria-label="Main navigation">
          <NavLink
            to="/properties"
            className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
          >
            Search properties
          </NavLink>

          {isLandlord && (
            <>
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
                to="/manage/applications"
                className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
              >
                Applications
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
                to="/payments"
                className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
              >
                Payment history
              </NavLink>
            </>
          )}

          {(user?.role === "landlord" || isTenant) && (
            <NavLink
              to="/messages"
              className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
            >
              Messages
            </NavLink>
          )}

          {isTenant && (
            <>
              <NavLink
                to="/tenant/details"
                className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
              >
                My details
              </NavLink>
              <NavLink
                to="/tenant/applications"
                className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
              >
                My applications
              </NavLink>
              <NavLink
                to="/payments"
                className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
              >
                Payment history
              </NavLink>
            </>
          )}

          {!isLandlord && !isTenant && (
            <>
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
            </>
          )}

          {user && (
            <NavLink
              to="/security"
              className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
            >
              Security
            </NavLink>
          )}

          {user && (
            <button type="button" className="app-navigation-link app-logout-button" onClick={handleLogout}>
              Logout
            </button>
          )}
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/properties" replace />} />
          <Route path="/properties" element={<SearchPage />} />
          <Route path="/properties/:id" element={<PropertyDetailsPage />} />
          <Route path="/tenants" element={<Navigate to="/manage/tenants" replace />} />

          <Route element={<ProtectedRoute allowedRoles={["landlord", "admin"]} />}>
            <Route path="/manage/properties" element={<ManagePropertiesPage />} />
            <Route path="/manage/tenants" element={<ManageTenantsPage />} />
            <Route path="/manage/applications" element={<ManageApplicationsPage />} />
            <Route path="/units" element={<UnitsPage />} />
            <Route path="/leases" element={<LeasesPage />} />
          </Route>

          <Route element={<ProtectedRoute allowedRoles={["tenant"]} />}>
            <Route path="/tenant/details" element={<TenantDetailsPage />} />
            <Route path="/tenant/applications" element={<TenantApplicationsPage />} />
          </Route>

          <Route element={<ProtectedRoute allowedRoles={["landlord", "tenant"]} />}>
            <Route path="/messages" element={<MessagesPage />} />
          </Route>

          <Route element={<ProtectedRoute allowedRoles={["landlord", "admin", "tenant"]} />}>
            <Route path="/payments" element={<PaymentsPage />} />
            <Route path="/security" element={<SecuritySettingsPage />} />
          </Route>

          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="app-footer">
        <span>Manage your rental portfolio in one place.</span>
        <span>Management pages are protected by your account role.</span>
      </footer>
    </div>
  );
}

function App() {
  return <AppShellNav />;
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