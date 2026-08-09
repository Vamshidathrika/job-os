import React, { useState } from 'react';
import { 
  Zap, Shield, TrendingUp, Users, DollarSign, Calendar, CheckCircle2, 
  AlertTriangle, Clock, Eye, Send, Play, Cpu, Lock, FileText, ChevronRight,
  Sparkles, Activity, Layers, Bell, RefreshCw
} from 'lucide-react';

interface ActionItem {
  id: string;
  company: string;
  role: string;
  band: 'A' | 'B' | 'C';
  type: string;
  ev_score: number;
  tier: number;
  status: string;
  created: string;
}

export function App() {
  const [activeTab, setActiveTab] = useState<'queue' | 'warmpath' | 'comp' | 'interview' | 'vault'>('queue');
  const [shadowMode, setShadowMode] = useState<boolean>(true);
  const [circuitBreakerStatus] = useState({ applies: 12, maxApplies: 20, emails: 4, maxEmails: 10 });

  // Mock data representing JOBOS live state
  const [actions, setActions] = useState<ActionItem[]>([
    { id: 'act-001', company: 'Stripe', role: 'Staff AI Engineer', band: 'A', type: 'Cold Apply (Tailored)', ev_score: 68500, tier: 1, status: 'Ready for execution', created: '10 mins ago' },
    { id: 'act-002', company: 'Linear', role: 'Lead Platform Architect', band: 'B', type: 'Referral Outreach Touch 1', ev_score: 54000, tier: 1, status: 'Pending user review', created: '25 mins ago' },
    { id: 'act-003', company: 'Vercel', role: 'Senior Systems Engineer', band: 'A', type: 'Cold Apply (Tailored)', ev_score: 42000, tier: 2, status: 'Ready for execution', created: '1 hour ago' },
    { id: 'act-004', company: 'Datadog', role: 'Principal AI Ops', band: 'C', type: 'CTC Field Mandatory Escalation', ev_score: 79000, tier: 1, status: 'Human intervention required', created: '2 hours ago' },
  ]);

  const [selectedCompRole, setSelectedCompRole] = useState({ title: 'Senior AI Engineer', location: 'India', yoe: 5 });
  const [compPrediction, setCompPrediction] = useState({ p25: 3200000, p50: 4200000, p75: 5500000, currency: 'INR' });

  const handleExecuteAction = (id: string) => {
    setActions(actions.filter(a => a.id !== id));
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
              <span className="badge badge-band-a" style={{ fontSize: '0.65rem' }}>RLS SECURED</span>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Multi-Tenant Autonomous Career Execution Engine</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          {/* Circuit Breaker Badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.05)', padding: '8px 14px', borderRadius: '10px', fontSize: '0.8rem' }}>
            <Activity size={14} color="#10b981" />
            <span>Circuit Breaker: <strong style={{ color: '#10b981' }}>{circuitBreakerStatus.applies}/{circuitBreakerStatus.maxApplies} Applies</strong></span>
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
            {shadowMode ? 'SHADOW MODE (PROPOSE ONLY)' : 'AUTOPILOT ACTIVE (LIVE EXECUTION)'}
          </button>
        </div>
      </header>

      {/* SYSTEM STATS TICKER */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Jobs Tracked</span>
            <Layers size={18} color="var(--accent-cyan)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>142</div>
          <span style={{ fontSize: '0.75rem', color: 'var(--accent-emerald)' }}>+18 this week from ATS radar</span>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Avg EV Score</span>
            <TrendingUp size={18} color="var(--accent-indigo)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>$54,200</div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>EV = P(offer) × Comp × P(accept)</span>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Warm Path Races</span>
            <Send size={18} color="var(--accent-purple)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>7 Active</div>
          <span style={{ fontSize: '0.75rem', color: '#a855f7' }}>7-day race holding Tier 1 apps</span>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.85rem' }}>Entailment Gate</span>
            <Shield size={18} color="var(--accent-emerald)" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#34d399' }}>100% Pass</div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Rule 14 cross-family verified</span>
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
          onClick={() => setActiveTab('interview')}
          style={{
            padding: '10px 20px',
            borderRadius: '10px',
            background: activeTab === 'interview' ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
            border: activeTab === 'interview' ? '1px solid var(--accent-emerald)' : '1px solid transparent',
            color: activeTab === 'interview' ? '#fff' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <FileText size={16} />
          Interview Prep & Debrief Studio
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
          Security Vault & Isolation
        </button>
      </div>

      {/* TAB CONTENT: ACTION QUEUE */}
      {activeTab === 'queue' && (
        <div style={{ display: 'grid', gap: '16px' }}>
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h2 style={{ fontSize: '1.2rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={20} color="var(--accent-indigo)" />
              Band-Aware Execution Queue
            </h2>
            <div style={{ display: 'grid', gap: '12px' }}>
              {actions.map((act) => (
                <div 
                  key={act.id} 
                  style={{ 
                    background: 'rgba(255,255,255,0.03)', 
                    border: '1px solid var(--border-color)', 
                    borderRadius: '12px', 
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifySpace: 'between',
                    gap: '16px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                    <span className={`badge badge-band-${act.band.toLowerCase()}`}>
                      BAND {act.band}
                    </span>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '1rem' }}>{act.role} <span style={{ color: 'var(--text-muted)' }}>at</span> {act.company}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'flex', gap: '12px', marginTop: '2px' }}>
                        <span>Type: {act.type}</span>
                        <span>•</span>
                        <span>Tier {act.tier}</span>
                        <span>•</span>
                        <span>EV: ${act.ev_score.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{act.created}</span>
                    <button 
                      onClick={() => handleExecuteAction(act.id)}
                      style={{
                        background: act.band === 'A' ? 'linear-gradient(135deg, #10b981, #059669)' : act.band === 'B' ? 'linear-gradient(135deg, #f59e0b, #d97706)' : 'linear-gradient(135deg, #ef4444, #dc2626)',
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
                      {act.band === 'A' ? 'Auto-Execute' : act.band === 'B' ? 'Approve & Run' : 'Escalate to Human'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB CONTENT: WARM PATH RACE */}
      {activeTab === 'warmpath' && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Active 7-Day Warm Path Races</h2>
          <div style={{ display: 'grid', gap: '16px' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <strong style={{ fontSize: '1rem' }}>Stripe — Staff AI Engineer (Tier 1)</strong>
                <span style={{ color: 'var(--accent-purple)', fontWeight: 600 }}>Day 3 of 7</span>
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                Outreach active across Referral (Apollo candidate found) + Recruiter Direct Message. Cold apply held until Day 7 fallback.
              </p>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: '42%', height: '100%', background: 'linear-gradient(90deg, #6366f1, #a855f7)' }}></div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB CONTENT: COMP INTELLIGENCE */}
      {activeTab === 'comp' && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Salary Band Predictor & Deflector</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '12px' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '12px' }}>Role & Location Inputs</h3>
              <div style={{ display: 'grid', gap: '12px' }}>
                <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Target Role Title</label>
                <input 
                  type="text" 
                  value={selectedCompRole.title}
                  onChange={(e) => setSelectedCompRole({...selectedCompRole, title: e.target.value})}
                  style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '10px', borderRadius: '8px' }}
                />

                <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Location (Multiplier: India 1.0x, US 3.0x)</label>
                <select 
                  value={selectedCompRole.location}
                  onChange={(e) => setSelectedCompRole({...selectedCompRole, location: e.target.value})}
                  style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '10px', borderRadius: '8px' }}
                >
                  <option value="India">India (1.0x)</option>
                  <option value="Singapore">Singapore (1.3x)</option>
                  <option value="US">US (3.0x)</option>
                </select>
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '12px' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '12px' }}>Predicted Compensation Bands</h3>
              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
                  <span>P25 (Conservative)</span>
                  <strong style={{ color: 'var(--accent-cyan)' }}>₹{(compPrediction.p25/100000).toFixed(1)}L</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'rgba(99, 102, 241, 0.15)', borderRadius: '6px', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                  <span>P50 (Median Market Target)</span>
                  <strong style={{ color: 'var(--accent-indigo)' }}>₹{(compPrediction.p50/100000).toFixed(1)}L</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
                  <span>P75 (Top Tier)</span>
                  <strong style={{ color: 'var(--accent-purple)' }}>₹{(compPrediction.p75/100000).toFixed(1)}L</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB CONTENT: INTERVIEW PREP */}
      {activeTab === 'interview' && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Interview Prep & Post-Interview Studio</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            JOBOS automatically generates comprehensive prep packs prior to scheduled interviews and blocks 60-minute prep windows on Google Calendar.
          </p>
        </div>
      )}

      {/* TAB CONTENT: SECURITY VAULT */}
      {activeTab === 'vault' && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Lock size={20} color="var(--accent-rose)" />
            Envelope Encryption Vault & RLS Status
          </h2>
          <div style={{ display: 'grid', gap: '12px' }}>
            <div style={{ padding: '12px 16px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem' }}>
              ✓ Postgres Row Level Security (RLS) active on all tables with FORCE ROW LEVEL SECURITY
            </div>
            <div style={{ padding: '12px 16px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem' }}>
              ✓ Envelope AES-256-GCM encryption active for tenant API keys & vault credentials
            </div>
            <div style={{ padding: '12px 16px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem' }}>
              ✓ Structlog Allowlist Scrubber scrubbing bearer tokens, openrouter, groq, and AWS keys
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
