import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, ArrowRight, Camera, FilePlus2, FileText, Fingerprint, Search, ShieldCheck, Sparkles, Trash2, UserRound } from "lucide-react";

export default function UserPortal() {
  const navigate = useNavigate();

  const [user, setUser] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [removingDocumentId, setRemovingDocumentId] = useState(null);
  const [faceCaptures, setFaceCaptures] = useState([]);
  const [documentSearch, setDocumentSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchingDocuments, setSearchingDocuments] = useState(false);

  const userEmail = sessionStorage.getItem("userEmail") || "";
  const uniqueId = sessionStorage.getItem("uniqueId") || "";

  useEffect(() => {
    const loadUserData = async () => {
      if (!userEmail) {
        navigate("/login", {
          replace: true,
        });

        return;
      }

      try {
        setLoading(true);
        setError("");

        const response = await fetch("/api/users/me", {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        });

        const responseText = await response.text();

        if (!response.ok) {
          let message = "Unable to load user profile.";

          if (responseText) {
            try {
              const result = JSON.parse(responseText);

              message = result.error || result.message || message;
            } catch {
              message = responseText;
            }
          }

          throw new Error(message);
        }

        const result = responseText ? JSON.parse(responseText) : {};

        setUser(result.user || null);

        setDocuments(Array.isArray(result.documents) ? result.documents : []);

        setFaceCaptures(
          Array.isArray(result.faceCaptures) ? result.faceCaptures : [],
        );
      } catch (loadError) {
        setError(
          loadError instanceof TypeError
            ? "Unable to connect to the Drishti AI server."
            : loadError.message || "Failed to load user data.",
        );
      } finally {
        setLoading(false);
      }
    };

    loadUserData();
  }, [navigate, userEmail]);

  useEffect(() => {
    const query = documentSearch.trim();
    if (query.length < 2) {
      setSearchResults([]);
      setSearchingDocuments(false);
      return undefined;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        setSearchingDocuments(true);
        const response = await fetch(`/api/documents/search?q=${encodeURIComponent(query)}`, {
          credentials: "include",
          signal: controller.signal,
        });
        const result = await response.json();
        if (response.ok) {
          setSearchResults(Array.isArray(result.documents) ? result.documents : []);
        } else {
          setSearchResults([]);
        }
      } catch (searchError) {
        if (searchError.name !== "AbortError") setSearchResults([]);
      } finally {
        if (!controller.signal.aborted) setSearchingDocuments(false);
      }
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [documentSearch]);


  const handleAddDocument = () => {
    navigate("/forensic");
  };

  const handleRemoveDocument = async (documentId) => {
    if (!uniqueId || !documentId) {
      return;
    }

    const document = documents.find(
      (item) => Number(item.id) === Number(documentId),
    );

    if (!document) {
      return;
    }

    const confirmed = window.confirm(
      `Remove this verified ${document.idType || "document"}?\n\nAfter removal, it will no longer exist in your verified repository and can be verified again.`,
    );

    if (!confirmed) {
      return;
    }

    try {
      setRemovingDocumentId(documentId);
      setError("");

      const response = await fetch(
        `/api/users/${encodeURIComponent(uniqueId)}/documents/${encodeURIComponent(documentId)}`,
        {
          method: "DELETE",
          credentials: "include",
        },
      );

      const text = await response.text();
      let result = {};

      try {
        result = text ? JSON.parse(text) : {};
      } catch {
        result = {};
      }

      if (!response.ok) {
        throw new Error(
          result.detail || result.message || "Unable to remove the document.",
        );
      }

      setDocuments((current) =>
        current.filter((item) => Number(item.id) !== Number(documentId)),
      );
    } catch (removeError) {
      setError(removeError.message || "Unable to remove the document.");
    } finally {
      setRemovingDocumentId(null);
    }
  };

  const getRiskLabel = (score) => {
    const numericScore = Number(score);

    if (numericScore < 25) {
      return "LOW";
    }

    if (numericScore < 50) {
      return "REVIEW";
    }

    return "HIGH";
  };

  const openDocument = (documentId) => {
    if (!uniqueId || !documentId) {
      return;
    }

    const fileUrl =
      `/api/users/${encodeURIComponent(uniqueId)}` +
      `/documents/${encodeURIComponent(documentId)}/file`;

    window.open(fileUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="site-page min-h-full bg-slate-200 px-4 sm:px-6 lg:px-8 py-6 lg:py-8">
      <div className="w-full max-w-7xl mx-auto">
        <div className="portal-hero">
          <div className="portal-hero-orb portal-hero-orb-a" />
          <div className="portal-hero-orb portal-hero-orb-b" />
          <div className="relative z-10">
            <div className="flex flex-col xl:flex-row xl:items-end xl:justify-between gap-6">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="portal-pill"><Activity size={13} /> SECURE USER PORTAL</span>
                  <span className="portal-live-pill"><span /> ACTIVE SESSION</span>
                </div>
                <p className="text-emerald-300 text-xs font-black uppercase tracking-[0.24em] mt-5">Drishti AI • Identity Workspace</p>
                <h1 className="text-3xl md:text-4xl font-black tracking-tight mt-2">Welcome back{user?.fullName ? `, ${user.fullName.split(" ")[0]}` : ""}</h1>
                <p className="text-slate-300 text-sm md:text-base mt-2 max-w-2xl leading-6">Manage your verified documents, review screening outcomes and keep your identity evidence in one place.</p>
              </div>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full xl:w-auto">
                <label className="relative block sm:w-72">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="search"
                    value={documentSearch}
                    onChange={(event) => setDocumentSearch(event.target.value)}
                    placeholder="Search name or verified ID"
                    aria-label="Search saved documents by name or verified ID"
                    className="w-full rounded-lg border border-white/15 bg-white/10 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-slate-400 outline-none focus:border-emerald-300"
                  />
                </label>
                <button type="button" onClick={handleAddDocument} className="portal-add-btn"><FilePlus2 size={17} /> Add document <ArrowRight size={15} /></button>
              </div>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-7">
              <div className="portal-stat"><FileText size={18} /><div><span>Documents</span><strong>{documents.length}</strong></div></div>
              <div className="portal-stat"><ShieldCheck size={18} /><div><span>Stored records</span><strong>{documents.length}</strong></div></div>
              <div className="portal-stat"><Camera size={18} /><div><span>Face captures</span><strong>{faceCaptures.length}</strong></div></div>
              <div className="portal-stat"><Sparkles size={18} /><div><span>AI workspace</span><strong>READY</strong></div></div>
            </div>
          </div>
        </div>

        {documentSearch.trim().length >= 2 && (
          <div className="mt-4 rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-black text-slate-700 uppercase tracking-wide">Saved document matches</h2>
                <p className="text-xs text-slate-500 mt-1">Search results show document details only.</p>
              </div>
              {searchingDocuments && <span className="text-xs font-bold text-sky-700">Searching...</span>}
            </div>
            {searchResults.length > 0 ? (
              <div className="divide-y divide-slate-200">
                {searchResults.map((document, index) => (
                  <div key={`${document.idType}-${document.documentNumber}-${index}`} className="px-5 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <p className="text-sm font-black text-slate-900">{document.fullName || "Name unavailable"}</p>
                      <p className="text-xs text-slate-500 mt-1">{document.idType || "Document"} · {document.documentNumber || "Verified ID unavailable"}</p>
                    </div>
                    <span className="text-xs font-bold uppercase text-emerald-700">{document.finalStatus || "Verified record"}</span>
                  </div>
                ))}
              </div>
            ) : !searchingDocuments ? (
              <p className="px-5 py-5 text-sm text-slate-500">No saved document matches found.</p>
            ) : null}
          </div>
        )}

        <div className="mt-4">
          {loading ? (
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-8 text-center">
              <p className="text-base font-semibold text-slate-700">
                Loading your Drishti AI profile...
              </p>

              <p className="text-sm text-slate-500 mt-1">
                Please wait while your verified records are retrieved.
              </p>
            </div>
          ) : error ? (
            <div className="bg-white rounded-lg border border-red-200 shadow-sm p-6">
              <p className="text-base font-bold text-red-700">
                Unable to load profile
              </p>

              <p className="text-sm text-slate-600 mt-2">{error}</p>

              <button
                type="button"
                onClick={() => window.location.reload()}
                className="mt-4 bg-sky-900 hover:bg-sky-800 text-white px-4 py-2 rounded text-sm font-bold"
              >
                Retry
              </button>
            </div>
          ) : (
            <>
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                <div className="bg-slate-100 px-5 py-3 border-b border-slate-200">
                  <div className="flex items-center gap-2"><UserRound size={15} className="text-emerald-600" /><h2 className="text-sm font-black text-slate-700 uppercase tracking-wide">User Identity</h2></div>
                </div>

                <div className="p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <p className="text-xs font-bold text-slate-500 uppercase">
                      Full Name
                    </p>

                    <p className="text-base font-bold text-slate-900 mt-1">
                      {user?.fullName || "Not Available"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-bold text-slate-500 uppercase">
                      Date of Birth
                    </p>

                    <p className="text-base font-bold text-slate-900 mt-1">
                      {user?.dateOfBirth || "Not Available"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-bold text-slate-500 uppercase">
                      Drishti AI Unique ID
                    </p>
                    <p className="text-base font-bold text-emerald-700 mt-1 font-mono tracking-widest">
                      {user?.uniqueId ||
                        sessionStorage.getItem("uniqueId") ||
                        "Not Available"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-bold text-slate-500 uppercase">
                      Account Email
                    </p>

                    <p className="text-base font-bold text-sky-900 mt-1 tracking-wider">
                      {user?.email || userEmail || "Not Available"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden mt-4">
                <div className="bg-slate-100 px-5 py-3 border-b border-slate-200">
                  <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wide">
                    Recent Camera Capture
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    The most recent camera capture saved to this authenticated
                    account.
                  </p>
                </div>

                {faceCaptures.length === 0 ? (
                  <div className="p-6 text-center">
                    <p className="text-sm font-semibold text-slate-700">
                      No camera capture saved yet.
                    </p>
                  </div>
                ) : (
                  <div className="p-5 flex flex-col sm:flex-row gap-4 items-start">
                    <img
                      src={`/api/users/${encodeURIComponent(uniqueId)}/face-captures/${encodeURIComponent(faceCaptures[0].id)}/file`}
                      alt="Latest camera capture"
                      className="w-40 h-32 object-cover rounded border border-slate-300"
                    />
                    <div>
                      <p className="text-base font-bold text-slate-800">
                        Latest camera capture
                      </p>
                      <p className="text-xs text-slate-500 mt-1">
                        {faceCaptures[0].capturedAt
                          ? new Date(
                              faceCaptures[0].capturedAt,
                            ).toLocaleString()
                          : "Time unavailable"}
                      </p>
                      <p className="text-xs text-slate-500 mt-2">
                        Source: {faceCaptures[0].source || "BROWSER_CAMERA"}
                      </p>
                    </div>
                  </div>
                )}
              </div>
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden mt-4">
                <div className="bg-slate-100 px-5 py-3 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wide">
                      Verified Documents
                    </h2>

                    <p className="text-xs text-slate-500 mt-1">
                      Add another document whenever you need.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold bg-sky-100 text-sky-900 px-2 py-1 rounded">
                      {documents.length} DOCUMENT
                      {documents.length === 1 ? "" : "S"}
                    </span>
                  </div>
                </div>

                {documents.length === 0 ? (
                  <div className="p-8 text-center">
                    <p className="text-base font-semibold text-slate-700">
                      No verified documents found.
                    </p>

                    <p className="text-sm text-slate-500 mt-1">
                      Upload and verify a document to see it here.
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-200">
                    {documents.map((document, index) => {
                      const riskScore = Number(document.riskScore ?? 0);

                      const riskLabel = getRiskLabel(riskScore);

                      return (
                        <div
                          key={document.id ?? index}
                          className="p-5 hover:bg-slate-50 transition-colors"
                        >
                          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                            <div className="flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="text-base font-bold text-slate-900 uppercase">
                                  {document.idType || "Document"}
                                </h3>

                                {String(document.finalStatus || "VERIFIED").toUpperCase() === "PENDING_REVIEW" ? (
                                  <span className="text-xs font-bold bg-amber-100 text-amber-700 px-2 py-1 rounded">
                                    PENDING REVIEW
                                  </span>
                                ) : (
                                  <span className="text-xs font-bold bg-green-100 text-green-700 px-2 py-1 rounded">
                                    VERIFIED
                                  </span>
                                )}
                              </div>

                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                                <div>
                                  <p className="text-xs font-bold text-slate-500 uppercase">
                                    Document Number
                                  </p>

                                  <p className="text-sm font-semibold text-slate-800 mt-1">
                                    {document.documentNumber || "Not Available"}
                                  </p>
                                </div>

                                <div>
                                  <p className="text-xs font-bold text-slate-500 uppercase">
                                    Verification Date
                                  </p>

                                  <p className="text-sm font-semibold text-slate-800 mt-1">
                                    {document.createdAt || "Not Available"}
                                  </p>
                                </div>

                                <div>
                                  <p className="text-xs font-bold text-slate-500 uppercase">
                                    Risk Assessment
                                  </p>

                                  <p className="text-sm font-bold text-green-700 mt-1">
                                    {riskScore} / 100 — {riskLabel}
                                  </p>
                                </div>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 self-start lg:self-center">
                              <button
                                type="button"
                                onClick={() => openDocument(document.id)}
                                className="bg-sky-900 hover:bg-sky-800 text-white px-4 py-2 rounded text-sm font-bold uppercase transition-all"
                              >
                                View Document
                              </button>

                              <button
                                type="button"
                                aria-label={`Delete saved ${document.idType || "document"}`}
                                title="Delete saved document"
                                disabled={removingDocumentId === document.id}
                                onClick={() =>
                                  handleRemoveDocument(document.id)
                                }
                                className="w-10 h-10 rounded border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 flex items-center justify-center transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                {removingDocumentId === document.id ? (
                                  <span className="text-sm font-bold">...</span>
                                ) : (
                                  <Trash2 size={17} aria-hidden="true" />
                                )}
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 mt-4">
                <p className="text-xs text-slate-500 leading-relaxed">
                  <span className="font-bold text-slate-700">
                    DRISHTI AI NOTICE:
                  </span>{" "}
                  This portal displays documents and screening records that were
                  successfully stored after Drishti AI screening. Screening
                  evidence does not by itself constitute a legal authenticity
                  verdict.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
