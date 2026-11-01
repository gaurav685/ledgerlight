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
