import { useRef, useState } from "react";
import { ApiError } from "../api/client";
import type { BulkResult } from "../api/types";
import Modal from "./Modal";

interface BulkUploadModalProps {
  title: string;
  columnsHint: string;
  onUpload: (file: File) => Promise<BulkResult>;
  onDownloadTemplate: () => Promise<void>;
  onClose: () => void;
  onDone: () => void;
}

export default function BulkUploadModal({
  title,
  columnsHint,
  onUpload,
  onDownloadTemplate,
  onClose,
  onDone,
}: BulkUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    if (!file) {
      setError("Please choose a .csv or .xlsx file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await onUpload(file));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        result ? (
          <button className="btn btn-primary" onClick={onDone}>
            Done
          </button>
        ) : (
          <>
            <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleUpload} disabled={busy || !file}>
              {busy ? "Uploading…" : "Upload"}
            </button>
          </>
        )
      }
    >
      {result ? (
        <div className="form-grid">
          <div className="alert alert-success full">
            Added <strong>{result.created}</strong> · Skipped{" "}
            <strong>{result.skipped}</strong>
          </div>
          {result.errors.length > 0 && (
            <div className="full">
              <p className="muted" style={{ marginBottom: 6 }}>
                Some rows were skipped:
              </p>
              <ul className="error-list">
                {result.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="form-grid">
          {error && <div className="alert alert-error full">{error}</div>}
          <p className="muted full">
            Upload a <strong>.csv</strong> or <strong>.xlsx</strong> file. Columns:{" "}
            {columnsHint}
          </p>
          <button
            type="button"
            className="link full"
            style={{ textAlign: "left" }}
            onClick={() => onDownloadTemplate().catch(() => setError("Could not download template"))}
          >
            ↓ Download a sample template
          </button>
          <div
            className="dropzone full"
            onClick={() => inputRef.current?.click()}
            role="button"
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm,text/csv"
              hidden
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
            />
            {file ? (
              <span className="dz-file">📄 {file.name}</span>
            ) : (
              <span className="muted">Click to choose a file…</span>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
