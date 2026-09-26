import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ArrowRight, BadgeCheck, Eye, EyeOff, Fingerprint, LockKeyhole, ScanText, ShieldCheck, Sparkles } from "lucide-react";

const API = "/api";
async function api(path, body) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  const text = await response.text();
  let result = {};
  try {
    result = text ? JSON.parse(text) : {};
  } catch {
    
  }
  if (!response.ok) {
    const detail = result.detail || result.message;
    throw new Error(
      detail ||
        `Server error (${response.status}). Please start the backend and try again.`,
    );
  }
  return result;
}
const validEmail = (v) => /^\S+@\S+\.\S+$/.test(v.trim());
const passwordError = (v) => {
  if (!v) return "Enter your password.";
  if (v.length > 10) return "Password must be at most 10 characters.";
  if (v.length < 8) return "Password must be at least 8 characters.";
  if (!/^[A-Za-z0-9@]+$/.test(v))
    return "Password may contain only letters, numbers and @.";
  if (!/[A-Z]/.test(v))
    return "Password must contain at least 1 capital letter.";
  if (!/[a-z]/.test(v)) return "Password must contain at least 1 small letter.";
  if (!/[0-9]/.test(v)) return "Password must contain at least 1 number.";
  if (!/@/.test(v)) return "Password must contain @ as the symbol.";
  return "";
};

function PasswordBox({ value, setValue, show, setShow, placeholder, onInput }) {
  return (
    <div className="relative">
      <input
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          onInput?.();
        }}
        className="w-full px-3 py-2.5 pr-11 border border-slate-300 rounded bg-slate-50 text-base"
        placeholder={placeholder}
        autoComplete="current-password"
        maxLength={10}
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-sky-900 cursor-pointer"
        aria-label={show ? "Hide password" : "Show password"}
      >
        {show ? (
          <EyeOff size={18} strokeWidth={2} />
        ) : (
          <Eye size={18} strokeWidth={2} />
        )}
      </button>
    </div>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [forgotMode, setForgotMode] = useState(false);
  const [resetMode, setResetMode] = useState(false);
  const [email, setEmail] = useState(location.state?.email || "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const clear = () => {
    setError("");
    setSuccess("");
  };
  const backToLogin = () => {
    setForgotMode(false);
    setResetMode(false);
    setOtpSent(false);
    setOtp("");
    setResetToken("");
    setPassword("");
    setConfirmPassword("");
    clear();
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    clear();
    const normalized = email.trim().toLowerCase();
    if (!validEmail(normalized))
      return setError("Enter a valid email address.");
    const pe = passwordError(password);
    if (pe) return setError(pe);
    setBusy(true);
    try {
      const r = await api("/auth/login", { email: normalized, password });
      sessionStorage.setItem("userEmail", normalized);
      sessionStorage.setItem("uniqueId", String(r.user?.uniqueId || ""));
      sessionStorage.setItem("isAuthenticated", "true");
      navigate("/user-portal", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const sendResetOtp = async () => {
    clear();
    const normalized = email.trim().toLowerCase();
    if (!validEmail(normalized))
      return setError("Enter the email address associated with your account.");
    setBusy(true);
    try {
      const r = await api("/auth/forgot-password", { email: normalized });
      setOtpSent(true);
      setSuccess(r.message || "A 6-digit OTP has been sent.");
    } catch (err) {
      setError(
        err instanceof TypeError
          ? "Cannot connect to the Drishti AI server. Start the backend on port 8000 and try again."
          : err.message,
      );
    } finally {
      setBusy(false);
    }
  };

  const verifyResetOtp = async () => {
    clear();
    if (!/^\d{6}$/.test(otp)) return setError("Enter the 6-digit OTP.");
    setBusy(true);
    try {
      const r = await api("/auth/forgot-password/verify-otp", {
        email: email.trim().toLowerCase(),
        otp,
      });
      setResetToken(r.resetToken);
      setResetMode(true);
      setOtp("");
      setSuccess(r.message || "OTP verified. Create your new password.");
    } catch (err) {
      setError(
        err instanceof TypeError
          ? "Cannot connect to the Drishti AI server. Start the backend on port 8000 and try again."
          : err.message,
      );
    } finally {
      setBusy(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    clear();
    const pe = passwordError(password);
    if (!resetToken)
      return setError("Verify the OTP before setting a new password.");
    if (pe) return setError(pe);
    if (password !== confirmPassword)
      return setError("Passwords do not match.");
    setBusy(true);
    try {
      const r = await api("/auth/reset-password", {
        token: resetToken,
        password,
      });
      setSuccess(
        r.message || "Password changed successfully. You can now log in.",
      );
      setTimeout(backToLogin, 600);
    } catch (err) {
      setError(
        err instanceof TypeError
          ? "Cannot connect to the Drishti AI server. Start the backend on port 8000 and try again."
          : err.message,
      );
    } finally {
      setBusy(false);
    }
  };

  const message = error ? (
    <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm font-semibold">
      {error}
    </div>
  ) : success ? (
    <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded p-3 text-sm font-semibold">
      {success}
    </div>
  ) : null;
  return (
    <div className="auth-page min-h-screen bg-slate-200 flex items-center justify-center p-4 md:p-6">
      <div className="auth-card w-full max-w-[980px] min-h-0 bg-white rounded-2xl border border-slate-200 shadow-2xl overflow-hidden grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="auth-side-panel relative hidden lg:flex overflow-hidden bg-sky-900 text-white p-6 xl:p-7">
          <div className="absolute -top-24 -right-24 w-64 h-64 rounded-full bg-emerald-400/15 blur-3xl" />
          <div className="absolute -bottom-28 -left-24 w-72 h-72 rounded-full bg-sky-400/20 blur-3xl" />
          <div className="relative z-10 w-full h-full flex flex-col justify-center">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-11 h-11 rounded-xl bg-emerald-400 text-sky-950 flex items-center justify-center font-black text-lg shadow-lg">DA</div>
              <div>
                <p className="text-[10px] text-emerald-300 font-bold uppercase tracking-[0.24em]">Intelligent Screening</p>
                <h1 className="text-2xl font-black tracking-wide">Drishti AI</h1>
              </div>
            </div>
            <div className="auth-live-card border border-white/15 bg-white/5 rounded-2xl p-5 backdrop-blur-sm w-full">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-base font-bold">AI-powered verification workspace</p>
                  <p className="text-xs text-slate-300 mt-1">Evidence-first screening for identity documents.</p>
                </div>
                <span className="auth-live-badge"><span className="auth-live-dot" />SYSTEM READY</span>
              </div>
              <div className="auth-pipeline mt-5">
                <div><span><ScanText size={15} /></span><p>OCR</p></div><i />
                <div><span><Fingerprint size={15} /></span><p>VERIFY</p></div><i />
                <div><span><Sparkles size={15} /></span><p>AI FORENSICS</p></div><i />
                <div><span><ShieldCheck size={15} /></span><p>REPORT</p></div>
              </div>
              <div className="grid grid-cols-3 gap-3 mt-5">
                <div className="auth-feature-tile"><p className="text-emerald-300 text-lg font-black">OCR</p><p className="text-[10px] text-slate-300 mt-1">Field extraction</p></div>
                <div className="auth-feature-tile"><p className="text-emerald-300 text-lg font-black">AI</p><p className="text-[10px] text-slate-300 mt-1">Risk screening</p></div>
                <div className="auth-feature-tile"><p className="text-emerald-300 text-lg font-black">LIVE</p><p className="text-[10px] text-slate-300 mt-1">Identity check</p></div>
              </div>
              <div className="auth-trust-row mt-4"><LockKeyhole size={15} /><span>Authenticated workspace</span><span className="auth-trust-separator" /><BadgeCheck size={15} /><span>Evidence-based workflow</span></div>
            </div>
          </div>
        </section>

        <section className="flex flex-col justify-center bg-white p-6 sm:p-7">
          <div className="max-w-md w-full mx-auto">
            <div className="auth-inline-card lg:hidden" aria-label="Drishti AI workspace">
              <div className="auth-inline-head">
                <div>
                  <p className="auth-inline-kicker">DRISHTI AI</p>
                  <p className="auth-inline-title">Secure verification workspace</p>
                </div>
                <span className="auth-inline-status"><i /> READY</span>
              </div>
              <div className="auth-inline-pipeline"><span><b>OCR</b><em>Extract</em></span><i /><span><b>VERIFY</b><em>Match</em></span><i /><span><b>RISK</b><em>Screen</em></span><i /><span><b>REPORT</b><em>Result</em></span></div>
            </div>
            <div className="lg:hidden flex items-center gap-3 mb-8">
              <div className="w-11 h-11 rounded-xl bg-sky-900 text-emerald-400 flex items-center justify-center font-black">
                DA
              </div>
              <div>
                <p className="text-2xl font-black text-sky-900">Drishti AI</p>
                <p className="text-xs text-slate-500 uppercase tracking-widest">
                  Secure verification
                </p>
              </div>
            </div>

            {resetMode ? (
              <form onSubmit={handleResetPassword} className="space-y-5">
                <div>
                  <p className="text-sm text-emerald-600 font-bold uppercase tracking-widest">
                    Account security
                  </p>
                  <h2 className="text-3xl font-black text-slate-900 mt-2">
                    Set New Password
                  </h2>
                  <p className="text-base text-slate-500 mt-2">
                    Create a new password for your account.
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 uppercase mb-2">
                    New Password
                  </label>
                  <PasswordBox
                    value={password}
                    setValue={setPassword}
                    show={showPassword}
                    setShow={setShowPassword}
                    placeholder="Minimum 8 characters"
                    onInput={clear}
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 uppercase mb-2">
                    Confirm New Password
                  </label>
                  <PasswordBox
                    value={confirmPassword}
                    setValue={setConfirmPassword}
                    show={showConfirm}
                    setShow={setShowConfirm}
                    placeholder="Re-enter your password"
                    onInput={clear}
                  />
                </div>
                {message}
                <button
                  disabled={busy}
                  className="w-full bg-sky-900 hover:bg-sky-800 disabled:bg-slate-400 text-white py-3 rounded-xl text-base font-bold uppercase tracking-wide transition"
                >
                  {busy ? "Updating..." : "Set New Password"}
                </button>
                <button
                  type="button"
                  onClick={backToLogin}
                  className="w-full text-base font-bold text-sky-900 underline"
                >
                  Back to Login
                </button>
              </form>
            ) : forgotMode ? (
              <div className="space-y-5">
                <div>
                  <p className="text-sm text-emerald-600 font-bold uppercase tracking-widest">
                    Account recovery
                  </p>
                  <h2 className="text-3xl font-black text-slate-900 mt-2">
                    Reset Password
                  </h2>
                  <p className="text-base text-slate-500 mt-2">
                    Enter your email and verify the OTP sent to it.
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 uppercase mb-2">
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      clear();
                    }}
                    className="w-full px-4 py-3 border border-slate-300 rounded-xl bg-slate-50 text-base outline-none focus:ring-2 focus:ring-sky-200 focus:border-sky-700"
                    placeholder="Enter your email"
                  />
                </div>
                {!otpSent ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={sendResetOtp}
                    className="w-full bg-sky-900 hover:bg-sky-800 disabled:bg-slate-400 text-white py-3 rounded-xl text-base font-bold uppercase tracking-wide"
                  >
                    {busy ? "Sending..." : "Send OTP"}
                  </button>
                ) : (
                  <>
                    <div>
                      <label className="block text-sm font-bold text-slate-700 uppercase mb-2">
                        6-Digit OTP
                      </label>
                      <input
                        inputMode="numeric"
                        maxLength={6}
                        value={otp}
                        onChange={(e) => {
                          setOtp(e.target.value.replace(/\D/g, ""));
                          clear();
                        }}
                        className="w-full px-4 py-3 border border-slate-300 rounded-xl bg-slate-50 text-base tracking-[0.4em] text-center outline-none focus:ring-2 focus:ring-sky-200 focus:border-sky-700"
                        placeholder="000000"
                      />
                    </div>
                    <div className="flex gap-3">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={verifyResetOtp}
                        className="flex-1 bg-sky-900 text-white py-3 rounded-xl text-base font-bold uppercase"
                      >
                        {busy ? "Verifying..." : "Verify OTP"}
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={sendResetOtp}
                        className="flex-1 border border-slate-300 text-slate-700 py-3 rounded-xl text-base font-bold uppercase"
                      >
                        Resend OTP
                      </button>
                    </div>
                  </>
                )}
                {message}
                <button
                  type="button"
                  onClick={backToLogin}
                  className="w-full text-base font-bold text-sky-900 underline"
                >
                  Back to Login
                </button>
              </div>
            ) : (
              <form onSubmit={handleLogin} className="space-y-6">
                <div>
                  <p className="text-sm text-emerald-600 font-bold uppercase tracking-widest">
                    Welcome back
                  </p>
                  <h2 className="text-3xl xl:text-4xl font-black text-slate-900 mt-2">
                    Sign in to Drishti AI
                  </h2>
                  <p className="text-base text-slate-500 mt-2">
                    Access your secure document verification workspace.
                  </p>
                  <div className="auth-secure-note mt-4"><ShieldCheck size={15} /><span>Secure sign-in • forensic workspace • audit-ready results</span><ArrowRight size={14} /></div>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-700 uppercase tracking-wide">
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      clear();
                    }}
                    className="w-full px-4 py-3.5 border border-slate-300 rounded-xl bg-slate-50 text-base outline-none focus:ring-2 focus:ring-sky-200 focus:border-sky-700 transition"
                    placeholder="Enter your email"
                    autoComplete="email"
                  />
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-700 uppercase tracking-wide">
                    Password
                  </label>
                  <PasswordBox
                    value={password}
                    setValue={setPassword}
                    show={showPassword}
                    setShow={setShowPassword}
                    placeholder="Enter your password"
                    onInput={clear}
                  />
                </div>

                {message}

                <div className="flex items-center justify-between gap-4">
                  <label className="flex items-center gap-2 text-sm text-slate-500">
                    <input
                      type="checkbox"
                      className="w-4 h-4 accent-sky-900 rounded"
                    />
                    Remember me
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setForgotMode(true);
                      clear();
                      setOtpSent(false);
                      setOtp("");
                    }}
                    className="text-sm font-semibold text-sky-900 hover:text-emerald-700"
                  >
                    Forgot Password?
                  </button>
                </div>

                <button
                  disabled={busy}
                  className="w-full bg-sky-900 hover:bg-sky-800 disabled:bg-slate-400 text-white py-3.5 rounded-xl text-base font-bold uppercase tracking-wide shadow-md transition"
                >
                  {busy ? "Signing In..." : "Login"}
                </button>

                <div className="relative py-1">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-slate-200" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="bg-white px-3 text-xs font-bold text-slate-400 uppercase tracking-widest">
                      New to Drishti AI?
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => navigate("/create-account")}
                  className="w-full border border-sky-900 text-sky-900 hover:bg-sky-50 py-3 rounded-xl text-base font-bold uppercase tracking-wide transition"
                >
                  Create Account
                </button>
              </form>
            )}

            <p className="text-xs text-center text-slate-400 mt-8 leading-relaxed">
              DRISHTI AI: SCREENING EVIDENCE & FORENSIC VERIFICATION. <br />
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
