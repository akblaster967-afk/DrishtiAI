import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Activity, FileSearch2, ShieldCheck, Sparkles, UserRoundCheck } from "lucide-react";

const capitalizeFirst = (v) => (v ? v.charAt(0).toUpperCase() + v.slice(1) : v);

const formatDobDisplay = (value = "") => {
  const raw = String(value || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const [yyyy, mm, dd] = raw.split("-");
    return `${dd}/${mm}/${yyyy}`;
  }
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
};

const dobForApi = (value = "") => {
  const raw = String(value || "").trim();
  const match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : raw;
};

const DOCUMENT_CONFIG = {
  PASSPORT: {
    label: "Passport",
    requiresName: true,
    requiresDob: true,
    requiresDocumentNumber: true,
  },

  VISA: {
    label: "Visa",
    requiresName: true,
    requiresDob: true,
    requiresDocumentNumber: true,
    numberLabel: "Visa Number",
    numberPlaceholder: "e.g. IN-AB1234567",
  },

  AADHAAR: {
    label: "Aadhaar Card",
    requiresName: true,
    requiresDob: true,
    requiresDocumentNumber: true,
  },

  PAN: {
    label: "PAN Card",
    requiresName: true,
    requiresDob: false,
    requiresDocumentNumber: true,
  },

  COLLEGE_ID: {
    label: "College ID Card",
    requiresName: true,
    requiresDob: false,
    requiresDocumentNumber: true,
  },

  DRIVING_LICENSE: {
    label: "Driving License",
    requiresName: true,
    requiresDob: true,
    requiresDocumentNumber: true,
  },
};

const FACE_CAPTURE_DOCUMENT_TYPES = new Set([
  "PASSPORT",
  "VISA",
  "AADHAAR",
  "PAN",
  "DRIVING_LICENSE",
  "COLLEGE_ID",
]);

const IDENTITY_LABELS = {
  name: "Name",
  dob: "Date of Birth",
  document_number: "Document Number",
};

const ANALYSIS_STEPS = [
  ["Reading document", "OCR and image normalization"],
  ["Extracting fields", "Document-specific field rules"],
  ["Checking consistency", "Dates, identifiers and template structure"],
  ["Checking document integrity", "Strict document verification"],
  ["Checking synthetic signals", "Supporting visual consistency screen"],
  ["Building evidence report", "Risk fusion and explainable findings"],
];

export default function ForensicDeepDive() {
  const navigate = useNavigate();
  const location = useLocation();

  const currentUserId = sessionStorage.getItem("uniqueId") || "";
  const [reverificationContext, setReverificationContext] = useState(() => {
    try {
      const raw = sessionStorage.getItem("reverificationContext");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  const isExistingUser = /^\d{10}$/.test(currentUserId);

  const [userProfile, setUserProfile] = useState(null);

  const [loadingProfile, setLoadingProfile] = useState(false);

  const [idType, setIdType] = useState(() => location.state?.idType || "PASSPORT");

  const [idNumber, setIdNumber] = useState("");

  const [referenceName, setReferenceName] = useState(() => location.state?.referenceName || "");

  const [referenceDob, setReferenceDob] = useState("");

  const [selectedFile, setSelectedFile] = useState(null);
  const [screeningMode, setScreeningMode] = useState(() => location.state?.screeningMode || "SINGLE_DOCUMENT");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const motionCanvasRef = useRef(null);
  const cameraStreamRef = useRef(null);
  const motionTimerRef = useRef(null);
  const previousMotionFrameRef = useRef(null);
  const motionValuesRef = useRef([]);
  const livenessFramesRef = useRef([]);
  const [cameraStatus, setCameraStatus] = useState("idle");
  const [livenessStatus, setLivenessStatus] = useState("idle");
  const [livenessScore, setLivenessScore] = useState(0);
  const [livenessSamples, setLivenessSamples] = useState(0);
  const [capturedFace, setCapturedFace] = useState("");
  const [captureId, setCaptureId] = useState(null);
  const [cameraError, setCameraError] = useState("");

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState(0);

  const [error, setError] = useState("");

  const documentConfig = DOCUMENT_CONFIG[idType] || DOCUMENT_CONFIG.PASSPORT;

  const faceCaptureRequired =
    screeningMode === "REFERENCE_FORM" && FACE_CAPTURE_DOCUMENT_TYPES.has(idType);

  useEffect(() => {
    if (!reverificationContext?.existingDocumentId) return;
    setIdType(String(reverificationContext.idType || idType).toUpperCase());
    setIdNumber(String(reverificationContext.documentNumber || ""));
    setReferenceName(String(reverificationContext.existingFullName || ""));
    setReferenceDob(formatDobDisplay(String(reverificationContext.existingDob || "")));
    setScreeningMode("REFERENCE_FORM");
  }, []);

  const stopLivenessMonitor = () => {
    if (motionTimerRef.current) {
      window.clearInterval(motionTimerRef.current);
      motionTimerRef.current = null;
    }
    previousMotionFrameRef.current = null;
  };

  const resetLiveness = () => {
    stopLivenessMonitor();
    motionValuesRef.current = [];
    livenessFramesRef.current = [];
    setLivenessStatus("idle");
    setLivenessScore(0);
    setLivenessSamples(0);
  };

  const sampleLivenessFrame = () => {
    const video = videoRef.current;
    const motionCanvas = motionCanvasRef.current;
    if (!video || !motionCanvas || video.readyState < 2 || !video.videoWidth) return;
    const context = motionCanvas.getContext("2d", { willReadFrequently: true });
    if (!context) return;
    motionCanvas.width = 96;
    motionCanvas.height = 72;
    context.drawImage(video, 0, 0, 96, 72);
    const current = context.getImageData(10, 8, 76, 56).data;
    const gray = new Float32Array(current.length / 4);
    for (let i = 0, j = 0; i < current.length; i += 4, j += 1) {
      gray[j] = current[i] * 0.299 + current[i + 1] * 0.587 + current[i + 2] * 0.114;
    }
    if (previousMotionFrameRef.current) {
      let total = 0;
      for (let i = 0; i < gray.length; i += 1) {
        total += Math.abs(gray[i] - previousMotionFrameRef.current[i]);
      }
      const score = (total / gray.length / 255) * 100;
      motionValuesRef.current = [...motionValuesRef.current.slice(-11), score];
      const average = motionValuesRef.current.reduce((sum, value) => sum + value, 0) / motionValuesRef.current.length;
      setLivenessScore(Math.round(average * 100) / 100);
      setLivenessSamples(motionValuesRef.current.length);
      if (average >= 0.8 && motionValuesRef.current.filter((value) => value >= 0.8).length >= 2) {
        setLivenessStatus("passed");
      }
    }
    previousMotionFrameRef.current = gray;
    const miniFrame = motionCanvas.toDataURL("image/jpeg", 0.45);
    livenessFramesRef.current = [...livenessFramesRef.current.slice(-7), miniFrame];
  };

  const startLivenessMonitor = () => {
    stopLivenessMonitor();
    motionValuesRef.current = [];
    livenessFramesRef.current = [];
    previousMotionFrameRef.current = null;
    setLivenessStatus("checking");
    setLivenessScore(0);
    setLivenessSamples(0);
    motionTimerRef.current = window.setInterval(sampleLivenessFrame, 220);
  };

  const stopCamera = () => {
    stopLivenessMonitor();
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  };

  const startCamera = async () => {
    setError("");
    setCameraError("");

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("unsupported");
      setCameraError("This browser does not support camera capture.");
      return;
    }

    try {
      stopCamera();
      setCapturedFace("");
      setCaptureId(null);
      resetLiveness();
      setCameraStatus("starting");

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "user" },
          width: { ideal: 720 },
          height: { ideal: 540 },
        },
        audio: false,
      });

      cameraStreamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraStatus("ready");
      startLivenessMonitor();
    } catch (cameraError) {
      console.error("Camera access error:", cameraError);
      stopCamera();
      setCameraStatus("denied");
      setCameraError(
        cameraError?.name === "NotAllowedError"
          ? "Camera permission was blocked. Allow camera access and click Start Capture again."
          : "Unable to open the camera. Please check that your camera is available.",
      );
    }
  };

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  useEffect(() => {
    if (!isExistingUser) {
      return;
    }

    let cancelled = false;

    const loadProfile = async () => {
      setLoadingProfile(true);

      try {
        const response = await fetch("/api/users/me", {
          credentials: "include",
        });

        const result = await response.json();

        if (!response.ok) {
          throw new Error(
            result.detail || result.message || "Unable to load user profile.",
          );
        }

        if (cancelled) {
          return;
        }

        const profile = result.user || null;

        setUserProfile(profile);

        if (profile?.fullName && !referenceName.trim()) {
          setReferenceName(profile.fullName);
        }

        if (profile?.dateOfBirth && !referenceDob.trim()) {
          setReferenceDob(formatDobDisplay(profile.dateOfBirth));
        }
      } catch (profileError) {
        if (!cancelled) {
          console.error("Unable to load profile:", profileError);
        }
      } finally {
        if (!cancelled) {
          setLoadingProfile(false);
        }
      }
    };

    loadProfile();

    return () => {
      cancelled = true;
    };
  }, [isExistingUser]);

  const handleIdTypeChange = (event) => {
    const nextType = event.target.value;

    setIdType(nextType);

    const nextConfig = DOCUMENT_CONFIG[nextType];

    if (!nextConfig?.requiresDob) {
      setReferenceDob("");
    }

    setIdNumber("");
    setError("");

    
    stopCamera();
    setCapturedFace("");
    setCaptureId(null);
    resetLiveness();
    setCameraStatus("idle");
    setCameraError("");
  };

  const startNewUser = async () => {
    try {
      await fetch("/api/user-logout", {
        method: "POST",
        credentials: "include",
      });
    } catch {}

    sessionStorage.removeItem("userEmail");
    sessionStorage.removeItem("uniqueId");
    sessionStorage.removeItem("latestAnalysisResult");
    window.location.reload();
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setError("");
  };

  const handleScreeningModeChange = (mode) => {
    setScreeningMode(mode);
    setError("");
    if (mode !== "REFERENCE_FORM") {
      stopCamera();
      setCapturedFace("");
      setCaptureId(null);
      resetLiveness();
      setCameraStatus("idle");
      setCameraError("");
    }
  };

  const handleCapture = async () => {
    setError("");
    setCameraError("");

    const video = videoRef.current;
    const canvas = canvasRef.current;

    if (livenessStatus !== "passed") {
      setCameraError("Live check not passed yet. Slowly move your head left and right for about 2 seconds, then capture.");
      return;
    }

    if (!video || !canvas || video.readyState < 2) {
      setError(
        "Camera is not ready. Please click Start Capture and try again.",
      );
      return;
    }

    const width = video.videoWidth || 720;
    const height = video.videoHeight || 540;
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");
    context.drawImage(video, 0, 0, width, height);

    const imageData = canvas.toDataURL("image/jpeg", 0.9);
    setCapturedFace(imageData);

    
    stopCamera();
    setCameraStatus("captured");

    try {
      const response = await fetch("/api/face-captures", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageData, livenessFrames: livenessFramesRef.current }),
      });

      const text = await response.text();
      let result = {};
      try {
        result = text ? JSON.parse(text) : {};
      } catch {
        result = {};
      }

      if (!response.ok) {
        throw new Error(
          result.detail || result.message || "Unable to save camera capture.",
        );
      }

      setCaptureId(result.capture?.id || null);
    } catch (captureError) {
      console.error("Camera capture save error:", captureError);
      setCaptureId(null);
      setError(
        captureError.message ||
          "The photo was captured, but the server could not save it.",
      );
    }
  };

  useEffect(() => {
    if (!isAnalyzing) {
      setAnalysisStep(0);
      return undefined;
    }
    const timer = window.setInterval(() => {
      setAnalysisStep((current) => Math.min(current + 1, ANALYSIS_STEPS.length - 1));
    }, 1100);
    return () => window.clearInterval(timer);
  }, [isAnalyzing]);

  useEffect(() => {
    document.body.style.overflow = isAnalyzing ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isAnalyzing]);

  const validateForm = () => {
    if (!selectedFile) {
      return "Please select the document to screen.";
    }

    if (screeningMode === "SINGLE_DOCUMENT") {
      return null;
    }

    if (faceCaptureRequired && !capturedFace) {
      return "Please capture a face photo before verification.";
    }

    if (documentConfig.requiresName && !referenceName.trim()) {
      return "Please enter the document holder's name.";
    }
    if (documentConfig.requiresDob && !referenceDob.trim()) {
      return "Please enter the date of birth shown on the document.";
    }
    if (documentConfig.requiresDocumentNumber && !idNumber.trim()) {
      return "Please enter the document number.";
    }

    return null;
  };

  const normalizedDocumentNumber = useMemo(
    () => idNumber.trim().toUpperCase(),
    [idNumber],
  );

  const getCameraCapturePayload = () => ({
    captureId: captureId || null,
    capturedAt: new Date().toISOString(),
    source: "BROWSER_CAMERA",
    fileUrl: captureId
      ? `/api/users/${encodeURIComponent(currentUserId)}/face-captures/${encodeURIComponent(captureId)}/file`
      : null,
    biometricComparison: faceCaptureRequired ? "PENDING" : "NOT_REQUIRED",
    livenessStatus: faceCaptureRequired ? (captureId ? "PASSED" : livenessStatus.toUpperCase()) : "NOT_REQUIRED",
    motionScore: livenessScore,
    motionSamples: livenessSamples,
  });

  const openAnalysisResult = (payload) => {
    sessionStorage.setItem(
      "latestAnalysisResult",
      JSON.stringify({
        ...payload,
        documentConfig,
      }),
    );
    navigate("/analysis-result");
  };

  const handleAnalyze = async (event) => {
    event.preventDefault();

    setError("");

    const validationError = validateForm();

    if (validationError) {
      setError(validationError);
      return;
    }

    setIsAnalyzing(true);
    setAnalysisStep(0);

    try {
      fetch("/api/audit-events", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          eventType: "DOCUMENT_VERIFICATION_ATTEMPT",
          status: "STARTED",
          details: {
            idType,
            screeningMode,
            documentNumber: normalizedDocumentNumber || null,
            cameraCaptured: Boolean(capturedFace),
          },
        }),
      }).catch(() => {});

      const existingUserId = sessionStorage.getItem("uniqueId") || "";

      const formData = new FormData();

      formData.append("file", selectedFile);

      formData.append("id_type", idType);
      formData.append("screening_mode", screeningMode);
      formData.append(
        "reference_name",
        screeningMode === "REFERENCE_FORM" && documentConfig.requiresName ? referenceName.trim() : "",
      );

      formData.append(
        "reference_dob",
        screeningMode === "REFERENCE_FORM" && documentConfig.requiresDob ? referenceDob.trim() : "",
      );

      formData.append(
        "reference_document_number",
        screeningMode === "REFERENCE_FORM" ? normalizedDocumentNumber : "",
      );

      formData.append(
        "user_unique_id",
        /^\d{10}$/.test(existingUserId) ? existingUserId : "",
      );

      formData.append(
        "capture_id",
        screeningMode === "REFERENCE_FORM" && faceCaptureRequired && captureId ? String(captureId) : "",
      );

      formData.append(
        "reverify_existing_document_id",
        reverificationContext?.existingDocumentId ? String(reverificationContext.existingDocumentId) : "",
      );
      formData.append(
        "allow_reverification",
        reverificationContext?.existingDocumentId ? "1" : "0",
      );

      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
        credentials: "include",
      });

      const text = await response.text();

      let result = {};

      try {
        result = text ? JSON.parse(text) : {};
      } catch {
        throw new Error("Server returned an invalid response.");
      }

      if (response.status === 409 && result?.duplicate) {
        openAnalysisResult({
          analysisResult: null,
          storageResult: null,
          cameraCapture: getCameraCapturePayload(),
          duplicateInfo: {
            message: result.message || "This document is already stored.",
            documentNumber: result.documentNumber || normalizedDocumentNumber,
            existingDocumentNumber: result.existingDocumentNumber || normalizedDocumentNumber,
            existingDocumentId: result.existingDocumentId || null,
            existingFullName: result.existingFullName || "",
            existingDob: result.existingDob || "",
            canUpdate: result.canUpdate === true,
            idType: result.idType || idType,
            detail: result.detail || "",
          },
        });

        return;
      }

      if (response.status === 422 && result?.dataStored === false) {
        const rejectedResult = {
          ...result,

          extracted_fields: result.extractedFields || {},
          extractedFields: result.extractedFields || {},

          identity_analysis: result.identityAnalysis || {},
          identityAnalysis: result.identityAnalysis || {},

          quality_analysis: result.qualityAnalysis || {},
          qualityAnalysis: result.qualityAnalysis || {},

          suspicious_indicators: result.suspiciousIndicators || {},
          suspiciousIndicators: result.suspiciousIndicators || {},

          aiDocumentAnalysis: result.aiDocumentAnalysis || {},
          documentVerification: result.documentVerification || {},

          risk_assessment: result.riskAssessment || {
            score: result.riskScore ?? "N/A",

            risk_band: result.riskBand || "High Risk",
          },

          ocr: {
            confidence: result.ocrConfidence ?? "N/A",

            text: result.ocrText || "",
          },
        };

        const rejectionStatus = String(result.status || "SCREENING_REJECTED").toUpperCase();
        const rejectedStorage = {
          success: false,
          dataStored: false,
          status: rejectionStatus,
          message:
            result.message ||
            "Document was not stored because a required verification gate did not pass.",
          riskScore: result.riskScore ?? null,
          riskBand: result.riskBand || "UNKNOWN",
          storageDecision: "NOT_STORED",
          finalDecision: result.finalDecision || null,
          verificationExplanation: result.verificationExplanation || result.finalDecision?.verificationExplanation || null,
        };

        openAnalysisResult({
          analysisResult: {
            ...rejectedResult,
            cameraCapture: result.cameraCapture || getCameraCapturePayload(),
          },
          storageResult: rejectedStorage,
          duplicateInfo: null,
        });

        return;
      }

      if (!response.ok) {
        throw new Error(
          result.detail ||
            result.error ||
            result.message ||
            "Document analysis failed.",
        );
      }

      const userStorage = result.userStorage || result.screening || {};

      const dataStored = userStorage.dataStored === true;

      const riskScore =
        userStorage.riskScore ?? result.risk_assessment?.score ?? null;

      const riskBand =
        userStorage.riskBand || result.risk_assessment?.risk_band || "LOW";

      const storageDecision = String(userStorage.storageDecision || "").toUpperCase();
      const pendingReview = dataStored && storageDecision === "PENDING_REVIEW";

      const nextStorageResult = {
        success: dataStored,
        dataStored,
        status: pendingReview ? "DOCUMENT_ADDED_PENDING_REVIEW" : dataStored ? "DOCUMENT_ADDED" : "DOCUMENT_NOT_STORED",
        storageDecision: storageDecision || null,
        message:
          userStorage.message ||
          (pendingReview
            ? "The document was stored, but automatic verification is pending manual review because evidence confidence is limited."
            : dataStored
              ? "The document was verified and added to your account."
              : "The document was not stored."),
        riskScore,
        riskBand,
        finalDecision: result.finalDecision || userStorage.finalDecision || null,
        authenticityStatus: result.authenticityStatus || userStorage.authenticityStatus || result.risk_assessment?.authenticity_status || null,
      };

      if (reverificationContext?.existingDocumentId) {
        sessionStorage.removeItem("reverificationContext");
        setReverificationContext(null);
      }

      openAnalysisResult({
        analysisResult: result,
        storageResult: nextStorageResult,
        duplicateInfo: null,
      });
    } catch (analysisError) {
      console.error("Document analysis error:", analysisError);

      setError(analysisError.message || "Unable to analyze the document.");
    } finally {
      setIsAnalyzing(false);
      setAnalysisStep(0);
    }
  };

  const getDocumentPlaceholder = () => {
    switch (idType) {
      case "AADHAAR":
        return "e.g. 1234 5678 9012";

      case "PAN":
        return "e.g. ABCDE1234F";

      case "COLLEGE_ID":
        return "e.g. COL-2026-00125";

      case "PASSPORT":
        return "e.g. P1234567";

      case "VISA":
        return documentConfig.numberPlaceholder || "e.g. IN-AB1234567";

      case "DRIVING_LICENSE":
        return "e.g. UP32 20260012345";

      default:
        return "Enter document number";
    }
  };

  const formatValue = (value) => {
    if (value === null || value === undefined || value === "") {
      return "N/A";
    }

    if (typeof value === "object") {
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    }

    return String(value);
  };

  const getStatusClass = (status) => {
    const value = String(status || "").toUpperCase();

    if (
      value.includes("MISMATCH") ||
      value.includes("HIGH") ||
      value.includes("FAILED") ||
      value.includes("REJECTED")
    ) {
      return "bg-red-100 text-red-800 border-red-300";
    }

    if (
      value.includes("PARTIAL") ||
      value.includes("MEDIUM") ||
      value.includes("REVIEW") ||
      value.includes("ADDED")
    ) {
      return "bg-amber-100 text-amber-800 border-amber-300";
    }

    if (
      value.includes("MATCH") ||
      value.includes("LOW") ||
      value.includes("SUCCESS") ||
      value.includes("VERIFIED") ||
      value.includes("CREATED") ||
      value.includes("STORED")
    ) {
      return "bg-emerald-100 text-emerald-800 border-emerald-300";
    }

    return "bg-slate-100 text-slate-700 border-slate-300";
  };

  return (
    <div className="site-page w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
      {reverificationContext?.existingDocumentId && (
        <section className="drishti-clear-box mb-4">
          <Activity size={18} />
          <div>
            <p className="font-black">Update / re-verification mode</p>
            <p className="text-xs mt-1">This stored document will be re-verified once. A successful same-account update refreshes the stored record; any later normal attempt is blocked as a duplicate.</p>
          </div>
        </section>
      )}
      <div className="drishti-forensic-hero text-white mb-5">
        <div className="drishti-forensic-orb orb-one" />
        <div className="drishti-forensic-orb orb-two" />
        <div className="relative z-10">
          <div className="flex flex-col xl:flex-row xl:items-end xl:justify-between gap-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="drishti-pill drishti-pill-dark"><Sparkles size={13} /> AI DOCUMENT FORENSICS</span>
                <span className="drishti-pill drishti-pill-dark">7 evidence layers</span>
                <span className="drishti-pill drishti-pill-dark">No original required in screening mode</span>
              </div>
              <h1 className="text-3xl md:text-4xl font-black mt-4 tracking-tight">Find what changed. Explain why it matters.</h1>
              <p className="text-sm md:text-base text-slate-300 mt-3 max-w-4xl leading-6">
                Drishti AI screens document evidence and verifies the claimed identity when known details and a live face are available.
              </p>
            </div>
            <div className="hidden xl:flex items-center gap-2 text-xs text-slate-300 font-bold">
              <ShieldCheck size={17} className="text-emerald-300" /> Explainable evidence &nbsp;•&nbsp; not a legal authenticity certificate
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-7">
            {[
              ["SINGLE_DOCUMENT", "Authenticity Screening", "One document • no original needed", FileSearch2],
              ["REFERENCE_FORM", "Identity Verification", "Known details + live face", UserRoundCheck],
            ].map(([mode, title, subtitle, Icon]) => (
              <button
                key={mode}
                type="button"
                onClick={() => handleScreeningModeChange(mode)}
                className={`drishti-mode-card ${screeningMode === mode ? "active" : ""}`}
              >
                <div className="drishti-mode-icon"><Icon size={20} /></div>
                <div className="min-w-0"><div className="text-sm font-black">{title}</div><div className="text-[11px] text-slate-400 mt-1">{subtitle}</div></div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="drishti-explainer-strip">
        <div className="flex items-start gap-3"><div className="drishti-strip-icon"><ShieldCheck size={18} /></div><div><p className="text-sm font-black text-slate-900">{screeningMode === "SINGLE_DOCUMENT" ? "Authenticity screening asks: does this document show signs of manipulation or synthetic generation?" : "Identity verification asks: do the document details and document photo match the claimed person?"}</p><p className="text-xs text-slate-500 mt-1">This page will never silently treat a missing issuer API as a successful government verification.</p></div></div>
        <a href="/how-it-works" className="text-xs font-black text-sky-800 hover:text-sky-600">How the evidence is combined →</a>
      </div>
      <div className="forensic-workspace">
        <div className="forensic-form-card bg-white border border-slate-300 rounded-lg p-5 shadow-sm">
          <div className="border-b pb-3 mb-4">
            <h2 className="text-base font-bold text-slate-800 uppercase">
              Document Verification
            </h2>

          <p className="text-xs text-slate-500 mt-1">
              Enter only information applicable to the selected document.
            </p>
          </div>

          <form
            id="document-verification-form"
            onSubmit={handleAnalyze}
            className="space-y-4"
          >
            <div>
              <label className="block text-sm font-bold text-slate-700 uppercase mb-1">
                Document Type
              </label>

              <select
                value={idType}
                onChange={handleIdTypeChange}
                className="w-full bg-slate-50 border border-slate-300 rounded px-3 py-2 text-base font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-900"
              >
                <option value="PASSPORT">Passport</option>

                <option value="VISA">Visa</option>

                <option value="AADHAAR">Aadhaar Card</option>

                <option value="PAN">PAN Card</option>

                <option value="COLLEGE_ID">College ID Card</option>

                <option value="DRIVING_LICENSE">Driving License</option>
              </select>
            </div>

            {screeningMode === "REFERENCE_FORM" && (
              <>
            {documentConfig.requiresName && (
              <div>
                <label className="block text-sm font-bold text-slate-700 uppercase mb-1">
                  Full Name
                </label>

                <input
                  type="text"
                  value={referenceName}
                  onChange={(event) =>
                    setReferenceName(capitalizeFirst(event.target.value))
                  }
                  placeholder="Name shown on the document"
                  disabled={isExistingUser && !!userProfile?.fullName}
                  className="w-full bg-slate-50 border border-slate-300 rounded px-3 py-2 text-base text-slate-900 disabled:bg-slate-100 disabled:text-slate-600"
                />

                {loadingProfile && (
                  <p className="text-xs text-slate-400 mt-1">
                    Loading your profile...
                  </p>
                )}
              </div>
            )}

            {documentConfig.requiresDob && (
              <div>
                <label className="block text-sm font-bold text-slate-700 uppercase mb-1">
                  Date of Birth
                </label>

                <input
                  type="text"
                  value={referenceDob}
                  onChange={(event) =>
                    setReferenceDob(formatDobDisplay(event.target.value))
                  }
                  placeholder="DD/MM/YYYY"
                  className="w-full bg-slate-50 border border-slate-300 rounded px-3 py-2 text-base font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-900"
                />
              </div>
            )}

            {documentConfig.requiresDocumentNumber && (
              <div>
                <label className="block text-sm font-bold text-slate-700 uppercase mb-1">
                  {documentConfig.numberLabel || "Document Number"}
                </label>

                <input
                  type="text"
                  value={idNumber}
                  onChange={(event) =>
                    setIdNumber(event.target.value.toUpperCase())
                  }
                  placeholder={getDocumentPlaceholder()}
                  className="w-full bg-slate-50 border border-slate-300 rounded px-3 py-2 text-base font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-900"
                />
              </div>
            )}

              </>
            )}

            <div>
              <label className="block text-sm font-bold text-slate-700 uppercase mb-1">
                Document File
              </label>

              <input
                type="file"
                accept=".jpg,.jpeg,.png,.pdf"
                onChange={handleFileChange}
                className="w-full text-sm bg-slate-50 border border-slate-300 rounded file:mr-3 file:py-2 file:px-3 file:border-0 file:bg-sky-900 file:text-white file:text-sm file:font-bold"
              />
            </div>

            {selectedFile && (
              <div className="bg-slate-50 border border-slate-200 rounded p-3">
                <p className="text-sm font-bold text-slate-800 break-all">Screening document: {selectedFile.name}</p>
                <p className="text-xs text-slate-500 mt-1">{(selectedFile.size / 1024).toFixed(1)} KB</p>
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded p-3 text-sm font-semibold text-red-700">
                {error}
              </div>
            )}
          </form>
        </div>

        <div className="forensic-camera-card">
          <div className="bg-white border border-slate-300 rounded-lg p-5 shadow-sm h-full flex flex-col">
            {faceCaptureRequired ? (
              <>
                <div className="flex items-center justify-between border-b pb-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-800 uppercase">
                      Camera &amp; Face Capture
                    </h2>
                    <p className="text-xs text-slate-500 mt-1">
                      Start the live check, slowly move your head left and right,
                      then capture only after the motion gate passes.
                    </p>
                  </div>
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded ${
                      cameraStatus === "captured"
                        ? "bg-emerald-100 text-emerald-800"
                        : cameraStatus === "ready"
                          ? "bg-sky-100 text-sky-800"
                          : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {cameraStatus === "captured"
                      ? "CAPTURED"
                      : cameraStatus === "ready"
                        ? "CAMERA OPEN"
                        : "CAMERA OFF"}
                  </span>
                </div>

                <div className="mt-4 flex justify-center">
                  <div className="relative w-full max-w-2xl aspect-[4/3] bg-slate-950 rounded-lg overflow-hidden border border-slate-300 shadow-inner">
                    <video
                      ref={videoRef}
                      autoPlay
                      muted
                      playsInline
                      onCanPlay={() => {
                        if (
                          cameraStatus === "ready" &&
                          videoRef.current?.paused
                        ) {
                          videoRef.current.play().catch(() => {});
                        }
                      }}
                      className={`absolute inset-0 w-full h-full object-contain bg-black ${cameraStatus === "ready" ? "block" : "hidden"}`}
                    />
                    {cameraStatus === "ready" && (
                      <div className="absolute inset-0 pointer-events-none">
                        <div className="absolute left-1/2 top-[18%] -translate-x-1/2 w-[38%] h-[58%] rounded-[45%] border-2 border-emerald-300/80 shadow-[0_0_0_9999px_rgba(15,23,42,0.22)]" />
                        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-slate-950/70 px-3 py-1.5 text-[11px] font-black text-white tracking-wide">Keep your full face inside the guide</div>
                      </div>
                    )}
                    {cameraStatus !== "ready" && capturedFace ? (
                      <img
                        src={capturedFace}
                        alt="Captured face"
                        className="absolute inset-0 w-full h-full object-cover"
                      />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center text-center">
                        <p className="text-white text-base font-bold uppercase tracking-wide">
                          Start Capture
                        </p>
                      </div>
                    )}

                    {cameraStatus === "starting" && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                        <div className="bg-white rounded px-4 py-3 text-sm font-bold text-slate-800 shadow">
                          Opening camera...
                        </div>
                      </div>
                    )}
                    <canvas ref={canvasRef} className="hidden" />
                    <canvas ref={motionCanvasRef} className="hidden" />
                  </div>
                </div>

                {cameraStatus === "ready" && (
                  <div className={`mt-3 rounded-xl border p-3 ${livenessStatus === "passed" ? "bg-emerald-50 border-emerald-200" : livenessStatus === "checking" ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-200"}`}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-black uppercase tracking-wide text-slate-700">Live motion check</p>
                        <p className="text-xs text-slate-500 mt-1">{livenessStatus === "passed" ? "Movement detected. You can capture now." : "Slowly move your head left and right for about 2 seconds."}</p>
                      </div>
                      <span className={`text-xs font-black px-2 py-1 rounded-full ${livenessStatus === "passed" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                        {livenessStatus === "passed" ? "PASSED" : "CHECKING"}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs font-semibold text-slate-500">
                      <span>Motion score: {livenessScore.toFixed(2)}%</span>
                      <span>Samples: {livenessSamples}</span>
                    </div>
                  </div>
                )}

                {cameraError && (
                  <div className="mt-3 bg-red-50 border border-red-200 rounded p-3 text-sm font-semibold text-red-700">
                    {cameraError}
                  </div>
                )}

                {capturedFace && (
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div
                      className={`${captureId ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"} border rounded p-3`}
                    >
                      <p
                        className={`text-xs font-bold uppercase ${captureId ? "text-emerald-700" : "text-red-700"}`}
                      >
                        {captureId ? "Capture saved" : "Capture rejected"}
                      </p>
                      <p
                        className={`text-sm mt-1 ${captureId ? "text-emerald-900" : "text-red-900"}`}
                      >
                        {captureId
                          ? "This captured face will be compared with the face detected in the uploaded document."
                          : "The server rejected this capture. Restart the live check and complete the motion step again."}
                      </p>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded p-3">
                      <p className="text-xs font-bold uppercase text-slate-500">
                        Verification Ready
                      </p>
                      <p className="text-sm font-semibold text-slate-800 mt-1">
                        {captureId
                          ? "Face capture is ready for secure comparison."
                          : "A valid face capture is required before analysis."}
                      </p>
                    </div>
                  </div>
                )}

                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {cameraStatus === "idle" ||
                  cameraStatus === "denied" ||
                  cameraStatus === "unsupported" ? (
                    <button
                      type="button"
                      onClick={startCamera}
                      className="sm:col-span-2 w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded text-sm font-bold uppercase transition-all"
                    >
                      Start Capture
                    </button>
                  ) : cameraStatus === "starting" ? (
                    <button
                      type="button"
                      disabled
                      className="sm:col-span-2 w-full bg-slate-400 text-white py-3 rounded text-sm font-bold uppercase"
                    >
                      Opening Camera...
                    </button>
                  ) : cameraStatus === "ready" ? (
                    <button
                      type="button"
                      onClick={handleCapture}
                      disabled={livenessStatus !== "passed"}
                      className="sm:col-span-2 w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 text-white py-3 rounded text-sm font-bold uppercase transition-all"
                    >
                      Capture
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={startCamera}
                        className="w-full bg-slate-700 hover:bg-slate-800 text-white py-3 rounded text-sm font-bold uppercase transition-all"
                      >
                        Retake
                      </button>

                      <button
                        type="submit"
                        form="document-verification-form"
                        disabled={isAnalyzing || !captureId}
                        className="w-full bg-sky-900 hover:bg-sky-800 disabled:bg-slate-400 text-white py-3 rounded text-sm font-bold uppercase transition-all"
                      >
                        {isAnalyzing ? "Analyzing..." : screeningMode === "SINGLE_DOCUMENT" ? "Run Forensic Screening" : "Analyze & Verify"}
                      </button>
                    </>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="border-b pb-3">
                    <h2 className="text-base font-bold text-slate-800 uppercase">
                    Single-Document Forensics
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    No trusted original is required. The pipeline checks OCR integrity, document-specific structure, template consistency and strict verification evidence.
                  </p>
                </div>

                <div className="flex-1 min-h-[360px] flex items-center justify-center text-center px-6">
                  <div>
                    <p className="text-base font-bold text-sky-900">
                      Ready for standalone forensic screening
                    </p>
                    <p className="text-sm text-slate-500 mt-2 max-w-lg">
                      This mode is not a duplicate of Identity Verification. It does not require known identity data or a live face; it is designed to screen a document when no original is available.
                    </p>
                  </div>
                </div>

                <button
                  type="submit"
                  form="document-verification-form"
                  disabled={isAnalyzing}
                  className="w-full bg-sky-900 hover:bg-sky-800 disabled:bg-slate-400 text-white py-3 rounded text-sm font-bold uppercase transition-all"
                >
                  {isAnalyzing ? "Analyzing..." : screeningMode === "SINGLE_DOCUMENT" ? "Run Forensic Screening" : "Analyze & Verify"}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {isAnalyzing && (
        <div className="drishti-analysis-overlay" role="status" aria-live="polite" aria-busy="true">
          <div className="drishti-analysis-panel">
            <div className="flex items-center justify-between gap-4">
              <div><p className="drishti-kicker text-cyan-300">DRISHTI AI IS WORKING</p><h2 className="text-xl font-black text-white mt-1">Running forensic evidence pipeline</h2></div>
              <div className="drishti-spinner"><Activity size={18} /></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-5">
              {ANALYSIS_STEPS.map(([title, subtitle], index) => (
                <div key={title} className={`drishti-analysis-step ${index < analysisStep ? "done" : index === analysisStep ? "current" : ""}`}>
                  <div className="drishti-analysis-step-dot">{index < analysisStep ? "✓" : index + 1}</div>
                  <div><p className="text-xs font-black">{title}</p><p className="text-[10px] text-slate-400 mt-1">{subtitle}</p></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
