import { useState } from "react";

export default function HelpIcon() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-[9999] text-lg">
      {isOpen && (
        <div className="mb-3 w-80 bg-white border border-slate-300 rounded-lg shadow-2xl p-4 text-slate-800 text-sm space-y-3">
          <div className="flex justify-between items-center border-b pb-2">
            <h3 className="font-bold text-sky-900 text-base">
              System Help & Guidance
            </h3>

            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-slate-600 font-bold text-base px-1"
            >
              ✕
            </button>
          </div>

          <div className="space-y-2">
            <div>
              <p className="font-bold text-slate-700">1. Document Upload:</p>
              <p className="text-slate-500">
                Select the document type and upload a clear document image.
              </p>
            </div>

            <div>
              <p className="font-bold text-slate-700">2. Enter Details:</p>
              <p className="text-slate-500">
                Enter the reference details correctly before verification.
              </p>
            </div>

            <div>
              <p className="font-bold text-slate-700">3. Face Capture:</p>
              <p className="text-slate-500">
                Keep one face centered inside the camera frame.
              </p>
            </div>

            <div>
              <p className="font-bold text-slate-700">4. Camera Status:</p>
              <p className="text-slate-500">
                Red border means face is not ready. Green border means face is
                ready.
              </p>
            </div>

            <div>
              <p className="font-bold text-slate-700">5. Face Verification:</p>
              <p className="text-slate-500">
                The captured face is compared with the document face.
              </p>
            </div>

            <div>
              <p className="font-bold text-slate-700">
                6. Verification Result:
              </p>
              <p className="text-slate-500">
                Check the face score, OCR details, identity match and risk
                result.
              </p>
            </div>

            <div>
              <p className="font-bold text-slate-700">7. Audit Logs:</p>
              <p className="text-slate-500">
                Verification results and successful login activity are recorded.
              </p>
            </div>
          </div>

          <div className="border-t pt-2 text-xs text-slate-400 text-center font-mono">
            Drishti Control Portal Support
          </div>
        </div>
      )}

      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-10 h-10 bg-sky-900 hover:bg-sky-800 text-white rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-110 focus:outline-none"
        title="Need Help?"
        type="button"
      >
        <span className="font-bold text-xl font-serif italic">?</span>
      </button>
    </div>
  );
}
