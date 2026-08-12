import { Cpu, RefreshCw, Eye, Zap, Bell } from 'lucide-react';

interface TopBarProps {
  onSync: () => void;
  syncing: boolean;
  shadowModeReal: boolean | null;
  onToggleShadowMode: () => void;
  onSignOut: () => void;
  pendingCount: number;
  onOpenInbox: () => void;
}

export function TopBar({
  onSync,
  syncing,
  shadowModeReal,
  onToggleShadowMode,
  onSignOut,
  pendingCount,
  onOpenInbox,
}: TopBarProps) {
  return (
    <header
      style={{
        padding: '16px 24px',
        marginBottom: '24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid var(--border-color)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
            padding: '10px',
            borderRadius: '12px',
            display: 'flex',
          }}
        >
          <Cpu size={22} color="#fff" />
        </div>
        <h1 style={{ fontSize: '1.2rem' }}>JOBOS</h1>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onOpenInbox}
          style={{
            position: 'relative',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid var(--border-color)',
            padding: '8px 14px',
            borderRadius: '8px',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.8rem',
          }}
        >
          <Bell size={14} />
          Needs your review
          {pendingCount > 0 && (
            <span
              style={{
                background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
                color: '#fff',
                borderRadius: '9999px',
                fontSize: '0.7rem',
                fontWeight: 700,
                padding: '1px 7px',
              }}
            >
              {pendingCount}
            </span>
          )}
        </button>

        <button
          onClick={onSync}
          style={{
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid var(--border-color)',
            padding: '8px 14px',
            borderRadius: '8px',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.8rem',
          }}
        >
          <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
          Sync
        </button>

        <button
          onClick={onToggleShadowMode}
          disabled={shadowModeReal === null}
          title="Toggles tenants.autonomy_mode for real — this changes what the send-guard actually allows."
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '10px',
            border:
              shadowModeReal === null
                ? '1px solid var(--border-color)'
                : shadowModeReal
                ? '1px solid rgba(245, 158, 11, 0.4)'
                : '1px solid rgba(16, 185, 129, 0.4)',
            background:
              shadowModeReal === null
                ? 'rgba(255,255,255,0.03)'
                : shadowModeReal
                ? 'rgba(245, 158, 11, 0.15)'
                : 'rgba(16, 185, 129, 0.15)',
            color: shadowModeReal === null ? 'var(--text-muted)' : shadowModeReal ? '#fbbf24' : '#34d399',
            fontWeight: 600,
            fontSize: '0.8rem',
          }}
        >
          {shadowModeReal !== false ? <Eye size={16} /> : <Zap size={16} />}
          {shadowModeReal === null ? 'Loading…' : shadowModeReal ? 'Shadow mode' : 'Autopilot live'}
        </button>

        <button
          onClick={onSignOut}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '0.8rem',
            textDecoration: 'underline',
          }}
        >
          sign out
        </button>
      </div>
    </header>
  );
}
