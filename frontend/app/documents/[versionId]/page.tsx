"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type { DocumentPageTextOut, SignedDocumentLinkOut } from "@/lib/types";

// Phase 5 §4: renders the real, immutable extracted page text
// (ledgerlight.db.models.DocumentPage.raw_text) and highlights the
// exact cited char_start/char_end span against it -- never a
// rendered PDF's own coordinates, since no real per-page PDF
// rendering is built. "Download the original" uses a real, signed,
// time-limited URL, fetched fresh on click (never cached past its
// real 5-minute server-side TTL).
function highlightedText(rawText: string, start: number | null, end: number | null) {
  if (start === null || end === null || start < 0 || end > rawText.length || start >= end) {
    return <>{rawText}</>;
  }
  return (
    <>
      {rawText.slice(0, start)}
      <mark className="evidence-highlight">{rawText.slice(start, end)}</mark>
      {rawText.slice(end)}
    </>
  );
}

function DocumentViewer() {
  const params = useParams<{ versionId: string }>();
  const searchParams = useSearchParams();
  const pageNumber = Number(searchParams.get("page") ?? "1");
  const charStart = searchParams.get("char_start");
  const charEnd = searchParams.get("char_end");

  const [page, setPage] = useState<DocumentPageTextOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  const [signedUrlError, setSignedUrlError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<DocumentPageTextOut>(`/documents/${params.versionId}/pages/${pageNumber}`)
      .then(setPage)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load page"));
  }, [params.versionId, pageNumber]);

  async function handleGetSignedUrl() {
    setSignedUrlError(null);
    try {
      const result = await apiFetch<SignedDocumentLinkOut>(
        `/documents/${params.versionId}/signed-url`,
      );
      setSignedUrl(result.url);
    } catch (err) {
      setSignedUrlError(err instanceof ApiError ? err.message : "Failed to get a signed link");
    }
  }

  return (
    <div>
      <h1>
        Document version {params.versionId} -- page {pageNumber}
      </h1>
      {error && <div className="error-banner">{error}</div>}
      {page && (
        <pre className="page-text">
          {highlightedText(
            page.raw_text,
            charStart !== null ? Number(charStart) : null,
            charEnd !== null ? Number(charEnd) : null,
          )}
        </pre>
      )}
      <p>
        <button type="button" className="btn secondary" onClick={handleGetSignedUrl}>
          Get a real, time-limited link to the original file
        </button>
      </p>
      {signedUrlError && <p>{signedUrlError}</p>}
      {signedUrl && (
        <p>
          <a href={signedUrl} target="_blank" rel="noreferrer">
            Open original (link expires soon)
          </a>
        </p>
      )}
    </div>
  );
}

export default function DocumentViewerPage() {
  return (
    <RequireAuth>
      <DocumentViewer />
    </RequireAuth>
  );
}
