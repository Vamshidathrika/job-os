import type { ActionItem } from '../types';

interface ApplicationsPageProps {
  bandBActions: ActionItem[];
  executingId: string | null;
  lastExecuteResult: any;
  onExecute: (id: string) => void;
  nudgeResult: any;
  onGenerateNudge: () => void;
}

export function ApplicationsPage({
  bandBActions,
  executingId,
  lastExecuteResult,
  onExecute,
  nudgeResult,
  onGenerateNudge,
}: ApplicationsPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Applications</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Real Playwright form-filling. It fills the real application and screenshots it for you —
        it never clicks Submit, even from here. Approving below runs the fill and shows the
        result; finishing the actual application is your own action, in your own browser.
      </p>
      {bandBActions.filter((a) => a.action_type === 'submit_application').length === 0 ? (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Nothing queued for review.</span>
      ) : (
        <div className="scroll-x" style={{ display: 'grid', gap: '10px', marginBottom: '20px' }}>
          {bandBActions
            .filter((a) => a.action_type === 'submit_application')
            .map((act) => (
              <div
                key={act.action_id}
                style={{
                  padding: '14px',
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: '10px',
                  border: '1px solid var(--border-color)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {String(act.payload?.job_url ?? '')}
                </div>
                <button
                  onClick={() => onExecute(act.action_id)}
                  disabled={executingId === act.action_id}
                  style={{ background: 'var(--accent-cyan)', color: '#fff', border: 'none', padding: '6px 14px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600 }}
                >
                  {executingId === act.action_id ? 'Filling…' : 'Fill & preview'}
                </button>
              </div>
            ))}
        </div>
      )}
      {lastExecuteResult?.result?.screenshot_path && (
        <div style={{ padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', fontSize: '0.8rem', color: '#38bdf8', marginBottom: '20px' }}>
          Prepared: {lastExecuteResult.result.fields_filled} fields filled. Screenshot saved
          server-side at <code>{lastExecuteResult.result.screenshot_path}</code>.
        </div>
      )}
      <button onClick={onGenerateNudge} style={{ background: 'var(--accent-cyan)', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', fontWeight: 600, fontSize: '0.85rem' }}>
        Generate Follow-Up Nudge
      </button>
      {nudgeResult && (
        <div style={{ marginTop: '12px', padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', fontSize: '0.85rem', color: '#38bdf8' }}>
          Subject: {nudgeResult.subject}
          <br />
          <br />
          Body: {nudgeResult.body}
        </div>
      )}
    </div>
  );
}
