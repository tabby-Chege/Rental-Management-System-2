import { useEffect, useState } from "react";
import { getCurrentUser } from "../../api/authAPI";
import { listLeases, listMyLeases } from "../../api/leasesAPI";
import {
  downloadPrivateFile,
  listLeaseDocuments,
  uploadLeaseDocument,
} from "../../api/landlordToolsApi";
import "../manage.css";

function LeaseDocumentsPage() {
  const [leases, setLeases] = useState([]);
  const [selectedLeaseId, setSelectedLeaseId] = useState("");
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let ignore = false;
    async function loadLeases() {
      try {
        const { user } = await getCurrentUser();
        const result = user.role === "tenant" ? await listMyLeases() : await listLeases();
        if (!ignore) {
          setLeases(result);
          setSelectedLeaseId((current) => current || String(result[0]?.id ?? ""));
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadLeases();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedLeaseId) {
      setDocuments([]);
      return undefined;
    }
    let ignore = false;
    listLeaseDocuments(selectedLeaseId)
      .then((result) => {
        if (!ignore) {
          setDocuments(result);
          setError("");
        }
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      });
    return () => {
      ignore = true;
    };
  }, [selectedLeaseId]);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedLeaseId) return;
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const result = await uploadLeaseDocument(selectedLeaseId, file);
      setDocuments((current) => [result.document, ...current]);
      setNotice("Lease document uploaded securely.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDownload(document) {
    setError("");
    try {
      await downloadPrivateFile(
        document.download_url,
        document.filename || `lease-document-${document.id}`,
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <section className="manage-page">
      <h1>Lease documents</h1>
      <p className="manage-status">
        Share and securely download documents attached to your lease.
      </p>
      {error && <p className="manage-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {loading ? (
        <p className="manage-status">Loading leases…</p>
      ) : leases.length === 0 ? (
        <p className="manage-status">No leases are available for your account yet.</p>
      ) : (
        <>
          <label className="manage-field">
            <span>Lease</span>
            <select
              value={selectedLeaseId}
              onChange={(event) => setSelectedLeaseId(event.target.value)}
            >
              {leases.map((lease) => (
                <option key={lease.id} value={lease.id}>
                  Lease #{lease.id} · Unit #{lease.unit_id} · {lease.start_date}
                </option>
              ))}
            </select>
          </label>
          <label className="manage-field">
            <span>Upload agreement or supporting document (PDF/JPEG/PNG/WebP, max 10 MB)</span>
            <input
              type="file"
              accept="application/pdf,image/jpeg,image/png,image/webp"
              disabled={uploading}
              onChange={handleUpload}
            />
          </label>
          {uploading && <p className="manage-status">Uploading securely…</p>}
          {documents.length === 0 ? (
            <p className="manage-status">No documents have been shared for this lease.</p>
          ) : (
            <ul className="manage-list">
              {documents.map((document) => (
                <li className="manage-card" key={document.id}>
                  <div>
                    <strong>{document.filename}</strong>
                    <p>
                      {document.content_type} · {Math.ceil(document.file_size / 1024)} KB
                    </p>
                    <small>Uploaded {new Date(document.uploaded_at).toLocaleString()}</small>
                  </div>
                  <button
                    className="manage-button is-secondary"
                    type="button"
                    onClick={() => handleDownload(document)}
                  >
                    Download
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

export default LeaseDocumentsPage;
