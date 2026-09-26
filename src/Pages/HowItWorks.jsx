export default function HowItWorks() {
  const steps = [
    [
      "01",
      "Login & Account Security",
      "Login securely with your registered account. Only authenticated users can access the verification portal.",
    ],
    [
      "02",
      "Document Upload",
      "Select the document type, enter the reference details, and upload a clear document image for OCR and verification.",
    ],
    [
      "03",
      "OCR & Document Analysis",
      "Drishti AI extracts document information such as name, date of birth and document number, then checks the document data.",
    ],
    [
      "04",
      "Live Face Capture",
      "Position one face inside the camera guide. A red border means the face is not ready; a green border means the face is properly detected and centered.",
    ],
    [
      "05",
      "Face Verification",
      "The captured face is compared with the face detected in the uploaded document. The verification threshold is 60%.",
    ],
    [
      "06",
      "Identity & Risk Result",
      "The system compares reference and extracted details and generates the final identity, face-match and risk result.",
    ],
    [
      "07",
      "Secure Audit Log",
      "Completed verification results and successful login activity are recorded in the audit history for monitoring and review.",
    ],
  ];

  return (
    <div className="site-page w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8 space-y-8">
      <div className="bg-white border border-slate-300 rounded-lg p-6 shadow-sm">
        <h1 className="text-3xl font-bold text-sky-950">
          How Drishti AI Works
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Secure Login, Document OCR, Face Verification &amp; Risk Analysis
          Workflow
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {steps.map(([num, title, text], index) => (
          <div
            key={num}
            className={`bg-white border-t-4 ${
              index === 6 ? "border-emerald-600" : "border-sky-900"
            } border-x border-b border-slate-300 rounded-b-lg p-5 shadow-sm space-y-2`}
          >
            <div
              className={`w-8 h-8 ${
                index === 6
                  ? "bg-emerald-100 text-emerald-950"
                  : "bg-sky-100 text-sky-950"
              } rounded-full flex items-center justify-center font-bold text-base`}
            >
              {num}
            </div>

            <h2 className="text-base font-bold text-slate-800 uppercase">
              {title}
            </h2>

            <p className="text-sm text-slate-600 leading-relaxed">{text}</p>
          </div>
        ))}
      </div>

      <div className="bg-white border border-slate-300 rounded-lg p-6 shadow-sm space-y-4">
        <h2 className="text-lg font-bold text-slate-800 border-b pb-3 uppercase tracking-wider">
          Core Operational Modules
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
          <div className="space-y-2">
            <h3 className="text-sm font-bold text-sky-900 uppercase">
              • Secure Login
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Authenticated users can access the verification portal and perform
              authorized document verification.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-sky-900 uppercase">
              • OCR &amp; Identity Check
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Document information is extracted through OCR and compared with
              the reference details provided by the user.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-sky-900 uppercase">
              • Face Verification
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              One centered face is captured and compared with the document face
              using the configured 60% verification threshold.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-sky-900 uppercase">
              • Live Camera Screening
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              The camera guide changes from red to green only when a valid face
              is properly detected and positioned.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-sky-900 uppercase">
              • Risk Analysis
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Document quality, identity consistency, face verification and
              other checks contribute to the final verification result.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold text-sky-900 uppercase">
              • Audit Logs
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Completed verification results and successful login activity are
              maintained for secure audit tracking.
            </p>
          </div>
        </div>
      </div>

      <div className="bg-slate-900 text-white rounded-lg p-6 shadow-md">
        <h3 className="text-base font-bold uppercase tracking-wider text-emerald-400">
          Verification Workflow
        </h3>

        <p className="text-sm text-slate-300 mt-1">
          Login → Document Upload → OCR Analysis → Enter Details → Center Face →
          Capture → Face Verification → Risk Result → Audit Log
        </p>
      </div>
    </div>
  );
}
