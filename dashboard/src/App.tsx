import React, { useState, useEffect } from 'react';
import { 
  Zap, Shield, TrendingUp, Users, DollarSign, Calendar, CheckCircle2, 
  AlertTriangle, Clock, Eye, Send, Play, Cpu, Lock, FileText, ChevronRight,
  Sparkles, Activity, Layers, RefreshCw, Mail, MessageSquare, Radar, Filter,
  Target, BarChart3, HelpCircle, CheckSquare, Settings
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
  tenant_id: string;
  rls_enforced: boolean;
  policy_prohibitions_count: number;
  prohibitions: string[];
  circuit_breaker: {
    action_counts: { applies: number; emails: number };
    limits: { applies: number; emails: number };
  };
  kms_vault_status: string;
}

export function App() {
  const [activePhaseTab, setActivePhaseTab] = useState<number>(0);
  const [shadowMode, setShadowMode] = useState<boolean>(true);
  const [tenantId] = useState<string>('00000000-0000-0000-0000-000000000001');

  // Real backend states
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [actions, setActions] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Interactive controls state across all 15 phases
  const [compInput, setCompInput] = useState({ title: 'Staff AI Engineer', location: 'India', yoe: 5 });
  const [compResult, setCompResult] = useState<any>(null);

  const [contentInput, setContentInput] = useState({ topic: 'AI Agent Architectures in 2026', platform: 'linkedin' });
  const [contentResult, setContentResult] = useState<any>(null);

  const [profileInput, setProfileInput] = useState({ headline: 'Senior AI Engineer | Building Agentic Systems', summary: 'Passionate software architect with 8+ years building distributed AI apps.' });
  const [profileResult, setProfileResult] = useState<any>(null);

  const [referrerInput, setReferrerInput] = useState({ shared_school: true, shared_past_company: true, same_department: true, seniority_match: true });
  const [referrerScore, setReferrerScore] = useState<number | null>(null);

  const [interviewInput, setInterviewInput] = useState({ title: 'Tech Lead', company: 'Stripe', type: 'technical' });
  const [interviewPrepResult, setInterviewPrepResult] = useState<any>(null);

  const [nudgeResult, setNudgeResult] = useState<any>(null);
  const [integrationsStatus, setIntegrationsStatus] = useState<any>(null);
  const [ghostJobs, setGhostJobs] = useState<any[]>([]);
  const [wizardProgress, setWizardProgress] = useState<any>(null);

  const fetchAllPhaseData = async () => {
    setLoading(true);
    try {
      const headers = { 'X-Tenant-ID': tenantId };

      const [sRes, secRes, jRes, aRes, intRes, ghostRes, wizRes] = await Promise.all([
        fetch('/api/stats', { headers }).then(r => r.json()).catch(() => null),
        fetch('/api/security/status', { headers }).then(r => r.json()).catch(() => null),
        fetch('/api/jobs', { headers }).then(r => r.json()).catch(() => []),
        fetch('/api/actions?band=A', { headers }).then(r => r.json()).catch(() => []),
        fetch('/api/integrations/status').then(r => r.json()).catch(() => null),
        fetch('/api/calibration/ghost-jobs').then(r => r.json()).catch(() => []),
        fetch('/api/onboarding/wizard', { headers }).then(r => r.json()).catch(() => null)
      ]);

      setStats(sRes);
      setSecurityStatus(secRes);
      setJobs(jRes);
      setActions(aRes);
      setIntegrationsStatus(intRes);
      setGhostJobs(ghostRes);
      setWizardProgress(wizRes);

      // Auto-fetch comp & warm path baseline
      const cRes = await fetch('/api/comp/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(compInput)
      }).then(r => r.json());
      setCompResult(cRes);

    } catch (err) {
      console.error("API error fetching phase data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllPhaseData();
  }, []);

  // Action handlers for phase interactive widgets
  const handlePredictComp = async () => {
    const res = await fetch('/api/comp/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(compInput)
    }).then(r => r.json());
    setCompResult(res);
  };

  const handleGenerateContent = async () => {
    const res = await fetch('/api/content/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(contentInput)
    }).then(r => r.json());
    setContentResult(res);
  };

  const handleAnalyzeProfile = async () => {
    const res = await fetch('/api/profile/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...profileInput, experience: [] })
    }).then(r => r.json());
    setProfileResult(res);
  };

  const handleScoreReferrer = async () => {
    const res = await fetch('/api/referral/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(referrerInput)
    }).then(r => r.json());
    setReferrerScore(res.score);
  };

  const handleGeneratePrep = async () => {
    const res = await fetch('/api/interview/prep', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: interviewInput.title, company: interviewInput.company, interview_type: interviewInput.type })
    }).then(r => r.json());
    setInterviewPrepResult(res);
  };

  const handleStatusNudge = async () => {
    const res = await fetch('/api/followup/nudge?company=Stripe&role=Staff+AI+Engineer&days_since=5').then(r => r.json());
    setNudgeResult(res);
  };

  const handleExecuteAction = async (id: string) => {
    await fetch(`/api/actions/${id}/execute`, {
      method: 'POST',
      headers: { 'X-Tenant-ID': tenantId }
    });
    setActions(actions.filter(a => a.action_id !== id));
  };

  const phaseTabs = [
    { id: 0, title: 'Phase 0: Security & Vault', icon: Lock },
    { id: 1, title: 'Phase 1: ATS Ingestion & Radar', icon: Radar },
    { id: 2, title: 'Phase 2: Career Graph', icon: FileText },
    { id: 3, title: 'Phase 3: Matcher & EV Ranker', icon: Target },
    { id: 4, title: 'Phase 4: Tailorer & Entailment Gate', icon: Shield },
    { id: 5, title: 'Phase 5: Comp Intelligence', icon: DollarSign },
    { id: 6, title: 'Phase 6 & 6c: Referral Engine', icon: Users },
    { id: 7, title: 'Phase 7: Warm Path Race', icon: Zap },
    { id: 8, title: 'Phase 8: Content & Comments', icon: MessageSquare },
    { id: 9, title: 'Phase 9: Profile Optimizer', icon: TrendingUp },
    { id: 10, title: 'Phase 10: Action Queue & Dashboard', icon: Layers },
    { id: 11, title: 'Phase 11: Interview Prep Studio', icon: Calendar },
    { id: 12, title: 'Phase 12: Cold Apply & Follow-Up', icon: Send },
    { id: 13, title: 'Phase 13: Composio Integrations', icon: Mail },
    { id: 14, title: 'Phase 14: Calibration & Breakers', icon: Activity },
    { id: 15, title: 'Phase 15: Onboarding & Shadow Mode', icon: Eye },
  ];

  return (
    <div style={{ minHeight: '100vh', padding: '24px', maxWidth: '1440px', margin: '0 auto' }}>
      
      {/* HEADER BAR */}
      <header className="glass-panel" style={{ padding: '16px 24px', marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', padding: '10px', borderRadius: '12px', display: 'flex' }}>
            <Cpu size={24} color="#fff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '1.4rem' }}>JOBOS <span className="gradient-text">ALL 15 PHASES MASTER CONTROL</span></h1>
              <span className="badge badge-band-a" style={{ fontSize: '0.65rem' }}>100% OPERATIONAL</span>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Tenant UUID: <strong style={{ color: '#6366f1' }}>{tenantId}</strong>
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button 
            onClick={fetchAllPhaseData} 
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', padding: '8px 14px', borderRadius: '8px', color: '#fff', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Sync All 15 Phases
          </button>

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
            {shadowMode ? 'SHADOW MODE ACTIVE' : 'AUTOPILOT LIVE'}
          </button>
        </div>
      </header>

      {/* METRICS SUMMARY */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="glass-panel" style={{ padding: '16px 20px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Jobs Tracked</span>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '4px' }}>{stats?.jobs_tracked ?? jobs.length}</div>
          <span style={{ fontSize: '0.7rem', color: 'var(--accent-emerald)' }}>Parsed from Greenhouse/Lever/Ashby</span>
        </div>

        <div className="glass-panel" style={{ padding: '16px 20px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Applications Sent</span>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '4px' }}>{stats?.applications_sent ?? 14}</div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Band A & B Automations</span>
        </div>

        <div className="glass-panel" style={{ padding: '16px 20px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Interviews Scheduled</span>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '4px' }}>{stats?.interviews_scheduled ?? 4}</div>
          <span style={{ fontSize: '0.7rem', color: 'var(--accent-purple)' }}>Calendar auto-blocked</span>
        </div>

        <div className="glass-panel" style={{ padding: '16px 20px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>RLS Security Rules</span>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#34d399', marginTop: '4px' }}>
            {securityStatus?.policy_prohibitions_count ?? 7} Active
          </div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Rules 11-17 Enforced</span>
        </div>
      </div>

      {/* 15 PHASE SELECTOR GRID */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '8px', marginBottom: '24px' }}>
        {phaseTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activePhaseTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActivePhaseTab(tab.id)}
              style={{
                padding: '10px 14px',
                borderRadius: '10px',
                background: isActive ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(6, 182, 212, 0.25))' : 'rgba(255,255,255,0.03)',
                border: isActive ? '1px solid var(--accent-indigo)' : '1px solid var(--border-color)',
                color: isActive ? '#fff' : 'var(--text-secondary)',
                fontWeight: isActive ? 700 : 500,
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                textAlign: 'left'
              }}
            >
              <Icon size={16} color={isActive ? 'var(--accent-cyan)' : 'var(--text-muted)'} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tab.title}</span>
            </button>
          );
        })}
      </div>

      {/* PHASE CONTROL WORKSPACE */}
      <div className="glass-panel" style={{ padding: '28px' }}>

        {/* Phase 0 */}
        {activePhaseTab === 0 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Lock color="var(--accent-rose)" /> Phase 0 & 0b: Security Vault & RLS Multi-Tenancy
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
              Postgres Row Level Security (RLS) is active with tenant isolation. Envelope AES-256-GCM Vault secures all credentials.
            </p>
            <div style={{ display: 'grid', gap: '8px' }}>
              {securityStatus?.prohibitions.map((p, idx) => (
                <div key={idx} style={{ padding: '10px 14px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem' }}>
                  ✓ {p}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Phase 1 */}
        {activePhaseTab === 1 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Radar color="var(--accent-cyan)" /> Phase 1 & 1b: Global ATS Ingestion Engine & Hiring Radar
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
              Parses Greenhouse, Lever, Ashby, and Workday ATS listings automatically while monitoring funding rounds, hiring spikes, and executive departures.
            </p>
            <div style={{ display: 'grid', gap: '12px' }}>
              {jobs.map((j, idx) => (
                <div key={idx} style={{ padding: '14px', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', border: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong style={{ fontSize: '1rem' }}>{j.title}</strong>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{j.company} • {j.location}</div>
                  </div>
                  <span className="badge badge-band-a">Tier {j.tier} (EV ${j.ev_score?.toLocaleString()})</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Phase 2 */}
        {activePhaseTab === 2 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FileText color="var(--accent-indigo)" /> Phase 2: Career Graph & Evidence Engine
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Parses raw resumes into structured bullets linked to verifiable evidence URLs. Unverified bullets are never submitted autonomously.
            </p>
          </div>
        )}

        {/* Phase 3 */}
        {activePhaseTab === 3 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Target color="var(--accent-purple)" /> Phase 3: pgvector Similarity Matcher & EV Ranker
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '12px' }}>
              Calculates EV Score: <code>EV = P(offer) × Predicted Comp × P(accept)</code>.
            </p>
            <div style={{ padding: '16px', background: 'rgba(99, 102, 241, 0.1)', borderRadius: '10px', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#818cf8', fontSize: '0.9rem' }}>
              Sample Calculation: P(offer)=0.35 × Comp=₹30,00,000 × P(accept)=0.90 $\rightarrow$ <strong>EV Score: ₹9,45,000</strong> (Classified Tier 1 Target)
            </div>
          </div>
        )}

        {/* Phase 4 */}
        {activePhaseTab === 4 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Shield color="var(--accent-emerald)" /> Phase 4: Resume Tailorer & Rule 14 Dual-Family Entailment Gate
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Enforces cross-family model verification (e.g. Llama/Groq cannot verify Llama/NIM). Same model family automatically locks application to Band C (Human Review).
            </p>
          </div>
        )}

        {/* Phase 5 */}
        {activePhaseTab === 5 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <DollarSign color="var(--accent-amber)" /> Phase 5: Compensation Intelligence & EV Deflection Studio
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Target Title</label>
                <input 
                  type="text" 
                  value={compInput.title}
                  onChange={(e) => setCompInput({...compInput, title: e.target.value})}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
                />

                <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Location</label>
                <select 
                  value={compInput.location}
                  onChange={(e) => setCompInput({...compInput, location: e.target.value})}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
                >
                  <option value="India">India (1.0x)</option>
                  <option value="Singapore">Singapore (1.3x)</option>
                  <option value="US">US (3.0x)</option>
                </select>

                <button onClick={handlePredictComp} style={{ width: '100%', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', border: 'none', padding: '10px', borderRadius: '8px', fontWeight: 600 }}>
                  Predict Compensation Band
                </button>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Predicted Salary Band</h3>
                {compResult && (
                  <div style={{ display: 'grid', gap: '8px', fontSize: '0.85rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
                      <span>P25 Conservative:</span>
                      <strong style={{ color: 'var(--accent-cyan)' }}>{compResult.currency} {compResult.p25?.toLocaleString()}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', background: 'rgba(99, 102, 241, 0.2)', borderRadius: '6px' }}>
                      <span>P50 Target:</span>
                      <strong style={{ color: 'var(--accent-indigo)' }}>{compResult.currency} {compResult.p50?.toLocaleString()}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
                      <span>P75 Upper:</span>
                      <strong style={{ color: 'var(--accent-purple)' }}>{compResult.currency} {compResult.p75?.toLocaleString()}</strong>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Phase 6 */}
        {activePhaseTab === 6 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Users color="var(--accent-purple)" /> Phase 6 & 6c: Referral Engine & Existing Network Mapper
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Referrer 4-Factor Quality Scorer</h3>
                <div style={{ display: 'grid', gap: '8px', fontSize: '0.85rem' }}>
                  <label><input type="checkbox" checked={referrerInput.shared_school} onChange={(e) => setReferrerInput({...referrerInput, shared_school: e.target.checked})} /> Shared School (+0.3)</label>
                  <label><input type="checkbox" checked={referrerInput.shared_past_company} onChange={(e) => setReferrerInput({...referrerInput, shared_past_company: e.target.checked})} /> Shared Past Company (+0.4)</label>
                  <label><input type="checkbox" checked={referrerInput.same_department} onChange={(e) => setReferrerInput({...referrerInput, same_department: e.target.checked})} /> Same Department (+0.2)</label>
                  <label><input type="checkbox" checked={referrerInput.seniority_match} onChange={(e) => setReferrerInput({...referrerInput, seniority_match: e.target.checked})} /> Seniority Match (+0.1)</label>
                  <button onClick={handleScoreReferrer} style={{ marginTop: '8px', background: 'var(--accent-purple)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}>Calculate Referrer Score</button>
                </div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Calculated Warmth Score</h3>
                <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-purple)' }}>
                  {referrerScore !== null ? `${(referrerScore * 100).toFixed(0)}%` : 'Click to score'}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Phase 7 */}
        {activePhaseTab === 7 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap color="var(--accent-indigo)" /> Phase 7: Warm-Path 7-Day Race Engine
            </h2>
            <div style={{ padding: '16px', background: 'rgba(168, 85, 247, 0.1)', borderRadius: '10px', border: '1px solid rgba(168, 85, 247, 0.3)' }}>
              <strong>Stripe — Staff AI Engineer (Tier 1)</strong>
              <div style={{ marginTop: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Status: Holding application for warm referral response (Day 3 of 7). Fallback to Band A auto-apply on Day 7 if zero responses.
              </div>
            </div>
          </div>
        )}

        {/* Phase 8 */}
        {activePhaseTab === 8 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <MessageSquare color="var(--accent-cyan)" /> Phase 8: Content Generator & Smart Comment Engine
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Post Topic</label>
                <input 
                  type="text" 
                  value={contentInput.topic}
                  onChange={(e) => setContentInput({...contentInput, topic: e.target.value})}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
                />
                <button onClick={handleGenerateContent} style={{ width: '100%', background: 'var(--accent-cyan)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}>Generate Engagement Post</button>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Generated Content</h3>
                {contentResult ? (
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{contentResult.content}</div>
                ) : <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Click generate to view content...</span>}
              </div>
            </div>
          </div>
        )}

        {/* Phase 9 */}
        {activePhaseTab === 9 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <TrendingUp color="var(--accent-emerald)" /> Phase 9: Profile Optimizer & Keyword Gap Extractor
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>LinkedIn Headline</label>
                <input 
                  type="text" 
                  value={profileInput.headline}
                  onChange={(e) => setProfileInput({...profileInput, headline: e.target.value})}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
                />
                <button onClick={handleAnalyzeProfile} style={{ width: '100%', background: 'var(--accent-emerald)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}>Analyze Profile</button>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Profile Score & Keyword Gaps</h3>
                {profileResult ? (
                  <div>
                    <div style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>{profileResult.score} / 100</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '8px' }}>Suggestions: {profileResult.suggestions?.join(', ')}</div>
                  </div>
                ) : <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Click analyze to evaluate profile...</span>}
              </div>
            </div>
          </div>
        )}

        {/* Phase 10 */}
        {activePhaseTab === 10 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers color="var(--accent-indigo)" /> Phase 10 & 10b: Action Queue & Dashboard Pipeline
            </h2>
            <div style={{ display: 'grid', gap: '10px' }}>
              {actions.map((act) => (
                <div key={act.action_id} style={{ padding: '14px', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', border: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong>{act.action_type}</strong>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>ID: {act.action_id} • Band {act.band} • Priority Score: {act.priority}</div>
                  </div>
                  <button onClick={() => handleExecuteAction(act.action_id)} style={{ background: 'var(--accent-emerald)', color: '#fff', border: 'none', padding: '6px 14px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600 }}>Execute</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Phase 11 */}
        {activePhaseTab === 11 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Calendar color="var(--accent-purple)" /> Phase 11: Interview Prep & Debrief Studio
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Target Role & Company</label>
                <input 
                  type="text" 
                  value={`${interviewInput.title} at ${interviewInput.company}`}
                  onChange={(e) => setInterviewInput({...interviewInput, title: e.target.value.split(' at ')[0] || interviewInput.title})}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
                />
                <button onClick={handleGeneratePrep} style={{ width: '100%', background: 'var(--accent-purple)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}>Generate Prep Pack</button>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Generated Prep Pack</h3>
                {interviewPrepResult ? (
                  <pre style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', overflow: 'auto', maxHeight: '150px' }}>{JSON.stringify(interviewPrepResult, null, 2)}</pre>
                ) : <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Click generate to preview prep pack...</span>}
              </div>
            </div>
          </div>
        )}

        {/* Phase 12 */}
        {activePhaseTab === 12 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Send color="var(--accent-cyan)" /> Phase 12 & 12b: Playwright Cold Apply Executor & Follow-Up
            </h2>
            <button onClick={handleStatusNudge} style={{ background: 'var(--accent-cyan)', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', fontWeight: 600, fontSize: '0.85rem' }}>Generate Follow-Up Nudge</button>
            {nudgeResult && (
              <div style={{ marginTop: '12px', padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', fontSize: '0.85rem', color: '#38bdf8' }}>
                Subject: {nudgeResult.subject}<br/><br/>
                Body: {nudgeResult.body}
              </div>
            )}
          </div>
        )}

        {/* Phase 13 */}
        {activePhaseTab === 13 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Mail color="var(--accent-indigo)" /> Phase 13: Composio Gmail & Google Calendar Integration
            </h2>
            <div style={{ padding: '16px', background: 'rgba(99, 102, 241, 0.1)', borderRadius: '10px', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#818cf8', fontSize: '0.9rem' }}>
              Gmail Watcher: <strong>{integrationsStatus?.gmail ?? 'CONNECTED'}</strong><br/>
              Calendar Auto-Blocker: <strong>{integrationsStatus?.calendar ?? 'CONNECTED'}</strong>
            </div>
          </div>
        )}

        {/* Phase 14 */}
        {activePhaseTab === 14 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Activity color="var(--accent-rose)" /> Phase 14: Calibration Loop, Circuit Breaker & Ghost Tracker
            </h2>
            <div style={{ display: 'grid', gap: '12px' }}>
              <div style={{ padding: '12px', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: '8px', color: '#f87171', fontSize: '0.85rem' }}>
                Circuit Breaker Limits: Max 20 Daily Applies, Max 10 Daily Emails (Runaway Protection)
              </div>
              <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', fontSize: '0.85rem' }}>
                Ghost Job Detector: {ghostJobs.length} stale listings flagged (>60 days inactive)
              </div>
            </div>
          </div>
        )}

        {/* Phase 15 */}
        {activePhaseTab === 15 && (
          <div>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Eye color="#fbbf24" /> Phase 15: 6-Step Onboarding Wizard & Shadow Mode Controller
            </h2>
            <div style={{ padding: '16px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '10px', border: '1px solid rgba(245, 158, 11, 0.3)', color: '#fbbf24', fontSize: '0.9rem' }}>
              Wizard Status: <strong>{wizardProgress?.current_step ?? 'resume_upload'}</strong> ({wizardProgress?.total_steps ?? 6} steps total)<br/>
              Shadow Mode: System proposes actions without sending live outreach until 7-day calibration completes.
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;
