import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { clearToken, getCurrentUser, getToken } from "../api/authAPI";

function ProtectedRoute({ allowedRoles }) {
  const location = useLocation();
  const token = getToken();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(token));

  useEffect(() => {
    let ignore = false;
    if (!token) {
      setUser(null);
      setLoading(false);
      return () => {
        ignore = true;
      };
    }

    setLoading(true);
    getCurrentUser()
      .then(({ user: currentUser }) => {
        if (!ignore) setUser(currentUser);
      })
      .catch(() => {
        clearToken();
        if (!ignore) setUser(null);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [token]);

  if (!token) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          returnTo: `${location.pathname}${location.search}${location.hash}`,
        }}
      />
    );
  }

  if (loading) {
    return <p className="manage-status" role="status">Checking your account…</p>;
  }
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          returnTo: `${location.pathname}${location.search}${location.hash}`,
        }}
      />
    );
  }
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <Navigate
        to={user.role === "tenant" ? "/tenant/details" : "/manage/properties"}
        replace
      />
    );
  }

  return <Outlet />;
}

export default ProtectedRoute;
