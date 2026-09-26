import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BadgeCheck, Eye, EyeOff, Fingerprint, LockKeyhole, ScanText, ShieldCheck, Sparkles } from "lucide-react";

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
  try { result = text ? JSON.parse(text) : {}; } catch {}
  if (!response.ok) {
    const detail = result.detail || result.message;
    throw new Error(detail || `Server error (${response.status}). Please start the backend and try again.`);
  }
  return result;
}

const validEmail = (v) => /^\S+@\S+\.\S+$/.test(v.trim());
const capitalizeFirst = (v) => v ? v.charAt(0).toUpperCase() + v.slice(1) : v;
const passwordError = (v) => {
  if (!v) return "Enter your password.";
  if (v.length > 10) return "Password must be at most 10 characters.";
  if (v.length < 8) return "Password must be at least 8 characters.";
  if (!/^[A-Za-z0-9@]+$/.test(v)) return "Password may contain only letters, numbers and @.";
  if (!/[A-Z]/.test(v)) return "Password must contain at least 1 capital letter.";
  if (!/[a-z]/.test(v)) return "Password must contain at least 1 small letter.";
  if (!/[0-9]/.test(v)) return "Password must contain at least 1 number.";
  if (!/@/.test(v)) return "Password must contain @ as the symbol.";
  return "";
};

function PasswordInput({ value, onChange, disabled, placeholder }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        type={show ? "text" : "password"}
        value={value}
        disabled={disabled}
        onChange={onChange}
        className="w-full px-3 py-2.5 pr-11 border border-slate-300 rounded bg-slate-50 text-sm disabled:opacity-60"
        placeholder={placeholder}
        maxLength={10}
        autoComplete="new-password"
      />
      <button type="button" onClick={() => setShow(v => !v)} disabled={disabled} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-sky-900 cursor-pointer disabled:opacity-40" aria-label={show ? "Hide password" : "Show password"}>
        {show ? <EyeOff size={18} strokeWidth={2} /> : <Eye size={18} strokeWidth={2} />}
      </button>
    </div>
  );
}

export default function CreateAccount() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [verifiedToken, setVerifiedToken] = useState("");
  const [emailVerified, setEmailVerified] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [accountCreated, setAccountCreated] = useState(null);

  const clear = () => { setError(""); setSuccess(""); };

  const sendOtp = async () => {
    clear();
    const e = email.trim().toLowerCase();
    if (!validEmail(e)) return setError("Enter a valid email address.");
    setBusy(true);
    try {
      const r = await api("/auth/register/send-otp", { email: e });
      setEmail(e); setOtpSent(true); setSuccess(r.message || "A 6-digit OTP has been sent to your email.");
    } catch (err) {
      setError(err instanceof TypeError ? "Cannot connect to the Drishti AI server. Start the backend on port 8000 and try again." : err.message);
    }
    finally { setBusy(false); }
  };

  const verifyOtp = async () => {
    clear();
    if (!/^\d{6}$/.test(otp)) return setError("Enter the 6-digit OTP.");
    setBusy(true);
    try {
      const r = await api("/auth/register/verify-otp", { email: email.trim().toLowerCase(), otp });
      setVerifiedToken(r.verificationToken); setEmailVerified(true); setSuccess("Email verified successfully. Now create your password.");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const handleRegister = async (event) => {
    event.preventDefault(); clear();
    const e = email.trim().toLowerCase();
    const pe = passwordError(password);
    if (fullName.trim().length < 2) return setError("Enter a valid full name.");
    if (!validEmail(e)) return setError("Enter a valid email address.");
    if (!emailVerified || !verifiedToken) return setError("Verify your email with OTP first.");
    if (pe) return setError(pe);
    if (password !== confirmPassword) return setError("Passwords do not match.");
    setBusy(true);
    try {
      const r = await api("/auth/register", { fullName: fullName.trim(), email: e, password, verificationToken: verifiedToken });
      setSuccess("");
      setAccountCreated({
        message: r.message || "Account created successfully. You can now log in.",
        uniqueId: r.uniqueId || "",
      });
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const continueToLogin = () => {
    setAccountCreated(null);
    navigate("/login", { replace: true });
  };

  const message = error
    ? <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-xs font-semibold">{error}</div>
    : success
      ? <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded p-3 text-xs font-semibold">{success}</div>
      : null;

  return (
    <div className="auth-page min-h-screen bg-slate-200 flex items-center justify-center p-4 md:p-6">
      {accountCreated && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 p-7">
            <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-2xl font-black mx-auto">✓</div>
            <h2 className="text-2xl font-black text-slate-900 text-center mt-4">Account created successfully</h2>
            <p className="text-sm text-slate-600 text-center mt-2 leading-relaxed">{accountCreated.message}</p>
            {accountCreated.uniqueId && (
              <div className="mt-5 bg-sky-50 border border-sky-200 rounded-xl p-4 text-center">
                <p className="text-[11px] uppercase tracking-widest font-bold text-sky-700">Your Unique ID</p>
                <p className="font-mono text-2xl font-black text-sky-950 mt-1 tracking-widest">{accountCreated.uniqueId}</p>
                <p className="text-xs text-slate-500 mt-2">Keep this ID safe for your Drishti AI account.</p>
              </div>
            )}
            <button type="button" onClick={continueToLogin} className="w-full mt-6 bg-sky-900 hover:bg-sky-800 text-white py-3 rounded-xl text-sm font-bold uppercase tracking-wide">Continue to Login</button>
          </div>
        </div>
      )}

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
                  <p className="text-base font-bold">Secure account workspace</p>
                  <p className="text-xs text-slate-300 mt-1">Verify email, secure your account, then start screening.</p>
                </div>
                <span className="auth-live-badge"><span className="auth-live-dot" />READY</span>
              </div>
              <div className="auth-pipeline mt-5">
                <div><span><ScanText size={15} /></span><p>EMAIL</p></div><i />
                <div><span><Fingerprint size={15} /></span><p>SECURE</p></div><i />
                <div><span><Sparkles size={15} /></span><p>IDENTITY</p></div><i />
                <div><span><ShieldCheck size={15} /></span><p>START</p></div>
              </div>
              <div className="grid grid-cols-3 gap-3 mt-5">
                <div className="auth-feature-tile"><p className="text-emerald-300 text-lg font-black">01</p><p className="text-[10px] text-slate-300 mt-1">Email OTP</p></div>
                <div className="auth-feature-tile"><p className="text-emerald-300 text-lg font-black">02</p><p className="text-[10px] text-slate-300 mt-1">Password</p></div>
                <div className="auth-feature-tile"><p className="text-emerald-300 text-lg font-black">03</p><p className="text-[10px] text-slate-300 mt-1">Screening</p></div>
              </div>
              <div className="auth-trust-row mt-4"><LockKeyhole size={15} /><span>Secure workspace</span><span className="auth-trust-separator" /><BadgeCheck size={15} /><span>Ready to verify</span></div>
            </div>
          </div>
        </section>

        <section className="flex flex-col justify-center bg-white p-6 sm:p-7">
          <div className="max-w-md w-full mx-auto">
            <div className="auth-inline-card lg:hidden" aria-label="Drishti AI workspace">
              <div className="auth-inline-head">
                <div>
                  <p className="auth-inline-kicker">DRISHTI AI</p>
                  <p className="auth-inline-title">Secure account workspace</p>
                </div>
                <span className="auth-inline-status"><i /> READY</span>
              </div>
              <div className="auth-inline-pipeline"><span><b>EMAIL</b><em>Verify</em></span><i /><span><b>SECURE</b><em>Password</em></span><i /><span><b>IDENTITY</b><em>Ready</em></span><i /><span><b>START</b><em>Screen</em></span></div>
            </div>
            <div className="lg:hidden flex items-center gap-3 mb-8">
              <div className="w-11 h-11 rounded-xl bg-sky-900 text-emerald-400 flex items-center justify-center font-black">DA</div>
              <div>
                <p className="text-xl font-black text-sky-900">Drishti AI</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest">Secure account</p>
              </div>
            </div>

            <form onSubmit={handleRegister} className="space-y-5">
              <div className="mb-7">
                <p className="text-xs text-emerald-600 font-bold uppercase tracking-widest">Get started</p>
                <h2 className="text-3xl xl:text-4xl font-black text-slate-900 mt-2">Create your account</h2>
                <p className="text-sm text-slate-500 mt-2">Verify your email first, then create your password.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-2">Full Name</label>
                <input type="text" value={fullName} onChange={e => { setFullName(capitalizeFirst(e.target.value)); clear(); }} className="w-full px-4 py-3.5 border border-slate-300 rounded-xl bg-slate-50 text-sm outline-none focus:ring-2 focus:ring-sky-200 focus:border-sky-700" placeholder="Enter your full name" />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-2">Email Address</label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input type="email" value={email} disabled={emailVerified} onChange={e => { setEmail(e.target.value); setOtpSent(false); setEmailVerified(false); setVerifiedToken(""); clear(); }} className="flex-1 px-4 py-3.5 border border-slate-300 rounded-xl bg-slate-50 text-sm outline-none focus:ring-2 focus:ring-sky-200 focus:border-sky-700 disabled:bg-slate-100" placeholder="Enter your email" />
                  {!emailVerified && <button type="button" disabled={busy} onClick={sendOtp} className="sm:w-28 px-4 py-3 rounded-xl bg-sky-900 hover:bg-sky-800 text-white text-xs font-bold uppercase disabled:bg-slate-400">{otpSent ? "Resend" : "Verify"}</button>}
                </div>
                {emailVerified && <p className="text-xs text-emerald-600 font-semibold mt-2">✓ Email verified successfully</p>}
              </div>

              {otpSent && !emailVerified && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase mb-2">6-Digit OTP</label>
                  <div className="flex gap-2">
                    <input inputMode="numeric" maxLength={6} value={otp} onChange={e => { setOtp(e.target.value.replace(/\D/g, "")); clear(); }} className="flex-1 px-4 py-3 border border-slate-300 rounded-xl bg-slate-50 text-sm tracking-[0.35em] text-center outline-none focus:ring-2 focus:ring-sky-200 focus:border-sky-700" placeholder="000000" />
                    <button type="button" disabled={busy} onClick={verifyOtp} className="px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold uppercase">{busy ? "..." : "Verify OTP"}</button>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-2">Password</label>
                <PasswordInput value={password} disabled={!emailVerified} onChange={e => { setPassword(e.target.value); clear(); }} placeholder="Minimum 8 characters" />
                <p className="text-[10px] text-slate-500 mt-2">Minimum 8 characters with at least 1 capital, 1 small, 1 number and @.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-2">Confirm Password</label>
                <PasswordInput value={confirmPassword} disabled={!emailVerified} onChange={e => { setConfirmPassword(e.target.value); clear(); }} placeholder="Re-enter your password" />
              </div>

              {message}

              <button type="submit" disabled={busy || !emailVerified} className="w-full bg-sky-900 hover:bg-sky-800 disabled:bg-slate-400 text-white py-3.5 rounded-xl text-sm font-bold uppercase tracking-wide shadow-md">
                {busy ? "Creating..." : "Create Account"}
              </button>

              <div className="text-center pt-2">
                <button type="button" onClick={() => navigate("/login")} className="text-sm font-bold text-sky-900 hover:text-emerald-700 underline">
                  Already have an account? Login
                </button>
              </div>
            </form>

            <p className="text-[10px] text-center text-slate-400 mt-8 leading-relaxed">
              DRISHTI AI: SCREENING EVIDENCE, NOT A LEGAL AUTHENTICITY VERDICT
            </p>
          </div>
        </section>
      </div>
    </div>
  );

}
