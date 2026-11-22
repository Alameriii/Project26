import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import { useSession } from "./lib/session.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import ApprovalsPage from "./pages/ApprovalsPage.jsx";
import AssetDetailPage from "./pages/AssetDetailPage.jsx";
import AssetFormPage from "./pages/AssetFormPage.jsx";
import HomePage from "./pages/HomePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MarketplacePage from "./pages/MarketplacePage.jsx";
import NewRequestPage from "./pages/NewRequestPage.jsx";
import RequestDetailPage from "./pages/RequestDetailPage.jsx";
import RequestsPage from "./pages/RequestsPage.jsx";
import TransferDetailPage from "./pages/TransferDetailPage.jsx";
import TransfersPage from "./pages/TransfersPage.jsx";

function RequireAuth({ children }) {
  const { user, loading } = useSession();
  const location = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

function NotFound() {
  return (
    <div className="page page-narrow">
      <h1>Page not found</h1>
      <p className="muted" style={{ marginTop: 8 }}>The link may be out of date. Use the menu to continue.</p>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<HomePage />} />
        <Route path="assets" element={<MarketplacePage />} />
        <Route path="assets/new" element={<AssetFormPage />} />
        <Route path="assets/:id" element={<AssetDetailPage />} />
        <Route path="assets/:id/edit" element={<AssetFormPage />} />
        <Route path="requests" element={<RequestsPage />} />
        <Route path="requests/new" element={<NewRequestPage />} />
        <Route path="requests/:id" element={<RequestDetailPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        <Route path="transfers" element={<TransfersPage />} />
        <Route path="transfers/:id" element={<TransferDetailPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
