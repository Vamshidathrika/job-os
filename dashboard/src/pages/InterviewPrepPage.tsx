interface InterviewInput {
  title: string;
  company: string;
  type: string;
}

interface InterviewPrepPageProps {
  interviewInput: InterviewInput;
  interviewPrepResult: any;
  onInterviewInputChange: (next: InterviewInput) => void;
  onGeneratePrep: () => void;
}

export function InterviewPrepPage({
  interviewInput,
  interviewPrepResult,
  onInterviewInputChange,
  onGeneratePrep,
}: InterviewPrepPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Interview Prep</h2>

      <div style={{ padding: '12px 14px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', color: '#fbbf24', fontSize: '0.85rem', marginBottom: '20px' }}>
        Not yet wired into the pipeline: <code>jobos/tailorer/entailment.py</code> implements a
        cross-family verification gate and is tested, but nothing calls it before tailored resume
        text ships.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Target Role & Company</label>
          <input
            type="text"
            value={`${interviewInput.title} at ${interviewInput.company}`}
            onChange={(e) =>
              onInterviewInputChange({
                ...interviewInput,
                title: e.target.value.split(' at ')[0] || interviewInput.title,
              })
            }
            style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
          />
          <button
            onClick={onGeneratePrep}
            style={{ width: '100%', background: 'var(--accent-purple)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}
          >
            Generate Prep Pack
          </button>
        </div>

        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Generated Prep Pack</h3>
          {interviewPrepResult ? (
            <pre style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', overflow: 'auto', maxHeight: '150px' }}>
              {JSON.stringify(interviewPrepResult, null, 2)}
            </pre>
          ) : (
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Click generate to preview prep pack...</span>
          )}
        </div>
      </div>
    </div>
  );
}
