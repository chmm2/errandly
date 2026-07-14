import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import Campus from "./pages/Campus";
import Home from "./pages/Home";
import Login from "./pages/Login";
import NewErrand from "./pages/NewErrand";
import Register from "./pages/Register";
import Menu from "./pages/Menu";
import Runner from "./pages/Runner";
import Shops from "./pages/Shops";
import Timetable from "./pages/Timetable";
import Track from "./pages/Track";
import VendorPortal from "./pages/VendorPortal";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Home />} />
        <Route path="/errands/new" element={<NewErrand />} />
        <Route path="/errands/:id" element={<Track />} />
        <Route path="/runner" element={<Runner />} />
        <Route path="/timetable" element={<Timetable />} />
        <Route path="/campus" element={<Campus />} />
        <Route path="/shops" element={<Shops />} />
        <Route path="/shops/:id" element={<Menu />} />
        <Route path="/vendor" element={<VendorPortal />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
