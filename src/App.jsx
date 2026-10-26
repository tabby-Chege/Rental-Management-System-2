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
import MaintenancePage from "./pages/MaintenancePage/MaintenancePage";
import LeaseDocumentsPage from "./pages/LeaseDocumentsPage/LeaseDocumentsPage";
import ReportsPage from "./pages/ReportsPage/ReportsPage";
import LandlordDashboardPage from "./pages/LandlordDashboardPage";
import TenantDashboardPage from "./pages/TenantDashboardPage";
import PaymentsPage from "./pages/PaymentsPage/PaymentsPage";
import SecuritySettingsPage from "./pages/SecuritySettingsPage";
import { getCurrentUser, getToken, logoutUser } from "./api/authAPI";
import { listConversations } from "./api/conversationsApi";
import "./App.css";

function AppShellNav() {
  const [user, setUser] = useState(null);
  const [failedToken, setFailedToken] = useState("");
  const [unreadMessages, setUnreadMessages] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const token = getToken();

  useEffect(() => {
    if (!token) return undefined;
    let ignore = false;
    getCurrentUser()
      .then(({ user: currentUser }) => {
        if (!ignore) setUser(currentUser);
      })
      .catch((error) => {
        if (!ignore) {
          console.error("Could not load the signed-in account.", error);
          setUser(null);
          setFailedToken(token);
        }
      });
    return () => {
      ignore = true;
    };
  }, [token]);
  const userLoading = Boolean(token) && !user && failedToken !== token;

  const handleLogout = async () => {
    try {
      await logoutUser();
    } catch (error) {
      console.error("Server sign-out could not revoke the refresh token.", error);
    } finally {
      setUser(null);
      setFailedToken("");
      navigate("/login", { replace: true });
    }
  };

  const isLandlord = user?.role === "landlord" || user?.role === "admin";
  const isTenant = user?.role === "tenant";
  const navigation = isLandlord
    ? [
        ["Dashboard", "/dashboard"],
        ["Properties", "/manage/properties"],
        ["Tenants", "/manage/tenants"],
        ["Applications", "/manage/applications"],
        ["Units", "/units"],
        ["Leases", "/leases"],
        ["Maintenance", "/maintenance"],
        ["Lease documents", "/lease-documents"],
        ["Payments", "/payments"],
        ["Reports", "/reports"],
        ["Messages", "/messages"],
        ["Security", "/security"],
      ]
    : isTenant
      ? [
          ["Home", "/dashboard"],
          ["Find a place", "/properties"],
          ["My details", "/tenant/details"],
          ["My applications", "/tenant/applications"],
          ["Payments", "/payments"],
          ["Maintenance", "/maintenance"],
          ["Lease documents", "/lease-documents"],
          ["Messages", "/messages"],
          ["Security", "/security"],
        ]
      : [];

  useEffect(() => {
    if (!token || !user || !["landlord", "admin", "tenant"].includes(user.role)) return undefined;
    let ignore = false;
    async function refreshUnread() {
      try {
        const conversations = await listConversations();
        if (!ignore) {
          setUnreadMessages(
            conversations.reduce((total, item) => total + (item.unread_count || 0), 0),
          );
        }
      } catch (error) {
        if (!ignore) console.error("Could not refresh unread messages.", error);
      }
    }
    refreshUnread();
    const interval = window.setInterval(refreshUnread, 30000);
    return () => {
      ignore = true;
      window.clearInterval(interval);
    };
  }, [token, user, location.pathname]);

  return (
    <div className={`app-shell${user ? " has-sidebar" : ""}`}>
      <header className="app-header">
        <Link to="/" className="app-brand" aria-label="Property Finder home">
          <span className="app-brand-mark" aria-hidden="true">P</span>
          <span className="app-brand-name">
            <strong>Property Finder</strong>
            <small>{user ? `${user.role} account` : "PROPERTY RECORDS"}</small>
          </span>
        </Link>
        <div className="app-header-actions">
          <Link className="app-search-link" to="/properties">Search properties</Link>
          {user && (
            <details className="app-account-menu">
              <summary>{user.name || user.email || user.role}</summary>
              <div>
                <span>{user.email || `${user.role} account`}</span>
                <button type="button" className="app-logout-button" onClick={handleLogout}>Sign out</button>
              </div>
            </details>
          )}
          {!user && (
            <>
              <Link className="app-search-link" to="/login">Sign in</Link>
              <Link className="app-search-link" to="/register">Create account</Link>
            </>
          )}
        </div>
      </header>
      <div className="app-workspace">
      {user && (
        <aside className="app-sidebar">
          <p className="app-sidebar-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            {navigation.map(([label, path]) => (
              <NavLink
                key={path}
                to={path}
                end={path === "/dashboard"}
                className={({ isActive }) => isActive ? "app-navigation-link is-active" : "app-navigation-link"}
              >
                <span>{label}</span>
                {path === "/messages" && unreadMessages > 0 && (
                  <span className="app-unread-badge" aria-label={`${unreadMessages} unread messages`}>
                    {unreadMessages > 99 ? "99+" : unreadMessages}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>
      )}
      <main className="app-main">
        <Routes>
          <Route path="/" element={userLoading ? <p className="app-route-loading">Loading your workspace…</p> : <Navigate to={user ? "/dashboard" : "/properties"} replace />} />
          <Route path="/dashboard" element={
            userLoading
              ? <p className="app-route-loading">Loading your workspace…</p>
              : isLandlord
                ? <LandlordDashboardPage />
                : isTenant
                  ? <TenantDashboardPage />
                  : <Navigate to="/login" replace />
          } />
          <Route path="/properties" element={<SearchPage />} />
          <Route path="/properties/:id" element={<PropertyDetailsPage />} />
          <Route path="/tenants" element={<Navigate to="/manage/tenants" replace />} />

          <Route element={<ProtectedRoute allowedRoles={["landlord", "admin"]} />}>
            <Route path="/manage/properties" element={<ManagePropertiesPage />} />
            <Route path="/manage/tenants" element={<ManageTenantsPage />} />
            <Route path="/manage/applications" element={<ManageApplicationsPage />} />
            <Route path="/units" element={<UnitsPage />} />
            <Route path="/leases" element={<LeasesPage />} />
            <Route path="/reports" element={<ReportsPage />} />
          </Route>

          <Route element={<ProtectedRoute allowedRoles={["tenant"]} />}>
            <Route path="/tenant/details" element={<TenantDetailsPage />} />
            <Route path="/tenant/applications" element={<TenantApplicationsPage />} />
          </Route>

          <Route element={<ProtectedRoute allowedRoles={["landlord", "admin", "tenant"]} />}>
            <Route path="/messages" element={<MessagesPage />} />
            <Route path="/maintenance" element={<MaintenancePage />} />
            <Route path="/lease-documents" element={<LeaseDocumentsPage />} />
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
      </div>
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