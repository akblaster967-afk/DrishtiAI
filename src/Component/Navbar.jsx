import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  useEffect(() => {
    document.documentElement.classList.toggle("drishti-sidebar-open", menuOpen);
    return () => document.documentElement.classList.remove("drishti-sidebar-open");
  }, [menuOpen]);

  const handleLogout = async () => {
    try {
      await fetch("/api/user-logout", {
        method: "POST",
        credentials: "include",
      });
    } catch {}

    sessionStorage.removeItem("officerId");
    sessionStorage.removeItem("checkpoint");
    sessionStorage.removeItem("userRole");
    sessionStorage.removeItem("latestAnalysisResult");
    sessionStorage.removeItem("userEmail");
    sessionStorage.removeItem("uniqueId");
    sessionStorage.removeItem("isAuthenticated");
    localStorage.removeItem("officerId");
    localStorage.removeItem("checkpoint");
    localStorage.removeItem("userRole");
    closeMenu();
    navigate("/login", { replace: true });
  };

  const navClass = ({ isActive }) =>
    `nav-drawer-link text-base ${isActive ? "nav-drawer-link-active" : ""}`;

  return (
    <header className="site-navbar text-lg">
      <div className="site-navbar-inner">
        <div className="navbar-brand-group">
          <button
            type="button"
            onClick={() => setMenuOpen((previous) => !previous)}
            aria-label="Open navigation menu"
            aria-expanded={menuOpen}
            className="navbar-menu-button text-base"
          >
            <span className="navbar-menu-icon text-xl">☰</span>
          </button>

          <div className="navbar-logo text-xl">D</div>
          <div className="navbar-brand-copy">
            <p className="navbar-kicker text-sm">INTELLIGENT VERIFICATION</p>
            <h1 className="text-2xl font-bold">DRISHTI AI</h1>
            <p className="navbar-subtitle text-base">
              Smart Identity Authenticated System
            </p>
          </div>
        </div>

        <div className="navbar-actions text-base">
          <NavLink
            to="/user-portal"
            className={({ isActive }) =>
              `navbar-action-link text-base ${isActive ? "active" : ""}`
            }
          >
            User Portal
          </NavLink>
          <NavLink
            to="/audit-logs"
            className={({ isActive }) =>
              `navbar-action-link text-base ${isActive ? "active" : ""}`
            }
          >
            Audit Logs
          </NavLink>
          <button
            type="button"
            onClick={handleLogout}
            className="navbar-logout text-base"
          >
            Logout
          </button>
        </div>
      </div>

      {menuOpen && (
        <>
          <button
            type="button"
            aria-label="Close menu"
            onClick={closeMenu}
            className="navbar-overlay"
          />
          <div className="navbar-drawer text-lg">
            <div className="navbar-drawer-heading text-xl">
              DRISHTI AI <span className="text-sm">MENU</span>
            </div>
            <NavLink to="/user-portal" onClick={closeMenu} className={navClass}>
              User Portal
            </NavLink>
            <NavLink to="/forensic" onClick={closeMenu} className={navClass}>
              Screening and Analysis
            </NavLink>
            <NavLink to="/audit-logs" onClick={closeMenu} className={navClass}>
              Screening Audit Logs
            </NavLink>
            <NavLink
              to="/how-it-works"
              onClick={closeMenu}
              className={navClass}
            >
              How It Works
            </NavLink>
            <button
              type="button"
              onClick={handleLogout}
              className="nav-drawer-logout text-base"
            >
              Logout
            </button>
          </div>
        </>
      )}
    </header>
  );
}
