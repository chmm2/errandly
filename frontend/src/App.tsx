import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { fetchMyErrands } from "./api/errands";
import ProtectedRoute from "./components/ProtectedRoute";
import Campus from "./pages/Campus";
import Home from "./pages/Home";
import Login from "./pages/Login";
import NewErrand from "./pages/NewErrand";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import Menu from "./pages/Menu";
import Runner from "./pages/Runner";
import Shops from "./pages/Shops";
import Track from "./pages/Track";
import VendorPortal from "./pages/VendorPortal";

// While you're carrying a run (accepted or picked up), you're locked into
// runner mode — order-side pages redirect to /runner even via a direct URL,
// so the toggle lock can't be bypassed by typing the address.
function RequireNoActiveRun() {
  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });
  const onActiveRun = (mine?.running ?? []).some((e) =>
    ["ACCEPTED", "IN_PROGRESS"].includes(e.status),
  );
  return onActiveRun ? <Navigate to="/runner" replace /> : <Outlet />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<ProtectedRoute />}>
        {/* Always reachable, both roles */}
        <Route path="/errands/:id" element={<Track />} />
        <Route path="/runner" element={<Runner />} />
        <Route path="/campus" element={<Campus />} />
        <Route path="/vendor" element={<VendorPortal />} />

        {/* Order-mode pages — blocked while you have a live run */}
        <Route element={<RequireNoActiveRun />}>
          <Route path="/" element={<Home />} />
          <Route path="/errands/new" element={<NewErrand />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/shops" element={<Shops />} />
          <Route path="/shops/:id" element={<Menu />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
