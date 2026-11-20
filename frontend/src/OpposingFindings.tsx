import { useState } from "react";
import type { Contradiction, OpposingStatement } from "./api";
import type { FindingQuestion } from "./ComparisonStudio";
import { SavePassage } from "./SavedEvidence";
import { sourceLink } from "./sourceLink";

export function OpposingFindings({pairs, ask, workspaceId, focus}: {
  pairs: Contradiction[]; ask: (question: FindingQuestion) => void; workspaceId?: number;
  focus?: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return <section className="panel opposing-findings">
    <h2>Potential disagreements</h2>
    <p>Pairs require opposite comparisons of the same methods and matching reported evaluation conditions. Review the full methods before drawing a conclusion.</p>
    {!pairs.length && <p className="muted">The reviewed excerpts did not provide a pair that met these conditions.</p>}
    {pairs.slice(0, expanded ? pairs.length : 4).map(({left, right, conditions}, index) => <article className="claim-group" key={index}>
      <h3>{conditions.subject} vs. {conditions.baseline} · {conditions.metric}</h3>
      <dl className="opposing-conditions">
        {["dataset", "task", "split", "protocol"].map(key => <div key={key}><dt>{key}</dt><dd>{conditions[key]}</dd></div>)}
      </dl>
      <div className="opposing-sources">
        <StatementCard statement={left} baseline={conditions.baseline} focus={focus} workspaceId={workspaceId} />
        <StatementCard statement={right} baseline={conditions.baseline} focus={focus} workspaceId={workspaceId} />
      </div>
      <button className="secondary" onClick={() => ask({
        documentIds:[left.source.document_id, right.source.document_id], workspaceId,
        question:`Do these two reported findings use comparable conditions for ${conditions.subject} versus ${conditions.baseline}? Explain possible reasons for the opposing statements about ${conditions.metric} on ${conditions.dataset}, cite both papers, and flag remaining uncertainty.`,
      })}>Ask Assistant about this pair</button>
    </article>)}
    {pairs.length > 4 && <button className="secondary" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
      {expanded ? "Show fewer pairs" : `Show all ${pairs.length} pairs`}
    </button>}
  </section>;
}

function StatementCard({statement, baseline, focus, workspaceId}: {
  statement: OpposingStatement; baseline: string; focus?: (id: string) => void; workspaceId?: number;
}) {
  const {document_id, chunk_id, page_start, page_end} = statement.source;
  const id = statement.finding_id;
  return <section className="finding-card">
    <strong>{statement.title}</strong>
    <p className="muted">{statement.direction === "better" ? "Reports outperforming" : "Reports underperforming"} {baseline}</p>
    <blockquote>{statement.quote}</blockquote>
    <div className="finding-actions">
      <a href={sourceLink(document_id, page_start, chunk_id, workspaceId)}>Open source · {page_start === page_end ? `p. ${page_start}` : `pp. ${page_start}–${page_end}`}</a>
      <SavePassage id={chunk_id} />
      {id && focus && <button className="secondary" onClick={() => focus(id)}>Show in graph</button>}
    </div>
  </section>;
}
