import { useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import Login from "./Pages/Login";
import CreateAccount from "./Pages/CreateAccount";
import ForensicDeepDive from "./Pages/ForensicDeepDive";
import UserPortal from "./Pages/UserPortal";
import Navbar from "./Component/Navbar";
import HelpIcon from "./Component/HelpIcon";
import HowItWorks from "./Pages/HowItWorks";
import AuditLogs from "./Pages/AuditLogs";
import AnalysisResult from "./Pages/AnalysisResult";

function clearClientAuthState() {
  sessionStorage.removeItem("userEmail");
  sessionStorage.removeItem("uniqueId");
  sessionStorage.removeItem("isAuthenticated");
}

function ProtectedUserRoute({ children }) {
  const location = useLocation();
  const [status, setStatus] = useState(() => {
    const authenticated = sessionStorage.getItem("isAuthenticated") === "true";
    const userEmail = sessionStorage.getItem("userEmail");
    const uniqueId = sessionStorage.getItem("uniqueId");

    return authenticated && userEmail && uniqueId
      ? "authenticated"
      : "checking";
  });

  useEffect(() => {
    let cancelled = false;

    const localSessionLooksValid =
      sessionStorage.getItem("isAuthenticated") === "true" &&
      Boolean(sessionStorage.getItem("userEmail")) &&
      /^\d{10}$/.test(sessionStorage.getItem("uniqueId") || "");

    
    
    
    
    
    if (localSessionLooksValid) {
      setStatus("authenticated");
      return () => {
        cancelled = true;
      };
    }

    async function checkSession() {
      try {
        const response = await fetch("/api/users/me", {
          method: "GET",
          credentials: "include",
          headers: {
            Accept: "application/json",
          },
        });

        if (!response.ok) {
          clearClientAuthState();
          if (!cancelled) setStatus("unauthenticated");
          return;
        }

        const result = await response.json();
        const user = result.user || {};

        if (user.email) {
          sessionStorage.setItem("userEmail", String(user.email));
        }
        if (user.uniqueId) {
          sessionStorage.setItem("uniqueId", String(user.uniqueId));
        }

        sessionStorage.setItem("isAuthenticated", "true");

        if (!cancelled) setStatus("authenticated");
      } catch {
        clearClientAuthState();
        if (!cancelled) setStatus("error");
      }
    }

    checkSession();

    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "checking") {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm px-6 py-5 text-center">
          <div className="text-sm font-bold text-slate-800">Checking secure session...</div>
          <div className="text-xs text-slate-500 mt-1">Please wait.</div>
        </div>
      </div>
    );
  }

  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return children;
}

function ProtectedShell({ children }) {
  return (
    <div className="protected-shell">
      <Navbar />
      <main className="site-main">{children}</main>
      <HelpIcon />
    </div>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 flex flex-col relative">
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Login />} />
        <Route path="/create-account" element={<CreateAccount />} />
        <Route path="/reset-password" element={<Login />} />
        <Route path="/how-it-works" element={<ProtectedUserRoute><ProtectedShell><HowItWorks /></ProtectedShell></ProtectedUserRoute>} />
        <Route path="/forensic" element={<ProtectedUserRoute><ProtectedShell><ForensicDeepDive /></ProtectedShell></ProtectedUserRoute>} />
        <Route path="/audit-logs" element={<ProtectedUserRoute><ProtectedShell><AuditLogs /></ProtectedShell></ProtectedUserRoute>} />
        <Route path="/analysis-result" element={<ProtectedUserRoute><ProtectedShell><AnalysisResult /></ProtectedShell></ProtectedUserRoute>} />
        <Route path="/user-portal" element={<ProtectedUserRoute><ProtectedShell><UserPortal /></ProtectedShell></ProtectedUserRoute>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </div>
  );
}
