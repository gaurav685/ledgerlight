"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, ApiError } from "@/lib/api";
import type { ReviewTaskOut } from "@/lib/types";

function ReviewQueue() {
  const [tasks, setTasks] = useState<ReviewTaskOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ReviewTaskOut[]>("/review/tasks")
      .then(setTasks)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load queue"));
  }, []);

  return (
    <div>
      <h1>Review queue</h1>
      {error && <div className="error-banner">{error}</div>}
      <table>
        <thead>
          <tr>
            <th>Reason</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Created</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tasks && tasks.length === 0 && (
            <tr>
              <td colSpan={5}>No real open review tasks.</td>
            </tr>
          )}
          {tasks?.map((task) => (
            <tr key={task.id}>
              <td>{task.reason_code}</td>
              <td>{task.priority}</td>
              <td>{task.status}</td>
              <td>{task.created_at}</td>
              <td>
                <Link href={`/review/${task.id}`}>Review</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ReviewPage() {
  return (
    <RequireAuth>
      <ReviewQueue />
    </RequireAuth>
  );
}
