import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

export default function AuditLogs() {
  const navigate = useNavigate();

  const [logs, setLogs] = useState([]);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState("");

  const [selectedLogId, setSelectedLogId] = useState(null);

  const getLogKey = (log, index = 0) =>
    `${log?.log_source || "AUDIT"}-${log?.log_id ?? "row"}-${log?.created_at || index}`;

  useEffect(() => {
    let cancelled = false;

    const loadLogs = async () => {
      try {
        setLoading(true);
        setError("");

        let response = await fetch("/api/audit-logs", {
          credentials: "include",
        });

        const text = await response.text();

        let result = [];

        try {
          result = text ? JSON.parse(text) : [];
        } catch {
          result = [];
        }

        if (!response.ok) {
          throw new Error(
            result?.detail ||
              result?.message ||
              "Unable to load screening history.",
          );
        }

        if (!cancelled) {
          const nextLogs = Array.isArray(result) ? result : [];
          setLogs(nextLogs);
          setSelectedLogId((currentId) => {
            if (!currentId) return null;
            return nextLogs.some((item, index) => getLogKey(item, index) === currentId)
              ? currentId
              : null;
          });
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || "Unable to load screening history.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadLogs();

    return () => {
      cancelled = true;
    };
  }, []);

  const getDetails = (log) => {
    if (!log?.details) {
      return {};
    }

    if (typeof log.details !== "string") {
      return log.details;
    }

    try {
      return JSON.parse(log.details);
    } catch {
      return {};
    }
  };

  const renderAuditValue = (value) => {
    if (value === null || value === undefined || value === "") {
      return <span className="text-slate-400">Not available</span>;
    }

    if (Array.isArray(value)) {
      if (!value.length) return <span className="text-slate-400">None</span>;
      return (
        <div className="space-y-1.5">
          {value.map((item, index) => (
            <div
              key={index}
              className="bg-white border border-slate-200 rounded-lg px-3 py-2"
            >
              {renderAuditValue(item)}
            </div>
          ))}
        </div>
      );
    }

    if (typeof value === "object") {
      const entries = Object.entries(value).filter(
        ([key]) =>
          ![
            "captureId",
            "capture_id",
            "attemptId",
            "attempt_id",
            "verificationId",
            "verification_id",
            "documentId",
            "document_id",
            "storedFilename",
            "stored_filename",
            "storedPath",
            "stored_path",
            "fileUrl",
            "file_url",
          ].includes(key),
      );

      if (!entries.length)
        return <span className="text-slate-400">Not available</span>;

      return (
        <div className="space-y-2">
          {entries.map(([key, child]) => (
            <div
              key={key}
              className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1 border-b border-slate-100 last:border-0 pb-2 last:pb-0"
            >
              <span className="text-sm font-medium text-slate-500 capitalize">
                {String(key)
                  .replaceAll("_", " ")
                  .replace(/([a-z])([A-Z])/g, "$1 $2")}
              </span>
              <span className="text-sm font-bold text-slate-800 sm:text-right">
                {renderAuditValue(child)}
              </span>
            </div>
          ))}
        </div>
      );
    }

    const text = String(value);
    return text === "true" ? "Yes" : text === "false" ? "No" : text;
  };

  const screeningLogs = useMemo(() => logs, [logs]);

  const auditSummary = useMemo(() => {
    const attempts = logs.filter(
      (log) => log.event_type === "DOCUMENT_SCREENING",
    );

    const successfulDocuments = logs.filter((log) => {
      const status = String(log.status || "").toUpperCase();
      return status === "DOCUMENT_ADDED" || status === "DOCUMENT_VERIFIED";
    });

    const loginEvents = logs.filter(
      (log) =>
        log.event_type === "LOGIN" &&
        String(log.status).toUpperCase() === "SUCCESS",
    );

    const uniqueDocuments = new Set(
      successfulDocuments
        .map((log) => getDetails(log))
        .map((details) => details.documentNumber || details.document_number)
        .filter(Boolean),
    );

    const latestLogin = loginEvents[0]?.created_at || null;
    const accountUser = getDetails(logs[0] || {}).user || {};

    return {
      attempts: attempts.length,
      verifiedDocuments: uniqueDocuments.size || successfulDocuments.length,
      loginCount: loginEvents.length,
      latestLogin,
      accountUser,
    };
  }, [logs]);

  const getEventLabel = (log) => {
    const event = String(log?.event_type || "").toUpperCase();
    const labels = {
      LOGIN: "User Login",
      DOCUMENT_SCREENING: "Document Verification",
    };
    return labels[event] || event.replaceAll("_", " ") || "Account Activity";
  };

  const formatDate = (value) => {
    if (!value) {
      return "-";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  };

  const getRiskScore = (details) => {
    return details.riskScore ?? details.risk_score ?? "-";
  };

  const getRiskBand = (details, log) => {
    return (
      details.riskBand ??
      details.risk_band ??
      details.finalStatus ??
      log.status ??
      "UNKNOWN"
    );
  };

  const getDocumentType = (details) => {
    return details.idType ?? details.id_type ?? "DOCUMENT";
  };

  const getDocumentNumber = (details) => {
    return details.documentNumber ?? details.document_number ?? "-";
  };

  const getUserIdFromLog = (details, log) => {
    return (
      details.userEmail ??
      log.subject_id ??
      sessionStorage.getItem("userEmail") ??
      "Not available"
    );
  };

  const getStorageStatus = (details, log) => {
    if (details.dataStored === true) {
      return "STORED";
    }

    const status = String(log.status || "").toUpperCase();

    if (status === "DOCUMENT_ADDED" || status === "USER_ID_CREATED") {
      return "STORED";
    }

    return "NOT STORED";
  };

  const getStatusClass = (value) => {
    const status = String(value || "").toUpperCase();

    if (
      status.includes("LOW") ||
      status.includes("MATCH") ||
      status.includes("SUCCESS") ||
      status.includes("STORED") ||
      status.includes("VERIFIED")
    ) {
      return "bg-emerald-100 text-emerald-800";
    }

    if (
      status.includes("MEDIUM") ||
      status.includes("REVIEW") ||
      status.includes("PARTIAL") ||
      status.includes("EXISTING")
    ) {
      return "bg-amber-100 text-amber-800";
    }

    if (
      status.includes("HIGH") ||
      status.includes("REJECT") ||
      status.includes("FAILED") ||
      status.includes("MISMATCH") ||
      status.includes("NOT STORED")
    ) {
      return "bg-red-100 text-red-800";
    }

    return "bg-slate-100 text-slate-700";
  };

  const closeDetails = () => {
    setSelectedLogId(null);
  };

  const selectedLog = useMemo(
    () =>
      logs.find((log, index) => getLogKey(log, index) === selectedLogId) ?? null,
    [logs, selectedLogId],
  );

  const openDetails = (log, index) => {
    setSelectedLogId(getLogKey(log, index));
  };

  return (
    <div className="site-page w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
      <div className="bg-white border border-slate-300 rounded-lg shadow-sm p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="text-xs text-sky-700 font-bold uppercase tracking-widest">
              Drishti AI
            </p>

            <h1 className="text-2xl font-bold text-sky-900 mt-1">
              Account History
            </h1>

            <p className="text-sm text-slate-500 mt-1">
              Successful logins and completed document verification outcomes are
              shown.
            </p>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => navigate("/forensic")}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded text-sm font-bold uppercase"
            >
              + Add Document
            </button>

            <button
              type="button"
              onClick={() => navigate("/user-portal")}
              className="bg-sky-900 hover:bg-sky-800 text-white px-4 py-2 rounded text-sm font-bold uppercase"
            >
              User Portal
            </button>
          </div>
        </div>

        <div className="mt-4 bg-slate-50 border border-slate-200 rounded p-3">
          <p className="text-xs text-slate-500 uppercase font-bold">
            Authenticated Account
          </p>

          <p className="font-mono text-xl font-extrabold text-sky-900 tracking-widest mt-1">
            {sessionStorage.getItem("userEmail") || "Not available"}
          </p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-white border border-slate-300 rounded-lg p-4 shadow-sm">
          <p className="text-xs font-bold text-slate-500 uppercase">User</p>
          <p className="text-base font-bold text-sky-900 mt-1">
            {auditSummary.accountUser.fullName || "Not available"}
          </p>
          <p className="text-xs text-slate-500 mt-1 break-all">
            {auditSummary.accountUser.email ||
              sessionStorage.getItem("userEmail") ||
              "-"}
          </p>
        </div>
        <div className="bg-white border border-slate-300 rounded-lg p-4 shadow-sm">
          <p className="text-xs font-bold text-slate-500 uppercase">
            Screenings
          </p>
          <p className="text-3xl font-extrabold text-sky-900 mt-1">
            {auditSummary.attempts}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Every submitted document screening is counted.
          </p>
        </div>
        <div className="bg-white border border-slate-300 rounded-lg p-4 shadow-sm">
          <p className="text-xs font-bold text-slate-500 uppercase">
            Documents Verified
          </p>
          <p className="text-3xl font-extrabold text-emerald-700 mt-1">
            {auditSummary.verifiedDocuments}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Successfully stored verification records.
          </p>
        </div>
        <div className="bg-white border border-slate-300 rounded-lg p-4 shadow-sm">
          <p className="text-xs font-bold text-slate-500 uppercase">
            Session Times
          </p>
          <p className="text-xs font-bold text-slate-700 mt-2">
            Login: {formatDate(auditSummary.latestLogin)}
          </p>
        </div>
      </div>

      <div className="mt-5 bg-white border border-slate-300 rounded-lg shadow-sm overflow-hidden">
        {loading && (
          <div className="p-10 text-center">
            <div className="w-8 h-8 border-4 border-sky-900 border-t-transparent rounded-full animate-spin mx-auto" />

            <p className="text-sm text-slate-500 mt-3">
              Loading your screening history...
            </p>
          </div>
        )}

        {error && !loading && (
          <div className="p-6">
            <div className="bg-red-50 border border-red-200 text-red-700 rounded p-4 text-sm font-semibold">
              {error}
            </div>
          </div>
        )}

        {!loading && !error && screeningLogs.length === 0 && (
          <div className="p-10 text-center">
            <p className="text-base font-bold text-slate-700">
              No account history found.
            </p>

            <p className="text-sm text-slate-500 mt-1">
              Your account activity will appear here.
            </p>
          </div>
        )}

        {!loading && !error && screeningLogs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 border-b">
                <tr>
                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    Date
                  </th>

                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    User
                  </th>

                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    Event
                  </th>

                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    Document
                  </th>

                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    Risk
                  </th>

                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    Storage
                  </th>

                  <th className="text-left p-3 font-bold text-slate-600 uppercase">
                    Status
                  </th>

                  <th className="p-3" />
                </tr>
              </thead>

              <tbody className="divide-y">
                {screeningLogs.map((log, index) => {
                  const details = getDetails(log);

                  const riskBand = getRiskBand(details, log);

                  const storage = getStorageStatus(details, log);

                  const status = log.status || "ANALYZED";

                  return (
                    <tr key={getLogKey(log, index)} className="hover:bg-slate-50">
                      <td className="p-3 align-top">
                        {formatDate(log.created_at)}
                      </td>

                      <td className="p-3 align-top">
                        <p className="font-bold text-slate-800">
                          {details.user?.fullName || "Not available"}
                        </p>
                        <p className="text-xs text-slate-500 break-all mt-1">
                          {details.user?.email ||
                            getUserIdFromLog(details, log)}
                        </p>
                      </td>

                      <td className="p-3 align-top">
                        <p className="font-bold text-slate-800">
                          {getEventLabel(log)}
                        </p>
                      </td>

                      <td className="p-3 align-top">
                        <p className="font-bold text-slate-800">
                          {getDocumentType(details)}
                        </p>
                        <p className="text-xs font-mono text-slate-500 mt-1 break-all">
                          No: {getDocumentNumber(details)}
                        </p>
                      </td>

                      <td className="p-3 align-top">
                        <div>
                          <span
                            className={`inline-block px-2 py-1 rounded text-xs font-bold ${getStatusClass(
                              riskBand,
                            )}`}
                          >
                            {riskBand}
                          </span>
                        </div>

                        <p className="text-xs text-slate-500 mt-1">
                          Score: {getRiskScore(details)}
                        </p>
                      </td>

                      <td className="p-3 align-top">
                        <span
                          className={`inline-block px-2 py-1 rounded text-xs font-bold ${getStatusClass(
                            storage,
                          )}`}
                        >
                          {storage}
                        </span>
                      </td>

                      <td className="p-3 align-top">
                        <span
                          className={`inline-block px-2 py-1 rounded text-xs font-bold ${getStatusClass(
                            status,
                          )}`}
                        >
                          {status}
                        </span>
                      </td>

                      <td className="p-3 align-top text-right">
                        <button
                          type="button"
                          onClick={() => openDetails(log, index)}
                          className="bg-slate-800 hover:bg-slate-900 text-white px-3 py-1.5 rounded text-xs font-bold uppercase"
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedLog && (
        <div className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4">
          <div className="w-full max-w-2xl bg-white rounded-lg shadow-2xl overflow-hidden">
            <div className="bg-sky-900 text-white px-5 py-4 flex justify-between items-center">
              <div>
                <h2 className="text-base font-bold uppercase">
                  Screening Details
                </h2>

                <p className="text-xs text-sky-200 mt-1">
                  {formatDate(selectedLog.created_at)}
                </p>
              </div>

              <button
                type="button"
                onClick={closeDetails}
                className="text-2xl font-bold"
              >
                ×
              </button>
            </div>

            <div className="p-5 max-h-[70vh] overflow-auto">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-50 border rounded p-3">
                  <p className="text-xs text-slate-500 uppercase">
                    Account Email
                  </p>

                  <p className="font-mono font-bold text-sky-900 mt-1">
                    {getUserIdFromLog(getDetails(selectedLog), selectedLog)}
                  </p>
                </div>

                <div className="bg-slate-50 border rounded p-3">
                  <p className="text-xs text-slate-500 uppercase">Document</p>

                  <p className="font-bold text-slate-800 mt-1">
                    {getDocumentType(getDetails(selectedLog))}
                  </p>
                </div>
              </div>

              <div className="mt-4">
                <p className="text-xs text-slate-500 uppercase font-bold mb-2">
                  Verification Information
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(getDetails(selectedLog))
                    .filter(
                      ([key]) =>
                        ![
                          "captureId",
                          "capture_id",
                          "attemptId",
                          "attempt_id",
                          "verificationId",
                          "verification_id",
                          "documentId",
                          "document_id",
                          "storedFilename",
                          "stored_filename",
                          "storedPath",
                          "stored_path",
                          "fileUrl",
                          "file_url",
                        ].includes(key),
                    )
                    .map(([key, value]) => (
                      <div
                        key={key}
                        className="bg-slate-50 border border-slate-200 rounded-xl p-4"
                      >
                        <p className="text-xs text-slate-500 uppercase font-bold">
                          {String(key)
                            .replaceAll("_", " ")
                            .replace(/([a-z])([A-Z])/g, "$1 $2")}
                        </p>
                        <div className="mt-2 text-base font-semibold text-slate-800 break-words">
                          {renderAuditValue(value)}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>

            <div className="border-t bg-slate-50 p-4 flex justify-end">
              <button
                type="button"
                onClick={closeDetails}
                className="bg-slate-800 text-white px-5 py-2 rounded text-sm font-bold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
