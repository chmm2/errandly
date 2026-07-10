import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../stores/auth";

export default function ProtectedRoute() {
  const accessToken = useAuth((s) => s.accessToken);
  const location = useLocation();

  if (!accessToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
