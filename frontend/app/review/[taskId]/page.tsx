"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type { ReviewTaskOut } from "@/lib/types";

const DECISIONS = ["approve", "approve_with_edits", "reject", "escalate"] as const;

function ReviewTaskDetail() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const [task, setTask] = useState<ReviewTaskOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<string>(DECISIONS[0]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiFetch<ReviewTaskOut>(`/review/tasks/${params.taskId}`)
      .then(setTask)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load task"));
  }, [params.taskId]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch<ReviewTaskOut>(`/review/tasks/${params.taskId}/decision`, {
        method: "POST",
        body: { decision, notes: notes || null },
      });
      router.push("/review");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to record decision");
    } finally {
      setSubmitting(false);
    }
  }

  if (!task) {
    return error ? <div className="error-banner">{error}</div> : <p>Loading...</p>;
  }

  return (
    <div>
      <h1>Review task</h1>
      <p>
        Reason: <strong>{task.reason_code}</strong> -- priority {task.priority} -- status{" "}
        {task.status}
      </p>
      {task.dossier_id && (
        <p>
          <a href={`/dossiers`}>Find this task&apos;s dossier in the dossiers list</a> (dossier id:{" "}
          {task.dossier_id})
        </p>
      )}

      {task.status === "closed" ? (
        <p>
          Already decided: <strong>{task.decision}</strong>
        </p>
      ) : (
        <form onSubmit={handleSubmit}>
          {error && <div className="error-banner">{error}</div>}
          <div className="field">
            <label htmlFor="decision">Decision</label>
            <select id="decision" value={decision} onChange={(e) => setDecision(e.target.value)}>
              {DECISIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="notes">Notes</label>
            <textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={4} />
          </div>
          <button type="submit" className="btn" disabled={submitting}>
            {submitting ? "Submitting..." : "Submit decision"}
          </button>
        </form>
      )}
    </div>
  );
}

export default function ReviewTaskPage() {
  return (
    <RequireAuth>
      <ReviewTaskDetail />
    </RequireAuth>
  );
}
