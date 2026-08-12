import { useState } from 'react';
import { authFetch } from '../api';
import type { ActionItem } from '../types';

interface ReviewInboxPageProps {
  token: string;
  pending: ActionItem[];
  onActed: (actionId: string) => void;
}

export function ReviewInboxPage({ token, pending, onActed }: ReviewInboxPageProps) {
  const [busyId, setBusyId] = useState<string | null>(null);

  const act = async (actionId: string, verb: 'execute' | 'reject') => {
    setBusyId(actionId);
    try {
      await authFetch(`/api/actions/${actionId}/${verb}`, token, { method: 'POST' });
      onActed(actionId);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Needs your review</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Every send, apply, or schedule action stops here first. Nothing runs until you approve it.
      </p>
      {pending.length === 0 ? (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Nothing pending.</span>
      ) : (
        <div className="scroll-x" style={{ display: 'grid', gap: '10px' }}>
          {pending.map((item) => (
            <div
              key={item.action_id}
              style={{
                padding: '14px',
                background: 'rgba(255,255,255,0.03)',
                borderRadius: '10px',
                border: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '12px',
              }}
            >
              <div>
                <strong style={{ fontSize: '0.9rem' }}>{item.action_type}</strong>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  Band {item.band}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                <button
                  onClick={() => act(item.action_id, 'reject')}
                  disabled={busyId === item.action_id}
                  style={{
                    background: 'rgba(244, 63, 94, 0.15)',
                    color: '#f87171',
                    border: '1px solid rgba(244, 63, 94, 0.3)',
                    padding: '6px 14px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  Reject
                </button>
                <button
                  onClick={() => act(item.action_id, 'execute')}
                  disabled={busyId === item.action_id}
                  style={{
                    background: 'var(--accent-emerald)',
                    color: '#fff',
                    border: 'none',
                    padding: '6px 14px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {busyId === item.action_id ? 'Working…' : 'Approve'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
