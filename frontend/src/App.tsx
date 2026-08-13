import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { setCurrencySymbol } from "./lib/format";
import CustomerDetailPage from "./pages/CustomerDetail";
import CustomersPage from "./pages/Customers";
import DashboardPage from "./pages/Dashboard";
import ItemsPage from "./pages/Items";
import LoginPage from "./pages/Login";
import SettingsPage from "./pages/Settings";

export default function App() {
  const { loading } = useAuth();

  // Load display meta (currency symbol, app name) once at startup.
  useEffect(() => {
    api
      .meta()
      .then((m) => setCurrencySymbol(m.currency_symbol))
      .catch(() => {
        /* falls back to default ₹ */
      });
  }, []);

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/items" element={<ItemsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
