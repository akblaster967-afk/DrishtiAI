import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleHelp,
  Copy,
  FileSearch2,
  Info,
  QrCode,
  ScanText,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserRoundCheck,
} from "lucide-react";

const FIELD_LABELS = {
  name: "Name",
  dob: "Date of Birth",
  document_number: "Document Number",
  address: "Address",
  issue_date: "Issue Date",
  validity_nt: "Validity (NT)",
  validity_tr: "Validity (TR)",
  relation_name: "Parent / Spouse Name",
  blood_group: "Blood Group",
  organ_donor: "Organ Donor",
  passing_year: "Passing Year",
  school_name: "School Name",
  expiry_date: "Expiry Date",
  nationality: "Nationality",
  gender: "Gender",
  father_name: "Father Name",
  mother_name: "Mother Name",
  surname: "Surname",
  given_names: "Given Names",
  place_of_birth: "Place of Birth",
  place_of_issue: "Place of Issue",
  institution_name: "Institution / College",
  course: "Course / Program",
  enrollment_number: "Enrollment Number",
  valid_until: "Valid Until",
  board: "Board",
  registration_number: "Registration Number",
  examination: "Examination",
};

const hasValue = (value) => {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
};

const isDisplayValue = (value) => {
  if (!hasValue(value)) return false;
  const normalized = String(value).trim().toUpperCase();
  return !["N/A", "NA", "NULL", "NONE", "UNAVAILABLE", "NOT_AVAILABLE", "NOT CONFIGURED"].includes(normalized);
};

const text = (value, fallback = "Not available") => {
  if (!hasValue(value)) return fallback;
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
};

const upper = (value) => String(value || "").trim().toUpperCase();

const displayMode = (mode) => {
  if (mode === "SINGLE_DOCUMENT") return "Single-document authenticity screening";
  if (mode === "REFERENCE_DOCUMENT") return "Reference-document comparison";
  if (mode === "REFERENCE_FORM") return "Identity verification";
  return "Document screening";
};

const DISPLAY_FIELDS_BY_TYPE = {
  PAN: ["name", "father_name", "dob", "document_number"],
  AADHAAR: ["name", "dob", "gender", "document_number", "address"],
  PASSPORT: ["name", "surname", "given_names", "dob", "document_number", "nationality", "gender", "issue_date", "expiry_date", "place_of_birth", "place_of_issue"],
  DRIVING_LICENSE: ["name", "dob", "document_number", "address", "gender", "relation_name", "father_name", "issue_date", "validity_nt", "validity_tr", "expiry_date"],
  COLLEGE_ID: ["name", "document_number", "erp_id", "dob", "course", "institution_name", "enrollment_number", "valid_until"],
  NATIONAL_ID: ["name", "dob", "gender", "document_number", "address"],
  VISA: ["name", "surname", "given_names", "document_number", "dob", "gender", "nationality", "issue_date", "expiry_date", "place_of_birth", "place_of_issue", "passport_number"],
};

const normalizeDocType = (value) => {
  const raw = upper(value).replace(/\s+/g, " ");
  const aliases = {
    "PAN CARD": "PAN",
    "AADHAAR CARD": "AADHAAR",
    "AADHAR": "AADHAAR",
    "AADHAR CARD": "AADHAAR",
    "DRIVING LICENSE": "DRIVING_LICENSE",
    "DRIVING LICENCE": "DRIVING_LICENSE",
    "DL": "DRIVING_LICENSE",
    "COLLEGE ID": "COLLEGE_ID",
    "COLLEGE ID CARD": "COLLEGE_ID",
    "STUDENT ID": "COLLEGE_ID",
    "STUDENT CARD": "COLLEGE_ID",
    "NATIONAL ID": "NATIONAL_ID",
    "NATIONAL IDENTIFICATION": "NATIONAL_ID",
    "VISA CARD": "VISA",
    "TOURIST VISA": "VISA",
    "ENTRY VISA": "VISA",
    "WORK VISA": "VISA",
    "STUDENT VISA": "VISA",
  };
  return aliases[raw] || raw;
};

const statusTone = (status) => {
  const value = upper(status);
  if (["HIGH", "MISMATCH", "FAILED", "REJECTED", "CONCERN", "LOW_SIMILARITY", "NOT_SIMILAR", "NOT_FOUND", "QUALITY_FAILED", "FRAMING_INVALID", "NOT_CENTERED", "COMPARISON_ERROR", "MULTIPLE_"].some((x) => value.includes(x))) {
    return {
      label: "Concern",
      className: "drishti-tone-danger",
      icon: ShieldAlert,
    };
  }
  if (["MEDIUM", "REVIEW", "PARTIAL", "ADDED", "CHANGED"].some((x) => value.includes(x))) {
    return {
      label: "Review",
      className: "drishti-tone-warning",
      icon: AlertTriangle,
    };
  }
  if (["LOW", "PASS", "MATCH", "MATCHED", "VERIFIED", "SUCCESS", "NORMAL", "NOT_DETECTED"].some((x) => value.includes(x))) {
    return {
      label: "Clear",
      className: "drishti-tone-success",
      icon: CheckCircle2,
    };
  }
  return {
    label: "Unavailable",
    className: "drishti-tone-neutral",
    icon: CircleHelp,
  };
};

const verdictFor = (riskBand, screeningMode, identityIssues, referenceComparison) => {
  if (screeningMode === "REFERENCE_DOCUMENT" && upper(referenceComparison?.band) === "HIGH") {
    return {
      title: "Significant differences found",
      subtitle: "The two copies contain changes that should be manually investigated.",
      tone: "danger",
      icon: ShieldAlert,
    };
  }
  if (identityIssues.some(({ value }) => upper(value?.status) === "MISMATCH")) {
    return {
      title: "Identity details do not match",
      subtitle: "The document fields do not agree with the supplied identity details.",
      tone: "danger",
      icon: UserRoundCheck,
    };
  }
  const band = upper(riskBand);
  if (band.includes("HIGH")) {
    return {
      title: "Detailed verification required",
      subtitle: "Multiple screening signals indicate that this document needs further review.",
      tone: "danger",
      icon: ShieldAlert,
    };
  }
  if (band.includes("MEDIUM") || band.includes("REVIEW")) {
    return {
      title: "Manual review recommended",
      subtitle: "Some evidence is inconsistent or inconclusive. Review the highlighted findings.",
      tone: "warning",
      icon: AlertTriangle,
    };
  }
  return {
    title: "No strong manipulation evidence found",
    subtitle: "The configured checks did not find a strong contradiction. This is not an issuer authenticity certificate.",
    tone: "success",
    icon: ShieldCheck,
  };
};

function ModuleCard({ module }) {
  const tone = statusTone(module?.status);
  const Icon = tone.icon;
  return (
    <div className={`drishti-module-card ${tone.className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={17} />
          <p className="font-black text-sm truncate">{module?.label || "Check"}</p>
        </div>
        <span className="drishti-mini-status">{tone.label}</span>
      </div>
      <p className="text-xs mt-2 leading-5 opacity-80">{text(module?.message, "No explanation was returned.")}</p>
    </div>
  );
}

function SignalCard({ signal }) {
  const tone = statusTone(signal?.severity);
  const Icon = tone.icon;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-slate-500" />
          <p className="text-xs font-black uppercase tracking-wide text-slate-500">
            {String(signal?.type || "Evidence").replaceAll("_", " ")}
          </p>
        </div>
        <span className={`text-[10px] font-black px-2 py-1 rounded-full border ${tone.className}`}>
          {upper(signal?.severity) || "INFO"}
        </span>
      </div>
      <p className="text-sm font-semibold text-slate-800 mt-2 leading-6">{text(signal?.message)}</p>
    </div>
  );
}

export default function AnalysisResult() {
  const navigate = useNavigate();
  const [payload] = useState(() => {
    try {
      const saved = sessionStorage.getItem("latestAnalysisResult");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [copied, setCopied] = useState(false);

  const analysisResult = payload?.analysisResult || null;
  const storageResult = payload?.storageResult || null;
  const duplicateInfo = payload?.duplicateInfo || null;
  const documentConfig = payload?.documentConfig || {};
  const screeningMode = analysisResult?.screeningMode || payload?.screeningMode || "REFERENCE_FORM";
  const risk = analysisResult?.risk_assessment || analysisResult?.riskAssessment || {};
  const riskScore = Number(risk?.score ?? analysisResult?.riskScore ?? storageResult?.riskScore ?? 0);
  const riskBand = risk?.risk_band || risk?.riskBand || analysisResult?.riskBand || storageResult?.riskBand || "UNKNOWN";
  const evidenceConfidence = analysisResult?.evidenceConfidence || risk?.analysis_confidence || "MEDIUM";
  const finalDecision = analysisResult?.finalDecision || storageResult?.finalDecision || {};
  const caseId = analysisResult?.caseId || analysisResult?.case_id || payload?.caseId || "";
  const crossDocument = analysisResult?.crossDocumentConsistency || {};
  const identity = analysisResult?.identity_analysis || analysisResult?.identityAnalysis || {};
  const ai = analysisResult?.aiDocumentAnalysis || analysisResult?.ai_document_analysis || {};
  const authenticityStatus = risk?.authenticity_status || analysisResult?.authenticityStatus || finalDecision?.authenticityStatus || "REVIEW_REQUIRED";
  const consistency = analysisResult?.documentConsistency || analysisResult?.document_consistency || {};
  const verification = analysisResult?.documentVerification || analysisResult?.document_verification || {};
  const referenceComparison = analysisResult?.referenceComparison || analysisResult?.reference_comparison || {};
  const qualityAnalysis = analysisResult?.qualityAnalysis || analysisResult?.quality_analysis || {};
  const suspiciousIndicators = analysisResult?.suspiciousIndicators || analysisResult?.suspicious_indicators || {};
  const integrityScreening = verification?.integrityScreening || verification?.integrity_screening || {};
  const issuer = verification?.issuerVerification || {};
  const qr = verification?.qrCheck || {};
  const sha = verification?.sha256 || "";
  const ocr = analysisResult?.ocr || {
    confidence: analysisResult?.ocrConfidence,
    text: analysisResult?.ocrText,
  };
  const documentPreview = analysisResult?.documentPreview || ocr?.documentPreview || payload?.documentPreview || "";
  const rawFace = payload?.faceComparison || analysisResult?.faceComparison || null;
  const cameraCapture = payload?.cameraCapture || analysisResult?.cameraCapture || {};
  const face = screeningMode === "REFERENCE_FORM" && rawFace && rawFace.status && upper(rawFace.status) !== "NOT_AVAILABLE" && upper(rawFace.status) !== "NOT_REQUIRED" ? rawFace : null;
  const extractedFields = analysisResult?.extracted_fields || analysisResult?.extractedFields || {};
  const extractionMeta = analysisResult?.extractionMeta || {};
  const fieldConfidence = extractionMeta?.fieldConfidence || {};

  const openIdentityVerification = () => {
    navigate("/forensic", {
      state: {
        screeningMode: "REFERENCE_FORM",
        idType: normalizeDocType(
          documentConfig?.idType || analysisResult?.idType || documentConfig?.label,
        ),
        referenceName: extractedFields.name || "",
      },
    });
  };

  const identityIssues = Object.entries(identity || {})
    .filter(([, value]) => value && typeof value === "object")
    .map(([field, value]) => ({ field, value }))
    .filter(({ field }) => field !== "address")
    .filter(({ value }) => {
      const status = upper(value?.status);
      return hasValue(value?.reference) || hasValue(value?.extracted) || status;
    })
    .filter(({ value }) => upper(value?.status) !== "MATCH" || !hasValue(value?.extracted));

  const riskReasons = (() => {
    const reasons = risk?.reasons ?? [];
    return Array.isArray(reasons) ? reasons.filter(Boolean) : [String(reasons)].filter(Boolean);
  })();

  const aiSignals = Array.isArray(ai?.signals) ? ai.signals : [];
  const verificationModules = Array.isArray(verification?.modules) ? verification.modules : [];
  const showAiSection = ai?.available !== false && isDisplayValue(ai?.band);
  const showEncodedSection = Boolean(sha || qr?.decoded || (isDisplayValue(qr?.status) && upper(qr?.status) !== "NOT_DETECTED") || (isDisplayValue(issuer?.status) && !["NOT_CONFIGURED", "UNAVAILABLE"].includes(upper(issuer?.status))));
  const showAdvancedEvidence = Boolean(isDisplayValue(ocr?.text) || hasValue(risk?.score_breakdown) || hasValue(risk?.verification_evidence));

  const evidenceModules = useMemo(() => {
    const modules = [...verificationModules].filter((item) => {
      const status = upper(item?.status);
      return status && !["UNAVAILABLE", "NOT_CONFIGURED", "NOT_REQUIRED", "N/A", "NA", "NULL"].includes(status);
    });
    if (!modules.some((item) => item?.id === "ocr")) {
      modules.unshift({
        id: "ocr",
        label: "OCR & field extraction",
        status: Number(ocr?.confidence || 0) >= 70 ? "PASS" : "REVIEW",
        message: `Readability confidence: ${text(ocr?.confidence, "0")}%`,
      });
    }
    if (!modules.some((item) => item?.id === "consistency")) {
      modules.push({
        id: "consistency",
        label: "Internal consistency",
        status: consistency?.band || "UNAVAILABLE",
        message: text(consistency?.summary, "Cross-field rules were evaluated."),
      });
    }
    if (screeningMode === "REFERENCE_DOCUMENT" && !modules.some((item) => item?.id === "reference")) {
      modules.push({
        id: "reference",
        label: "Reference comparison",
        status: referenceComparison?.band || "UNAVAILABLE",
        message: text(referenceComparison?.message, "Two-document comparison was completed."),
      });
    }
    if (screeningMode === "REFERENCE_FORM" && face && !modules.some((item) => item?.id === "biometric")) {
      modules.push({
        id: "biometric",
        label: "Face comparison",
        status: face?.verified ? "PASS" : face?.status || "REVIEW",
        message: text(face?.message, "Document photo was compared with the camera capture."),
      });
    }
    if (crossDocument?.available && !modules.some((item) => item?.id === "cross-document")) {
      modules.push({
        id: "cross-document",
        label: "Account consistency",
        status: crossDocument?.status || "REVIEW",
        message: text(crossDocument?.reasons?.[0], "Previously stored documents were checked for shared identity consistency."),
      });
    }
    return modules;
  }, [verificationModules, ocr, consistency, screeningMode, referenceComparison, face, crossDocument]);

  const fieldComparisonRows = useMemo(() => {
    if (screeningMode === "REFERENCE_DOCUMENT" && Array.isArray(referenceComparison?.fieldComparison?.comparisons)) {
      return referenceComparison.fieldComparison.comparisons.map((row) => ({
        field: row?.field,
        label: FIELD_LABELS[row?.field] || String(row?.field || "Field").replaceAll("_", " "),
        expected: row?.reference,
        actual: row?.suspect,
        status: upper(row?.status),
      }));
    }
    if (screeningMode === "REFERENCE_FORM") {
      return Object.entries(identity || {})
        .filter(([, value]) => value && typeof value === "object" && (
          hasValue(value?.reference) || hasValue(value?.extracted) || hasValue(value?.status)
        ))
        .map(([field, value]) => ({
          field,
          label: FIELD_LABELS[field] || field.replaceAll("_", " "),
          expected: value?.reference,
          actual: value?.extracted,
          status: upper(value?.status),
        }));
    }
    return (verification?.schemaChecks || []).map((row) => ({
      field: row?.field,
      label: row?.label || FIELD_LABELS[row?.field] || String(row?.field || "Field").replaceAll("_", " "),
      expected: "Document template",
      actual: row?.value,
      status: upper(row?.status),
    }));
  }, [screeningMode, referenceComparison, identity, verification?.schemaChecks]);

  const matchedFields = fieldComparisonRows.filter((row) => ["MATCH", "PASS", "MATCHED"].includes(row.status));
  const unmatchedFields = fieldComparisonRows.filter((row) => !["MATCH", "PASS", "MATCHED"].includes(row.status));
  const qualityStatus = upper(qualityAnalysis?.overall || qualityAnalysis?.status || "REVIEW");
  const integrityStatus = upper(integrityScreening?.status || "INCONCLUSIVE");

  const finalOutcome = upper(finalDecision?.outcome || "");
  const identityStatus = upper(finalDecision?.identityVerification || "");
  const faceRejected = upper(face?.verified) === "FALSE" || ["FAILED", "NOT_SIMILAR", "LOW_SIMILARITY", "DOCUMENT_FACE_NOT_FOUND", "MULTIPLE_DOCUMENT_FACES", "CAPTURE_FACE_NOT_FOUND", "MULTIPLE_CAPTURE_FACES", "CAPTURE_QUALITY_FAILED", "FACE_FRAMING_INVALID", "FACE_NOT_CENTERED", "COMPARISON_ERROR"].includes(upper(face?.status));
  const identityGateBlocked = finalOutcome.includes("REJECTED_IDENTITY") || identityStatus === "FAILED" || faceRejected;
  const verificationExplanation = text(
    finalDecision?.verificationExplanation || analysisResult?.verificationExplanation ||
      (identityGateBlocked
        ? `Document screening risk is ${riskScore}/100 (${upper(riskBand)}), but identity verification did not pass. A low document-risk score only means that the configured document screening checks found no strong contradiction; it does not prove that the document belongs to the person presenting it. Overall result: NOT VERIFIED.`
        : "Document screening risk and identity verification are separate gates.")
  );
  const verdict = identityGateBlocked
    ? { title: "Identity verification failed", subtitle: verificationExplanation, tone: "danger", icon: UserRoundCheck }
    : finalOutcome === "VERIFIED"
      ? { title: "Document verified", subtitle: "The document passed the configured identity and screening gates and was stored as verified.", tone: "success", icon: ShieldCheck }
      : finalOutcome === "UNDER_REVIEW"
        ? { title: "Manual review required", subtitle: text(finalDecision?.nextAction, "The document is stored for review and is not marked as verified."), tone: "warning", icon: AlertTriangle }
        : verdictFor(riskBand, screeningMode, identityIssues, referenceComparison);
  const VerdictIcon = verdict.icon;
  const riskWidth = `${Math.max(0, Math.min(100, riskScore))}%`;

  const findings = [
    ...riskReasons.slice(0, 4).map((message) => ({ type: "Risk engine", message, severity: "MEDIUM" })),
    ...aiSignals.slice(0, 4),
  ];
  if (faceRejected) {
    findings.unshift({
      type: "Identity verification",
      severity: "HIGH",
      message: text(face?.message, "The live camera face did not pass the identity comparison gate."),
    });
  }
  if (identityIssues.length > 0 && !faceRejected) {
    const firstIssue = identityIssues[0];
    findings.unshift({
      type: "Identity verification",
      severity: "HIGH",
      message: `Identity verification requires attention for ${FIELD_LABELS[firstIssue?.field] || firstIssue?.field || "a document field"}.`,
    });
  }
  if (referenceComparison?.fieldComparison) {
    const counts = referenceComparison.fieldComparison;
    if ((counts.addedCount || 0) > 0) findings.unshift({ type: "Reference comparison", severity: "HIGH", message: `${counts.addedCount} field(s) were found in the suspect copy but not in the reference copy.` });
    if ((counts.changedCount || 0) > 0) findings.unshift({ type: "Reference comparison", severity: "HIGH", message: `${counts.changedCount} extracted field(s) differ from the reference copy.` });
  }
  const visibleFindings = findings.slice(0, 8);

  const normalizedDocumentType = normalizeDocType(
    analysisResult?.id_type ||
    analysisResult?.idType ||
    analysisResult?.document_type ||
    payload?.idType ||
    documentConfig?.idType ||
    ""
  );
  const allowedFieldKeys = DISPLAY_FIELDS_BY_TYPE[normalizedDocumentType];
  const fieldMetadataKeys = new Set(["fieldConfidence", "fieldConfidenceSummary", "template", "documentSpecificTemplate", "ocrPasses", "consensusFields", "referencePoints", "referenceFieldsUsed"]);
  const extractedFieldKeys = Object.keys(extractedFields).filter((key) => !fieldMetadataKeys.has(key));
  const requiredFieldKeys = allowedFieldKeys
    ? [...new Set([...allowedFieldKeys, ...extractedFieldKeys])]
    : extractedFieldKeys;
  const requiredFields = requiredFieldKeys
    .map((key) => [key, extractedFields?.[key]])
    .filter(([, value]) => isDisplayValue(value));
  const indicatorItems = Array.isArray(suspiciousIndicators?.indicators) ? suspiciousIndicators.indicators : [];

  const copyHash = async () => {
    if (!sha) return;
    try {
      await navigator.clipboard.writeText(sha);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  if (!payload) {
    return (
      <div className="site-page">
        <div className="drishti-empty-state">
          <FileSearch2 size={38} />
          <h1>Nothing to review yet</h1>
          <p>Run a document screening first. The evidence report will appear here.</p>
          <button type="button" onClick={() => navigate("/forensic")} className="drishti-primary-btn">
            Open Screening Workspace <ArrowRight size={16} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="site-page drishti-result-page">
      <section className={`drishti-result-hero drishti-verdict-${verdict.tone}`}>
        <div className="drishti-hero-glow" />
        <div className="relative z-10 flex flex-col xl:flex-row xl:items-center xl:justify-between gap-7">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="drishti-pill drishti-pill-dark"><Activity size={13} /> LIVE SCREENING REPORT</span>
              <span className="drishti-pill drishti-pill-dark">{displayMode(screeningMode)}</span>
              <span className="drishti-pill drishti-pill-dark">Evidence confidence: {upper(evidenceConfidence)}</span>
            </div>
            <div className="flex items-start gap-4">
              <div className="drishti-verdict-icon drishti-verdict-pulse"><VerdictIcon size={28} /></div>
              <div>
                <p className="text-xs uppercase tracking-[0.24em] font-black opacity-80">Drishti AI screening outcome</p>
                <h1 className="text-3xl md:text-4xl font-black tracking-tight mt-1">{verdict.title}</h1>
                <p className="text-sm md:text-base opacity-90 mt-2 max-w-3xl leading-6">{verdict.subtitle}</p>
              </div>
            </div>
          </div>

          <div className="drishti-risk-orb shrink-0 drishti-risk-orb-live">
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-300 font-black">Screening risk</div>
            <div className="text-5xl font-black mt-1">{riskScore}</div>
            <div className="text-xs font-bold text-slate-300 mt-1">out of 100</div>
            <div className="drishti-risk-track"><span style={{ width: riskWidth }} /></div>
            <div className="text-[11px] font-black uppercase mt-3">{text(riskBand)}</div>
          </div>
        </div>

        <div className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-3 mt-6">
          <div className="drishti-hero-stat"><ScanText size={17} /><div><span>Document</span><strong>{documentConfig?.label || "Document"}</strong></div></div>
          <div className="drishti-hero-stat"><Shield size={17} /><div><span>Evidence confidence</span><strong>{upper(evidenceConfidence)}</strong></div></div>
          {showAiSection ? <div className="drishti-hero-stat"><Sparkles size={17} /><div><span>AI / synthetic screen</span><strong>{upper(ai.band)}</strong></div></div> : <div className="drishti-hero-stat"><FileSearch2 size={17} /><div><span>Evidence found</span><strong>{verification?.evidenceCount ?? visibleFindings.length} finding(s)</strong></div></div>}
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3 mt-4">
        <div className="drishti-card p-4">
          <p className="drishti-kicker">Final decision</p>
          <p className="text-xl font-black mt-1 text-slate-900">{text(finalDecision?.outcome, storageResult?.storageDecision || "UNDER_REVIEW")}</p>
          <p className="text-xs text-slate-500 mt-1">{text(finalDecision?.nextAction, "Review the evidence shown below.")}</p>
        </div>
        <div className="drishti-card p-4">
          <p className="drishti-kicker">Document authenticity</p>
          <p className="text-xl font-black mt-1 text-slate-900">{text(finalDecision?.documentAuthenticity, upper(riskBand))}</p>
          <p className="text-xs text-slate-500 mt-1">Separate from identity verification.</p>
        </div>
        <div className="drishti-card p-4">
          <p className="drishti-kicker">Identity gate</p>
          <p className="text-xl font-black mt-1 text-slate-900">{text(finalDecision?.identityVerification, screeningMode === "REFERENCE_FORM" ? "REVIEW" : "NOT_REQUIRED")}</p>
          <p className="text-xs text-slate-500 mt-1">Identity and document screening are evaluated as separate gates.</p>
        </div>
        <div className="drishti-card p-4">
          <p className="drishti-kicker">Authenticity screen</p>
          <p className="text-xl font-black mt-1 text-slate-900">{String(authenticityStatus).replaceAll("_", " ")}</p>
          <p className="text-xs text-slate-500 mt-1">Based on document-specific verification evidence.</p>
        </div>
        <div className="drishti-card p-4">
          <p className="drishti-kicker">Case ID</p>
          <p className="text-base font-black mt-2 font-mono break-all text-slate-900">{text(caseId, "Not assigned")}</p>
          <p className="text-xs text-slate-500 mt-1">Use this ID when reviewing the audit trail.</p>
        </div>
      </section>

      {identityGateBlocked && (
        <section className="drishti-card mt-4 border-rose-200 bg-rose-50">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-rose-100 text-rose-700 p-2"><UserRoundCheck size={18} /></div>
            <div>
              <p className="drishti-kicker text-rose-700">Why this document was not verified</p>
              <h2 className="text-lg font-black text-rose-950 mt-1">Document risk and identity verification are separate</h2>
              <p className="text-sm text-rose-900 mt-2 leading-6">{verificationExplanation}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                <div className="rounded-xl border border-rose-200 bg-white/70 p-3">
                  <p className="text-[10px] uppercase tracking-wide font-black text-slate-500">Document screening</p>
                  <p className="text-base font-black text-slate-900 mt-1">{riskScore}/100 · {upper(riskBand)}</p>
                </div>
                <div className="rounded-xl border border-rose-200 bg-white/70 p-3">
                  <p className="text-[10px] uppercase tracking-wide font-black text-slate-500">Identity verification</p>
                  <p className="text-base font-black text-rose-800 mt-1">{text(finalDecision?.identityVerification, "FAILED")}</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {documentPreview && (
        <section className="drishti-card mt-4">
          <div className="drishti-card-heading">
            <div>
              <p className="drishti-kicker">Extracted document image</p>
              <h2>Clear inspection preview</h2>
              <p className="text-xs text-slate-500 mt-1">This preview uses the high-resolution PDF/image source used by the screening pipeline.</p>
            </div>
            <ScanText size={22} className="text-cyan-700" />
          </div>
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-950 p-2 overflow-hidden">
            <img src={documentPreview} alt="Extracted document preview" className="w-full max-h-[620px] object-contain rounded-xl bg-white" />
          </div>
        </section>
      )}

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <div className="drishti-card p-5">
          <div className="flex items-center justify-between gap-3"><div><p className="drishti-kicker">Document quality</p><p className="text-2xl font-black mt-1 text-slate-900">{qualityStatus}</p></div><ScanText size={20} className="text-cyan-700" /></div>
          <p className="text-xs text-slate-500 mt-2">{text(qualityAnalysis?.resolution?.width ? `${qualityAnalysis.resolution.width} × ${qualityAnalysis.resolution.height}px` : qualityAnalysis?.summary, "Quality metrics unavailable")}</p>
          <div className="grid grid-cols-2 gap-2 mt-4">
            {[["Brightness", qualityAnalysis?.brightness?.status], ["Contrast", qualityAnalysis?.contrast?.status], ["Blur", qualityAnalysis?.blur?.status], ["Glare", qualityAnalysis?.glare?.status]].map(([label, value]) => <div key={label} className="drishti-metric"><span>{label}</span><strong>{text(value, "N/A")}</strong></div>)}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div className="drishti-metric"><span>Skew</span><strong>{text(qualityAnalysis?.skew?.status, "N/A")}</strong></div>
            <div className="drishti-metric"><span>Edges</span><strong>{text(qualityAnalysis?.edge_density?.status, "N/A")}</strong></div>
          </div>
        </div>
        <div className="drishti-card p-5">
          <div className="flex items-center justify-between gap-3"><div><p className="drishti-kicker">Matched fields</p><p className="text-2xl font-black mt-1 text-emerald-700">{matchedFields.length}</p></div><CheckCircle2 size={20} className="text-emerald-600" /></div>
          <p className="text-xs text-slate-500 mt-2">Fields that matched the reference/template checks.</p>
        </div>
        <div className="drishti-card p-5">
          <div className="flex items-center justify-between gap-3"><div><p className="drishti-kicker">Unmatched / review fields</p><p className="text-2xl font-black mt-1 text-amber-700">{unmatchedFields.length}</p></div><AlertTriangle size={20} className="text-amber-600" /></div>
          <p className="text-xs text-slate-500 mt-2">Missing, changed or uncertain field checks are counted here.</p>
        </div>
      </section>

      <section className="drishti-card mt-4">
        <div className="drishti-card-heading"><div><p className="drishti-kicker">Other screening signals</p><h2>File and capture indicators</h2></div><Activity size={21} className="text-amber-600" /></div>
        {indicatorItems.length > 0 ? <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">{indicatorItems.map((signal, index) => <SignalCard signal={signal} key={`indicator-${index}`} />)}</div> : <div className="drishti-clear-box mt-4"><CheckCircle2 size={18} /><p>No file-level warning signals were detected.</p></div>}
        <p className="text-xs text-slate-500 mt-4">Highest indicator severity: {text(suspiciousIndicators?.highest_severity, "LOW")}. These signals support review and do not independently prove fraud.</p>
      </section>

      <section className="drishti-card mt-4">
        <div className="drishti-card-heading"><div><p className="drishti-kicker">Document integrity</p><h2>Original vs edited screening</h2><p className="text-xs text-slate-500 mt-1">A clean result means no strong edit signal was found; it does not prove that the source is an original issuer copy.</p></div><ShieldCheck size={21} className="text-indigo-600" /></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
          <div className="drishti-metric"><span>Integrity status</span><strong>{integrityStatus.replaceAll("_", " ")}</strong></div>
          {integrityScreening?.score !== null && integrityScreening?.score !== undefined && <div className="drishti-metric"><span>Edit evidence score</span><strong>{text(integrityScreening.score, "0")}/100</strong></div>}
          <div className="drishti-metric"><span>Matched fields</span><strong>{matchedFields.length}</strong></div>
        </div>
        <p className="text-sm font-semibold text-slate-700 mt-4">{text(integrityScreening?.summary, "Integrity screening was inconclusive.")}</p>
        {Array.isArray(integrityScreening?.evidence) && integrityScreening.evidence.length > 0 && <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">{integrityScreening.evidence.slice(0, 4).map((item, index) => <SignalCard key={`integrity-${index}`} signal={{ ...item, type: item?.type || "INTEGRITY", severity: item?.severity || "REVIEW" }} />)}</div>}
        <p className="text-[11px] text-slate-500 mt-4 leading-5">{text(integrityScreening?.notice)}</p>
      </section>

      {fieldComparisonRows.length > 0 && <section className="drishti-card mt-4">
        <div className="drishti-card-heading"><div><p className="drishti-kicker">Field comparison</p><h2>Matched and unmatched fields</h2></div><FileSearch2 size={21} className="text-violet-600" /></div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase tracking-wide text-slate-400 border-b"><th className="py-3 pr-4">Field</th><th className="py-3 pr-4">Expected / reference</th><th className="py-3 pr-4">Extracted</th><th className="py-3">Status</th></tr></thead><tbody>{fieldComparisonRows.map((row) => { const tone = statusTone(row.status); return <tr key={row.field} className="border-b last:border-0"><td className="py-3 pr-4 font-black text-slate-800">{row.label}</td><td className="py-3 pr-4 text-slate-500 break-all">{isDisplayValue(row.expected) ? text(row.expected) : "Not provided"}</td><td className="py-3 pr-4 font-bold text-slate-800 break-all">{isDisplayValue(row.actual) ? text(row.actual) : "Not extracted"}</td><td className="py-3"><span className={`drishti-mini-status ${tone.className}`}>{tone.label}</span></td></tr>; })}</tbody></table>
        </div>
      </section>}

      <section id="result-section-coverage" className="grid grid-cols-1 xl:grid-cols-[1.55fr_.85fr] gap-5 mt-5 scroll-mt-24">
        <div className="drishti-card drishti-card-accent">
          <div className="drishti-card-heading">
            <div><p className="drishti-kicker">What the system checked</p><h2>Verification coverage</h2></div>
            <ShieldCheck size={22} className="text-emerald-600" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
            {evidenceModules.map((module, index) => <ModuleCard key={`${module?.id || module?.label}-${index}`} module={module} />)}
          </div>
        </div>

        <div className="drishti-card">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Human-readable summary</p><h2>What should I do next?</h2></div><ArrowRight size={20} className="text-sky-700" /></div>
          <div className="drishti-next-step">
            <div className="drishti-step-icon"><ArrowRight size={18} /></div>
            <div>
              <p className="font-black text-slate-900">{identityGateBlocked ? text(finalDecision?.nextAction, "Identity verification failed. Capture the correct document holder's live face and run the verification again.") : text(risk?.recommendation, verdict.tone === "danger" ? "Do not accept this document without additional verification." : verdict.tone === "warning" ? "Perform manual review of the highlighted evidence." : "Proceed with the normal verification workflow.")}</p>
              <p className="text-xs text-slate-500 mt-1 leading-5">Risk is an explainable screening score derived from configured evidence checks.</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 mt-4">
            {isDisplayValue(analysisResult?.ocrConfidence ?? ocr?.confidence) && <div className="drishti-metric"><span>OCR confidence</span><strong>{text(analysisResult?.ocrConfidence ?? ocr?.confidence)}%</strong></div>}
            {verification?.reviewCount !== null && verification?.reviewCount !== undefined && <div className="drishti-metric"><span>Review items</span><strong>{verification.reviewCount}</strong></div>}
            {showAiSection && <div className="drishti-metric"><span>AI signals</span><strong>{aiSignals.length}</strong></div>}
            {screeningMode === "REFERENCE_DOCUMENT" && referenceComparison?.fieldComparison?.differenceCount !== null && referenceComparison?.fieldComparison?.differenceCount !== undefined && <div className="drishti-metric"><span>Reference changes</span><strong>{referenceComparison.fieldComparison.differenceCount}</strong></div>}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" onClick={() => navigate("/forensic", { state: { screeningMode: "SINGLE_DOCUMENT" } })} className="drishti-primary-btn">Run another check <ArrowRight size={16} /></button>
              {screeningMode === "SINGLE_DOCUMENT" && (
                <button type="button" onClick={openIdentityVerification} className="drishti-secondary-btn">Want to store this document <ShieldCheck size={16} /></button>
              )}
            </div>
            {storageResult?.success && <button type="button" onClick={() => navigate("/user-portal")} className="drishti-secondary-btn">Open document vault</button>}
          </div>
        </div>
      </section>

      {visibleFindings.length > 0 && (
        <section id="result-section-findings" className="drishti-card mt-5 scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Evidence that matters</p><h2>What the system found</h2><p className="text-xs text-slate-500 mt-1">Only meaningful findings are shown here. Technical detail remains available below.</p></div><FileSearch2 size={21} className="text-slate-500" /></div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
            {visibleFindings.map((signal, index) => <SignalCard key={`${signal?.type || "finding"}-${index}`} signal={signal} />)}
          </div>
        </section>
      )}

      {screeningMode === "REFERENCE_FORM" && (
        <section id="result-section-identity" className="drishti-card mt-5 scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Identity verification</p><h2>Fields that need attention</h2></div><UserRoundCheck size={21} className="text-sky-700" /></div>
          {identityIssues.length > 0 ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs uppercase tracking-wide text-slate-400 border-b"><th className="py-3 pr-4">Field</th><th className="py-3 pr-4">Expected</th><th className="py-3 pr-4">Extracted</th><th className="py-3">Status</th></tr></thead>
                <tbody>
                  {identityIssues.map(({ field, value }) => {
                    const tone = statusTone(value?.status);
                    return <tr key={field} className="border-b last:border-0"><td className="py-3 pr-4 font-black text-slate-800">{FIELD_LABELS[field] || field.replaceAll("_", " ")}</td><td className="py-3 pr-4 text-slate-500 break-all">{isDisplayValue(value?.reference) ? text(value?.reference) : "Not provided"}</td><td className="py-3 pr-4 font-bold text-slate-800 break-all">{isDisplayValue(value?.extracted) ? text(value?.extracted) : "Not extracted"}</td><td className="py-3"><span className={`drishti-mini-status inline-flex ${tone.className}`}>{tone.label}</span></td></tr>;
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="drishti-clear-box mt-4"><CheckCircle2 size={18} /><p>No field-level identity mismatch is currently visible.</p></div>
          )}
        </section>
      )}

      {screeningMode === "REFERENCE_DOCUMENT" && (
        <section id="result-section-reference" className="drishti-card mt-5 scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Two-document analysis</p><h2>Reference vs suspect changes</h2></div><FileSearch2 size={22} className="text-violet-600" /></div>
          <div className="grid grid-cols-3 gap-3 mt-4">
            <div className="drishti-metric"><span>Changed fields</span><strong>{referenceComparison?.fieldComparison?.changedCount ?? 0}</strong></div>
            <div className="drishti-metric"><span>Added fields</span><strong>{referenceComparison?.fieldComparison?.addedCount ?? 0}</strong></div>
            <div className="drishti-metric"><span>Changed visual regions</span><strong>{referenceComparison?.visualComparison?.regionCount ?? 0}</strong></div>
          </div>
          {Array.isArray(referenceComparison?.fieldComparison?.comparisons) && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs uppercase tracking-wide text-slate-400 border-b"><th className="py-3 pr-4">Field</th><th className="py-3 pr-4">Reference</th><th className="py-3 pr-4">Suspect</th><th className="py-3">Result</th></tr></thead>
                <tbody>
                  {referenceComparison.fieldComparison.comparisons.filter((row) => upper(row?.status) !== "MATCH").map((row) => <tr key={row.field} className="border-b last:border-0"><td className="py-3 pr-4 font-black">{FIELD_LABELS[row.field] || row.field.replaceAll("_", " ")}</td><td className="py-3 pr-4 text-slate-500">{isDisplayValue(row.reference) ? text(row.reference) : "Not present in reference"}</td><td className="py-3 pr-4 font-bold">{isDisplayValue(row.suspect) ? text(row.suspect) : "Not present in suspect"}</td><td className="py-3"><span className={`drishti-mini-status ${statusTone(row.status).className}`}>{upper(row.status)}</span></td></tr>)}
                </tbody>
              </table>
            </div>
          )}
          {Array.isArray(referenceComparison?.visualComparison?.regions) && referenceComparison.visualComparison.regions.length > 0 && (
            <div className="mt-4 rounded-2xl bg-violet-50 border border-violet-200 p-4">
              <p className="text-sm font-black text-violet-900">Visual changes detected</p>
              <p className="text-xs text-violet-800 mt-1">{referenceComparison.visualComparison.regionCount} region(s) changed after alignment. Lighting, crop and scan differences can also create visual changes.</p>
            </div>
          )}
        </section>
      )}

      <section id="result-section-extracted" className="drishti-card mt-5 scroll-mt-24">
        <div className="drishti-card-heading"><div><p className="drishti-kicker">Required extracted fields</p><h2>Document fields</h2><p className="text-xs text-slate-500 mt-1">All fields configured for {documentConfig?.label || normalizedDocumentType || "this document"} are shown, including fields that were not readable.</p></div><ScanText size={22} className="text-cyan-700" /></div>
        {requiredFields.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
            {requiredFields.map(([key, value]) => {
              const confidence = Number(fieldConfidence?.[key] ?? 0);
              return <div key={key} className="drishti-field-card"><div className="flex items-center justify-between gap-3"><p className="text-xs uppercase tracking-wide font-black text-slate-400">{FIELD_LABELS[key] || key.replaceAll("_", " ")}</p>{confidence > 0 && <span className="text-[10px] font-black text-slate-400">{Math.round(confidence)}%</span>}</div><p className={`text-sm md:text-base font-black mt-2 break-all ${isDisplayValue(value) ? "text-slate-800" : "text-slate-400"}`}>{text(value, "Not extracted")}</p>{confidence > 0 && <div className="drishti-confidence-track"><span style={{ width: `${Math.max(0, Math.min(100, confidence))}%` }} /></div>}</div>;
            })}
          </div>
        ) : <div className="drishti-warning-box mt-4"><AlertTriangle size={18} /><p>No required field configuration was returned for this document type.</p></div>}
      </section>

      {crossDocument?.available && (
        <section id="result-section-cross-document" className="drishti-card mt-5 scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Account-level verification</p><h2>Cross-document identity consistency</h2><p className="text-xs text-slate-500 mt-1">Previously stored documents for the same account are compared when comparable fields are available.</p></div><ShieldCheck size={21} className="text-emerald-600" /></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
            <div className="drishti-metric"><span>Status</span><strong>{text(crossDocument?.status)}</strong></div>
            <div className="drishti-metric"><span>Compared documents</span><strong>{text(crossDocument?.comparedDocumentCount, "0")}</strong></div>
            <div className="drishti-metric"><span>Consistency signal</span><strong>{text(crossDocument?.score, "0")}/10</strong></div>
          </div>
          {Array.isArray(crossDocument?.matches) && crossDocument.matches.filter((row) => upper(row?.status) !== "MATCH").length > 0 ? (
            <div className="mt-4 space-y-3">
              {crossDocument.matches.filter((row) => upper(row?.status) !== "MATCH").map((row, index) => (
                <div key={`${row?.field}-${index}`} className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <p className="text-sm font-black text-amber-900">{FIELD_LABELS[row?.field] || row?.field}</p>
                  <p className="text-xs text-amber-800 mt-1">Current: {text(row?.current)} · Previous: {text(row?.previous)} · {upper(row?.status)}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="drishti-clear-box mt-4"><CheckCircle2 size={18} /><p>{text(crossDocument?.reasons?.[0], "No shared-field inconsistency was found.")}</p></div>
          )}
        </section>
      )}

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-5">
        {showAiSection && <div id="result-section-ai" className="drishti-card scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">AI &amp; synthetic screening</p><h2>Could this be digitally generated or heavily edited?</h2></div><Sparkles size={21} className="text-fuchsia-600" /></div>
          <div className="flex items-center justify-between gap-4 mt-4"><div><p className="text-xs uppercase font-black tracking-wide text-slate-400">Forensic band</p><p className="text-3xl font-black mt-1">{upper(ai?.band || "UNAVAILABLE")}</p></div><div className="text-right"><p className="text-xs uppercase font-black tracking-wide text-slate-400">Screening score</p><p className="text-3xl font-black text-slate-900 mt-1">{text(ai?.score, "0")}</p></div></div>
          {aiSignals.length > 0 ? <div className="space-y-3 mt-4">{aiSignals.slice(0, 5).map((signal, i) => <SignalCard signal={signal} key={`ai-${i}`} />)}</div> : <div className="drishti-clear-box mt-4"><CheckCircle2 size={18} /><p>No strong AI/synthetic indicators were detected by the current heuristic screen.</p></div>}
          {Array.isArray(ai?.qualitySignals) && ai.qualitySignals.length > 0 && <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4"><p className="text-xs font-black uppercase tracking-wide text-amber-800">OCR quality note</p><div className="space-y-2 mt-2">{ai.qualitySignals.slice(0, 3).map((signal, i) => <p className="text-xs text-amber-900 leading-5" key={`quality-${i}`}>{text(signal?.message)}</p>)}</div></div>}
          <p className="text-[11px] text-slate-500 mt-4 leading-5">{text(ai?.notice, "This screen is forensic evidence, not proof of AI authorship.")}</p>
        </div>}

        {showEncodedSection && <div id="result-section-encoded" className="drishti-card scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Encoded &amp; file evidence</p><h2>QR, fingerprint and metadata</h2></div><QrCode size={21} className="text-indigo-600" /></div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
            {isDisplayValue(qr?.status) && upper(qr?.status) !== "NOT_DETECTED" && (
              <div className="drishti-metric"><span>QR status</span><strong>{upper(qr?.status)}</strong></div>
            )}
            {isDisplayValue(issuer?.status) && !["NOT_CONFIGURED", "UNAVAILABLE"].includes(upper(issuer?.status)) && (
              <div className="drishti-metric"><span>Issuer verification</span><strong>{upper(issuer?.status)}</strong></div>
            )}
          </div>
          {qr?.decoded && <div className="mt-3 rounded-2xl bg-slate-50 border border-slate-200 p-3"><p className="text-xs uppercase tracking-wide font-black text-slate-400">Readable QR payload</p><p className="font-mono text-xs mt-2 break-all text-slate-700">{text(qr?.payloadPreview)}</p></div>}
          {sha && <div className="mt-3 rounded-2xl bg-slate-50 border border-slate-200 p-3"><div className="flex items-center justify-between gap-3"><p className="text-xs uppercase tracking-wide font-black text-slate-400">SHA-256 fingerprint</p><button type="button" onClick={copyHash} className="text-xs font-black text-sky-700 inline-flex items-center gap-1"><Copy size={13} />{copied ? "Copied" : "Copy"}</button></div><p className="font-mono text-[11px] mt-2 break-all text-slate-700">{sha}</p></div>}
        </div>}
      </section>

      {face && (
        <section id="result-section-biometric" className="drishti-card mt-5 scroll-mt-24">
          <div className="drishti-card-heading"><div><p className="drishti-kicker">Biometric support</p><h2>Document photo vs live camera</h2></div><UserRoundCheck size={21} className="text-emerald-600" /></div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4">
            {face?.score !== null && face?.score !== undefined && <div className="drishti-metric"><span>Similarity</span><strong>{face.score}%</strong></div>}
            {face?.threshold !== null && face?.threshold !== undefined && <div className="drishti-metric"><span>Threshold</span><strong>{face.threshold}%</strong></div>}
            {isDisplayValue(face?.status) && <div className="drishti-metric"><span>Face status</span><strong>{upper(face.status)}</strong></div>}
            {isDisplayValue(cameraCapture?.livenessStatus) && <div className="drishti-metric"><span>Motion / liveness</span><strong>{upper(cameraCapture.livenessStatus)}</strong></div>}
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-xs font-bold text-slate-500">
            {cameraCapture?.motionScore !== null && cameraCapture?.motionScore !== undefined && <span className="rounded-full bg-slate-100 border border-slate-200 px-3 py-1.5">Motion score: {Number(cameraCapture.motionScore).toFixed(2)}%</span>}
            {cameraCapture?.motionSamples !== null && cameraCapture?.motionSamples !== undefined && Number(cameraCapture.motionSamples) > 0 && <span className="rounded-full bg-slate-100 border border-slate-200 px-3 py-1.5">Motion samples: {cameraCapture.motionSamples}</span>}
          </div>
          <div className="mt-4 flex flex-col md:flex-row gap-4">
            {face?.documentFace && <div className="w-full md:w-56"><p className="text-[10px] uppercase tracking-wide font-black text-slate-400 mb-2">Extracted document face</p><img src={face.documentFace} alt="Extracted face from document" className="w-full h-44 object-contain bg-slate-950 rounded-2xl" /></div>}
            {face?.captureFace && <div className="w-full md:w-56"><p className="text-[10px] uppercase tracking-wide font-black text-slate-400 mb-2">Live camera face</p><img src={face.captureFace} alt="Camera face" className="w-full h-44 object-contain bg-slate-950 rounded-2xl" /></div>}
            <div className="flex-1 rounded-2xl bg-slate-50 border border-slate-200 p-4"><p className="text-sm font-bold text-slate-800">{text(face?.message)}</p><p className="text-xs text-slate-500 mt-2 leading-5">Identity verification requires a live camera capture. The motion gate blocks the basic static-photo attempt; document authenticity remains a separate screening decision.</p></div>
          </div>
        </section>
      )}

      {showAdvancedEvidence && <section id="result-section-advanced" className="drishti-card mt-5 scroll-mt-24">
        <details>
          <summary className="cursor-pointer list-none flex items-center justify-between gap-4">
            <div><p className="drishti-kicker">Advanced evidence</p><h2>Technical details for operators</h2><p className="text-xs text-slate-500 mt-1">Open this only when you need to inspect raw forensic signals.</p></div>
            <ArrowRight size={19} className="text-slate-400" />
          </summary>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-5">
            {hasValue(risk?.score_breakdown) && <div className="drishti-tech-box">
              <h3>Risk-score breakdown</h3>
              <pre>{JSON.stringify(risk.score_breakdown, null, 2)}</pre>
            </div>}
            {hasValue(risk?.verification_evidence) && <div className="drishti-tech-box">
              <h3>Strict verification evidence</h3>
              <pre>{JSON.stringify(risk.verification_evidence, null, 2)}</pre>
            </div>}
            {isDisplayValue(ocr?.text) && <div className="drishti-tech-box lg:col-span-2"><h3>Raw OCR text</h3><pre>{ocr.text}</pre></div>}
          </div>
        </details>
      </section>}

      {duplicateInfo && (
        <section className="drishti-warning-box mt-5">
          <AlertTriangle size={19} />
          <div className="flex-1">
            <p className="font-black">Document already stored</p>
            <p className="text-xs mt-1">{text(duplicateInfo?.message)}</p>
            <p className="text-xs mt-1 font-semibold">Stored location: {duplicateInfo?.existingOwner === "CURRENT_USER" ? "your account" : "another account"}</p>
            {duplicateInfo?.existingDocumentNumber && (
              <p className="text-xs mt-1 font-mono">Stored document: {text(duplicateInfo.existingDocumentNumber)}</p>
            )}
            {duplicateInfo?.detail && <p className="text-xs mt-1 opacity-80">{text(duplicateInfo.detail)}</p>}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {duplicateInfo?.canUpdate && (
                <button
                  type="button"
                  className="drishti-primary-btn"
                  onClick={() => {
                    sessionStorage.setItem("reverificationContext", JSON.stringify({
                      existingDocumentId: duplicateInfo.existingDocumentId,
                      documentNumber: duplicateInfo.documentNumber || duplicateInfo.existingDocumentNumber,
                      idType: duplicateInfo.idType || normalizedDocumentType,
                      existingFullName: duplicateInfo.existingFullName || "",
                      existingDob: duplicateInfo.existingDob || "",
                    }));
                    navigate("/forensic");
                  }}
                >
                  Update & Re-verify <ArrowRight size={15} />
                </button>
              )}
              {duplicateInfo?.canUpdate === false && (
                <span className="text-xs font-bold px-3 py-2 rounded-lg bg-white/70 border border-amber-300 text-amber-800">Duplicate attempt blocked</span>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="drishti-disclaimer mt-5">
        <Info size={17} />
        <p>Drishti AI provides document-screening and verification assistance. A screening score is not a probability of fraud, and forensic image evidence alone cannot prove the exact editing tool or legal authenticity of a document.</p>
      </section>
    </div>
  );
}
