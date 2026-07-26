import { Navigate, Route, Routes } from "react-router-dom";
import { PageHomePage } from "./pages/PageHomePage";
import { PageServiceDetailPage } from "./pages/PageServiceDetailPage";
import { PageBookingPage } from "./pages/PageBookingPage";
import { PageConfirmationPage } from "./pages/PageConfirmationPage";
import { RoleAccess } from "./runtime/RoleAccess";

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RoleAccess pageId="PAGE-HOME" roleIds={["ROLE-CLIENT"]}>
            <PageHomePage />
          </RoleAccess>
        }
      />
      <Route
        path="/services"
        element={
          <RoleAccess pageId="PAGE-SERVICE-DETAIL" roleIds={["ROLE-CLIENT"]}>
            <PageServiceDetailPage />
          </RoleAccess>
        }
      />
      <Route
        path="/booking"
        element={
          <RoleAccess pageId="PAGE-BOOKING" roleIds={["ROLE-CLIENT"]}>
            <PageBookingPage />
          </RoleAccess>
        }
      />
      <Route
        path="/confirmation"
        element={
          <RoleAccess pageId="PAGE-CONFIRMATION" roleIds={["ROLE-CLIENT"]}>
            <PageConfirmationPage />
          </RoleAccess>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
