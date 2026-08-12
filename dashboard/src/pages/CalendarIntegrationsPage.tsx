import type { SecurityStatus } from '../types';

interface CalendarIntegrationsPageProps {
  integrationsStatus: any;
  securityStatus: SecurityStatus | null;
  ghostJobs: any[];
}

export function CalendarIntegrationsPage({
  integrationsStatus,
  securityStatus,
  ghostJobs,
}: CalendarIntegrationsPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Calendar & Integrations</h2>

      <div style={{ padding: '16px', background: 'rgba(99, 102, 241, 0.1)', borderRadius: '10px', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#818cf8', fontSize: '0.9rem', marginBottom: '10px' }}>
        Gmail: <strong>{integrationsStatus ? integrationsStatus.gmail : 'Checking…'}</strong>
        <br />
        Calendar: <strong>{integrationsStatus ? integrationsStatus.calendar : 'Checking…'}</strong>
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '24px' }}>
        "Configured" means a Composio key is set — it does not mean a human has completed the
        OAuth connection for this tenant. That can only be verified with a live Composio call.
      </p>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          Advanced: security & circuit breaker
        </summary>
        <div style={{ display: 'grid', gap: '12px', marginTop: '12px' }}>
          <div style={{ padding: '12px', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: '8px', color: '#f87171', fontSize: '0.85rem' }}>
            {securityStatus ? (
              <>
                Circuit Breaker: {securityStatus.circuit_breaker.action_counts.applies}/
                {securityStatus.circuit_breaker.limits.applies} daily applies,{' '}
                {securityStatus.circuit_breaker.action_counts.emails}/
                {securityStatus.circuit_breaker.limits.emails} daily emails used
              </>
            ) : (
              'Loading circuit breaker status…'
            )}
          </div>
          <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', fontSize: '0.85rem' }}>
            Ghost Job Detector: {ghostJobs.length} stale listings flagged (&gt;60 days inactive)
            <span style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              Checks one fixture job, not this tenant's real listings.
            </span>
          </div>
          {securityStatus && (
            <div style={{ display: 'grid', gap: '8px' }}>
              {securityStatus.prohibitions.map((p, idx) => (
                <div key={idx} style={{ padding: '10px 14px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem' }}>
                  ✓ {p}
                </div>
              ))}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
