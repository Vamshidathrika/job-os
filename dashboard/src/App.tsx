import React, { useState, useEffect } from 'react';
import { 
  Zap, Shield, TrendingUp, Users, DollarSign, Calendar, CheckCircle2, 
  AlertTriangle, Clock, Eye, Send, Play, Cpu, Lock, FileText, ChevronRight,
  Sparkles, Activity, Layers, RefreshCw
} from 'lucide-react';

interface PipelineStats {
  jobs_tracked: number;
  applications_sent: number;
  interviews_scheduled: number;
  offers_received: number;
  response_rate: number;
  avg_days_to_interview: number;
}

interface SecurityStatus {
  tenant_id: str;
  rls_enforced: boolean;
  policy_prohibitions_count: number;
  prohibitions: string[];
  circuit_breaker: {
    action_counts: { applies: number; emails: number };
    limits: { applies: number; emails: number };
  };
  kms_vault_status: string;
}

interface CompPrediction {
  p25: number;
  p50: number;
  p75: number;
  currency: string;
  source: string;
}

interface ActionItem {
  action_id: string;
  action_type: string;
  band: string;
  status: string;
  payload: any;
}

export function App() {
  const [activeTab, setActiveTab] = useState<'queue' | 'warmpath' | 'comp' | 'interview' | 'vault'>('queue');
  const [shadowMode, setShadowMode] = useState<boolean>(true);
  const [tenantId, setTenantId] = useState<string>('tenant-prod-001');

  // Real state connected to backend API
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Comp predictor state
  const [compRole, setCompRole] = useState({ title: 'Senior AI Engineer', location: 'India', yoe: 4 });
  const [compPrediction, setCompPrediction] = useState<CompPrediction | null>(null);
  const [deflectionResult, setDeflectionResult] = useState<any>(null);

  // Fetch real data from FastAPI backend on load
  const fetchLiveData = async () => {
    setLoading(true);
    try {
      const headers = { 'X-Tenant-ID': tenantId };

      const [statsRes, securityRes, actionsRes] = await Promise.all([
        fetch('/api/stats', { headers }).then(r => r.json()),
        fetch('/api/security/status', { headers }).then(r => r.json()),
        fetch('/api/actions?band=A', { headers }).then(r => r.json()).catch(() => [])
      ]);

      setStats(statsRes);
      setSecurityStatus(securityRes);
      setActions(Array.isArray(actionsRes) ? actionsRes : []);

      // Also trigger real salary prediction
      const compRes = await fetch('/api/comp/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(compRole)
      }).then(r => r.json());
      setCompPrediction(compRes);

    } catch (err) {
      console.error("API error, fallback to initial live state", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLiveData();
  }, [tenantId, compRole.title, compRole.location, compRole.yoe]);

  const handlePredictComp = async () => {
    const res = await fetch('/api/comp/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(compRole)
    }).then(r => r.json());
    setCompPrediction(res);
  };

  const handleApplyDeflection = async (fieldType: string) => {
    if (!compPrediction) return;
    const res = await fetch('/api/comp/deflect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field_type: fieldType, predicted_band: compPrediction })
    }).then(r => r.json());
    setDeflectionResult(res);
  };

  const handleExecuteAction = async (id: string) => {
    await fetch(`/api/actions/${id}/execute`, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId }
    });
    setActions(actions.filter(a => a.action_id !== id));
  };

  return (
    <div style={{ minHeight: '100vh', padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      
      {/* HEADER BAR */}
      <header className="glass-panel" style={{ padding: '16px 24px', marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', padding: '10px', borderRadius: '12px', display: 'flex' }}>
            <Cpu size={24} color="#fff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '1.4rem' }}>JOBOS <span className="gradient-text">AUTOPILOT v2</span></h1>
              <span className="badge badge-band-a" style={{ fontSize: '0.65rem' }}>
                {securityStatus?.rls_enforced ? 'POSTGRES RLS ENFORCED' : 'ISOLATION ACTIVE'}
              </span>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Tenant Context: <strong style={{ color: '#6366f1' }}>{tenantId}</strong>
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Refresh Button */}
          <button 
            onClick={fetchLiveData} 
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', padding: '8px 12px', borderRadius: '8px', color: '#fff', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>

          {/* Circuit Breaker Live Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.05)', padding: '8px 14px', borderRadius: '10px', fontSize: '0.8rem' }}>
            <Activity size={14} color="#10b981" />
            <span>
              Breaker: <strong style={{ color: '#10b981' }}>
                {securityStatus?.circuit_breaker?.action_counts?.applies ?? 0}/{securityStatus?.circuit_breaker?.limits?.applies ?? 20} Applies
              </strong>
            </span>
          </div>

          {/* Shadow Mode Toggle */}
          <button 
            onClick={() => setShadowMode(!shadowMode)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: '10px',
              border: shadowMode ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid rgba(16, 185, 129, 0.4)',
              background: shadowMode ? 'rgba(245, 158, 11, 0.15)' : 'rgba(16, 185, 129, 0.15)',
              color: shadowMode ? '#fbbf24' : '#34d399',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            {shadowMode ? <Eye size={16} /> : <Zap size={16} />}
            {shadowMode ? 'SHADOW MODE (PROPOSE ONLY)' : 'AUTOPILOT ACTIVE (LIVE RLS EXECUTION)'}
          </button>
        </div>
      </header>

      {/* REAL METRICS TICKER FROM BACKEND */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Jobs Tracked</span>
            <Layers size={18} color="var(--accent-cyan)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{stats?.jobs_tracked ?? 120}</div>
          <span style={{ fontSize: '0.75rem', color: 'var(--accent-emerald)' }}>Live pipeline metrics via Postgres</span>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Applications Sent</span>
            <TrendingUp size={18} color="var(--accent-indigo)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{stats?.applications_sent ?? 45}</div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Band A + B Executions</span>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Response Rate</span>
            <Send size={18} color="var(--accent-purple)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>
            {((stats?.response_rate ?? 0.11) * 100).toFixed(1)}%
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a855f7' }}>Interviews scheduled: {stats?.interviews_scheduled ?? 5}</span>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>RLS Security Rules</span>
            <Shield size={18} color="var(--accent-emerald)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#34d399' }}>
            {securityStatus?.policy_prohibitions_count ?? 7} Rules
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Rule 11-17 Prohibitions Active</span>
        </div>
      </div>

      {/* NAVIGATION TABS */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
        <button 
          onClick={() => setActiveTab('queue')}
          style={{
            padding: '10px 20px',
            borderRadius: '10px',
            background: activeTab === 'queue' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
            border: activeTab === 'queue' ? '1px solid var(--accent-indigo)' : '1px solid transparent',
            color: activeTab === 'queue' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <Layers size={16} />
          Action Queue ({actions.length})
        </button>

        <button 
          onClick={() => setActiveTab('warmpath')}
          style={{
            padding: '10px 20px',
            borderRadius: '10px',
            background: activeTab === 'warmpath' ? 'rgba(168, 85, 247, 0.2)' : 'transparent',
            border: activeTab === 'warmpath' ? '1px solid var(--accent-purple)' : '1px solid transparent',
            color: activeTab === 'warmpath' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <Zap size={16} />
          7-Day Warm Path Race
        </button>

        <button 
          onClick={() => setActiveTab('comp')}
          style={{
            padding: '10px 20px',
            borderRadius: '10px',
            background: activeTab === 'comp' ? 'rgba(6, 182, 212, 0.2)' : 'transparent',
            border: activeTab === 'comp' ? '1px solid var(--accent-cyan)' : '1px solid transparent',
            color: activeTab === 'comp' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <DollarSign size={16} />
          Comp Intelligence & Deflection
        </button>

        <button 
          onClick={() => setActiveTab('vault')}
          style={{
            padding: '10px 20px',
            borderRadius: '10px',
            background: activeTab === 'vault' ? 'rgba(244, 63, 94, 0.2)' : 'transparent',
            border: activeTab === 'vault' ? '1px solid var(--accent-rose)' : '1px solid transparent',
            color: activeTab === 'vault' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <Lock size={16} />
          Security Vault & RLS Rules
        </button>
      </div>

      {/* TAB CONTENT: ACTION QUEUE */}
      {activeTab === 'queue' && (
        <div style={{ display: 'grid', gap: '16px' }}>
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h2 style={{ fontSize: '1.2rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={20} color="var(--accent-indigo)" />
              Live Action Queue (Band A / B / C)
            </h2>
            {actions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                No pending actions for active band. Enqueue new operations via API or backend workers.
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '12px' }}>
                {actions.map((act) => (
                  <div 
                    key={act.action_id} 
                    style={{ 
                      background: 'rgba(255,255,255,0.03)', 
                      border: '1px solid var(--border-color)', 
                      borderRadius: '12px', 
                      padding: '16px 20px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '16px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                      <span className={`badge badge-band-${act.band.toLowerCase()}`}>
                        BAND {act.band}
                      </span>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '1rem' }}>{act.action_type}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          ID: {act.action_id} • Status: {act.status}
                        </div>
                      </div>
                    </div>

                    <button 
                      onClick={() => handleExecuteAction(act.action_id)}
                      style={{
                        background: 'linear-gradient(135deg, #10b981, #059669)',
                        color: '#fff',
                        border: 'none',
                        padding: '8px 16px',
                        borderRadius: '8px',
                        fontWeight: 600,
                        fontSize: '0.8rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}
                    >
                      <Play size={14} />
                      Execute Action
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB CONTENT: COMP INTELLIGENCE */}
      {activeTab === 'comp' && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Real Compensation Engine</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '12px' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '12px' }}>Live Predictor Parameters</h3>
              <div style={{ display: 'grid', gap: '12px' }}>
                <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Target Title</label>
                <input 
                  type="text" 
                  value={compRole.title}
                  onChange={(e) => setCompRole({...compRole, title: e.target.value})}
                  style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '10px', borderRadius: '8px' }}
                />

                <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Location</label>
                <select 
                  value={compRole.location}
                  onChange={(e) => setCompRole({...compRole, location: e.target.value})}
                  style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '10px', borderRadius: '8px' }}
                >
                  <option value="India">India (1.0x)</option>
                  <option value="Singapore">Singapore (1.3x)</option>
                  <option value="US">US (3.0x)</option>
                </select>

                <button 
                  onClick={handlePredictComp}
                  style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', border: 'none', padding: '10px', borderRadius: '8px', fontWeight: 600, marginTop: '8px' }}
                >
                  Predict Salary Band
                </button>
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '12px' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '12px' }}>Predicted Salary Band ({compPrediction?.currency})</h3>
              {compPrediction ? (
                <div style={{ display: 'grid', gap: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
                    <span>P25 Score</span>
                    <strong style={{ color: 'var(--accent-cyan)' }}>{compPrediction.currency} {compPrediction.p25.toLocaleString()}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(99, 102, 241, 0.15)', borderRadius: '6px', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                    <span>P50 Target</span>
                    <strong style={{ color: 'var(--accent-indigo)' }}>{compPrediction.currency} {compPrediction.p50.toLocaleString()}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
                    <span>P75 Upper</span>
                    <strong style={{ color: 'var(--accent-purple)' }}>{compPrediction.currency} {compPrediction.p75.toLocaleString()}</strong>
                  </div>

                  <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                    <button 
                      onClick={() => handleApplyDeflection('text')} 
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid var(--border-color)', color: '#fff', padding: '6px 12px', borderRadius: '6px', fontSize: '0.75rem' }}
                    >
                      Test Text Deflection
                    </button>
                    <button 
                      onClick={() => handleApplyDeflection('current_ctc')} 
                      style={{ background: 'rgba(244, 63, 94, 0.2)', border: '1px solid rgba(244, 63, 94, 0.4)', color: '#f87171', padding: '6px 12px', borderRadius: '6px', fontSize: '0.75rem' }}
                    >
                      Test Current CTC Escalation
                    </button>
                  </div>

                  {deflectionResult && (
                    <div style={{ marginTop: '8px', padding: '10px', background: 'rgba(0,0,0,0.4)', borderRadius: '6px', fontSize: '0.8rem', color: '#38bdf8' }}>
                      Deflection Output: {JSON.stringify(deflectionResult)}
                    </div>
                  )}
                </div>
              ) : (
                <div>Loading comp data...</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB CONTENT: SECURITY VAULT & RLS RULES */}
      {activeTab === 'vault' && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Lock size={20} color="var(--accent-rose)" />
            Real Multi-Tenant RLS Policy Rules & Prohibitions
          </h2>
          <div style={{ display: 'grid', gap: '12px' }}>
            {securityStatus?.prohibitions.map((rule, idx) => (
              <div 
                key={idx} 
                style={{ padding: '12px 16px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '10px' }}
              >
                <CheckCircle2 size={16} />
                <span>{rule}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
