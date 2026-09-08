import React from 'react';
import { describeStep } from '../lib/executionSteps';

/**
 * The full sequence of graph steps (validate -> plan -> execute -> advance ->
 * ... -> respond) as connected nodes in a line -- the "clear tag of the tool
 * chain" this app needs, without surfacing the raw planner reasoning text.
 * `vertical` stacks the nodes in a column (used in the narrow left panel)
 * instead of a wrapping horizontal row. `activeLast` pulses the most recent
 * node (the request is still streaming in more steps behind it).
 */
export default function StepTimeline({ steps, vertical = false, activeLast = false }) {
  if (!steps || steps.length === 0) return null;
  const described = steps.map(describeStep);

  return (
    <div className={`step-timeline ${vertical ? 'step-timeline-vertical' : ''}`}>
      {described.map((step, i) => {
        const isLast = i === described.length - 1;
        const tone = step.ok === true ? 'step-node-ok' : step.ok === false ? 'step-node-error' : 'step-node-pending';
        return (
          <React.Fragment key={i}>
            <span className={`step-node ${tone} ${activeLast && isLast ? 'step-node-active' : ''}`}>
              <span className="step-dot" />
              {step.label}
            </span>
            {!isLast && <span className="step-connector" />}
          </React.Fragment>
        );
      })}
    </div>
  );
}
