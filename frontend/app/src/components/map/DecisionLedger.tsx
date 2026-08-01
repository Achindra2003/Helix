import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listDecisions } from "@/lib/api";
import type { Decision } from "@/lib/types";
import { Spinner, EmptyState } from "@/components/common/Feedback";
import s from "@/routes/map.module.css";

/** "What did the team decide, and why?"
 *
 * The stemma answers what shape the thinking took. This answers the question a
 * person actually arrives with after a week away. Without it the record exists
 * but has no reader: you would open every conversation and inspect every
 * branch to find the four verdicts that matter.
 *
 * Newest first, because catching up runs backwards.
 */
export function DecisionLedger({ wid }: { wid: string }) {
  const nav = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["decisions", wid],
    queryFn: () => listDecisions(wid),
  });

  if (isLoading) return <Spinner />;
  const items: Decision[] = data?.items ?? [];

  if (items.length === 0) {
    return (
      <EmptyState title="Nothing decided yet">
        Fork a thread to try something, then record what came of it. Every
        verdict lands here, with the reason it was made.
      </EmptyState>
    );
  }

  return (
    <div className={s.ledger}>
      {items.map((d) => (
        <button
          key={d.branch_id}
          className={s.ledgerRow}
          data-status={d.status}
          onClick={() => nav(`/w/${wid}?conv=${d.conversation_id}&branch=${d.branch_id}`)}
          title="Open the thread this was decided in"
        >
          <span className={s.ledgerMark}>{d.status === "adopted" ? "✓" : "✕"}</span>
          <span className={s.ledgerBody}>
            {/* The reason leads. It is the part that has to survive — the
                labels and titles are how you find it again, not what it says. */}
            <span className={s.ledgerWhy}>{d.resolution}</span>
            <span className={s.ledgerMeta}>
              <b>{d.status === "adopted" ? "Adopted" : "Abandoned"}</b>
              {d.intent && <> · was trying: {d.intent}</>}
            </span>
            <span className={s.ledgerWhere}>
              {d.conversation_title} → {d.branch_name}
              {d.visibility === "private" && <span className={s.ledgerPrivate}> ◍ private</span>}
              {d.resolved_by_email && <> · {d.resolved_by_email}</>}
              {d.resolved_at && <> · {d.resolved_at.slice(0, 10)}</>}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}
