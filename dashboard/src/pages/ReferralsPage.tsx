interface ReferrerInput {
  shared_school: boolean;
  shared_past_company: boolean;
  same_department: boolean;
  seniority_match: boolean;
}

interface ReferralsPageProps {
  races: any[];
  referrerInput: ReferrerInput;
  referrerScore: number | null;
  onReferrerInputChange: (next: ReferrerInput) => void;
  onScoreReferrer: () => void;
}

export function ReferralsPage({
  races,
  referrerInput,
  referrerScore,
  onReferrerInputChange,
  onScoreReferrer,
}: ReferralsPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Referrals</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Referrer 4-Factor Quality Scorer</h3>
          <div style={{ display: 'grid', gap: '8px', fontSize: '0.85rem' }}>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.shared_school}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, shared_school: e.target.checked })}
              />{' '}
              Shared School (+0.3)
            </label>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.shared_past_company}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, shared_past_company: e.target.checked })}
              />{' '}
              Shared Past Company (+0.4)
            </label>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.same_department}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, same_department: e.target.checked })}
              />{' '}
              Same Department (+0.2)
            </label>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.seniority_match}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, seniority_match: e.target.checked })}
              />{' '}
              Seniority Match (+0.1)
            </label>
            <button
              onClick={onScoreReferrer}
              style={{ marginTop: '8px', background: 'var(--accent-purple)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}
            >
              Calculate Referrer Score
            </button>
          </div>
        </div>

        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Calculated Warmth Score</h3>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-purple)' }}>
            {referrerScore !== null ? `${(referrerScore * 100).toFixed(0)}%` : 'Click to score'}
          </div>
        </div>
      </div>

      <h3 style={{ fontSize: '1rem', marginBottom: '12px' }}>Warm-Path Races</h3>
      {races.length === 0 ? (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No warm-path races yet — starts automatically for Tier 1 matches when <code>jobos race</code>{' '}
          runs and a real LinkedIn connection exists at that company.
        </span>
      ) : (
        <div className="scroll-x" style={{ display: 'grid', gap: '10px' }}>
          {races.map((r, idx) => (
            <div key={idx} style={{ padding: '16px', background: 'rgba(168, 85, 247, 0.1)', borderRadius: '10px', border: '1px solid rgba(168, 85, 247, 0.3)' }}>
              <strong>
                {r.company} — {r.title}
              </strong>
              <div style={{ marginTop: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Status: {r.status}
                {r.resolution && ` (${r.resolution})`}
                {r.responded_channel && ` — response via ${r.responded_channel}`}
                {r.status === 'running' && ` — deadline ${new Date(r.deadline_at).toLocaleDateString()}`}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
