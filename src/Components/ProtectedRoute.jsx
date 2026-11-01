import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { getCurrentUser, getToken } from "../api/authAPI";

function ProtectedRoute({ allowedRoles }) {
  const location = useLocation();
  const token = getToken();
  const [authState, setAuthState] = useState({
    token: null,
    user: null,
    error: "",
  });
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let ignore = false;
    if (!token) return undefined;
    getCurrentUser()
      .then(({ user: currentUser }) => {
        if (!ignore) {
          setAuthState({ token, user: currentUser, error: "" });
        }
      })
      .catch((requestError) => {
        if (!ignore) {
          setAuthState({
            token,
            user: null,
            error:
              requestError.message ||
              "Your account could not be verified. Please try again.",
          });
        }
      });
    return () => {
      ignore = true;
    };
  }, [token, retryCount]);

  const stateMatchesToken = authState.token === token;
  const user = stateMatchesToken ? authState.user : null;

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

  if (!stateMatchesToken) {
    return <p className="manage-status" role="status">Checking your account…</p>;
  }
  if (authState.error) {
    return (
      <div className="app-request-error" role="alert">
        <p>{authState.error}</p>
        <button type="button" onClick={() => setRetryCount((count) => count + 1)}>
          Try again
        </button>
      </div>
    );
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
