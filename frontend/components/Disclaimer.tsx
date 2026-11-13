// Phase 5 §4: the permanent, neutral-language disclaimer this
// brief's own ground rules require wherever a real score, event tier,
// or credibility figure is shown -- never conditionally hidden,
// never a dismissible one-time toast.
export function Disclaimer({ children }: { children: React.ReactNode }) {
  return <div className="disclaimer-banner">{children}</div>;
}

export function ModelLimitationsBanner({ text }: { text: string }) {
  return (
    <Disclaimer>
      <strong>Model limitations.</strong> This score is a statistical estimate from a
      model with disclosed, real limitations -- it is not investment advice, not a
      certification of wrongdoing, and not a substitute for independent due diligence.
      <details style={{ marginTop: 6 }}>
        <summary>Read the real, current limitations</summary>
        <p style={{ whiteSpace: "pre-wrap" }}>{text}</p>
      </details>
    </Disclaimer>
  );
}

export function EventTierDisclaimer() {
  return (
    <Disclaimer>
      Events marked <span className="badge candidate">CANDIDATE</span> have not passed
      this project&apos;s own real reliability bar for the VERIFIED tier -- treat them as
      leads to check, not confirmed facts.
    </Disclaimer>
  );
}

export function EventStudyDisclaimer() {
  return (
    <Disclaimer>
      <strong>Not investment advice. Not a trading signal.</strong> A measured market
      reaction around an already-disclosed event, never a causal claim that the event
      caused it. Figures below a company-page comparison line are this project&apos;s
      own pre-registered study (see <code>docs/enhancements/event-study/spec.md</code>),
      not a recommendation.
    </Disclaimer>
  );
}
