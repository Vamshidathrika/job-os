import { useState, useEffect } from 'react';
import { Cpu } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { ProfilePage } from './pages/ProfilePage';
import { JobMatchesPage } from './pages/JobMatchesPage';
import { ApplicationsPage } from './pages/ApplicationsPage';
import { ReferralsPage } from './pages/ReferralsPage';
import { InterviewPrepPage } from './pages/InterviewPrepPage';
import { CalendarIntegrationsPage } from './pages/CalendarIntegrationsPage';
import { ReviewInboxPage } from './pages/ReviewInboxPage';
import type { PipelineStats, SecurityStatus, ActionItem } from './types';

export function App() {
  const [activeSection, setActiveSection] = useState<string>('matches');
  const [apiToken, setApiToken] = useState<string>(() => localStorage.getItem('jobos_token') || '');
  const [tokenInput, setTokenInput] = useState<string>('');
  const [authError, setAuthError] = useState<string>('');

  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [bandBActions, setBandBActions] = useState<ActionItem[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const [referrerInput, setReferrerInput] = useState({ shared_school: true, shared_past_company: true, same_department: true, seniority_match: true });
  const [referrerScore, setReferrerScore] = useState<number | null>(null);

  const [interviewInput, setInterviewInput] = useState({ title: 'Tech Lead', company: 'Stripe', type: 'technical' });
  const [interviewPrepResult, setInterviewPrepResult] = useState<any>(null);

  const [nudgeResult, setNudgeResult] = useState<any>(null);
  const [integrationsStatus, setIntegrationsStatus] = useState<any>(null);
  const [ghostJobs, setGhostJobs] = useState<any[]>([]);
  const [careerGraph, setCareerGraph] = useState<any>(null);
  const [races, setRaces] = useState<any[]>([]);
  const [shadowModeReal, setShadowModeReal] = useState<boolean | null>(null);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [lastExecuteResult, setLastExecuteResult] = useState<any>(null);

  const fetchAllPhaseData = async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${apiToken}` };
      const [sRes, secRes, jRes, bRes, pendRes, intRes, ghostRes, cgRes, raceRes, smRes] = await Promise.all([
        fetch('/api/stats', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/security/status', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/jobs', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/actions?band=B', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/actions?status=pending', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/integrations/status').then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/calibration/ghost-jobs').then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/career-graph/summary', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/warmpath/races', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/shadow-mode', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);

      setStats(sRes);
      setSecurityStatus(secRes);
      setJobs(jRes);
      setBandBActions(bRes);
      setPendingActions(pendRes);
      setIntegrationsStatus(intRes);
      setGhostJobs(ghostRes);
      setCareerGraph(cgRes);
      setRaces(raceRes);
      setShadowModeReal(smRes?.enabled ?? null);
    } catch (err) {
      console.error('API error fetching dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (apiToken) fetchAllPhaseData();
  }, [apiToken]);

  const handleSignIn = async () => {
    const candidate = tokenInput.trim();
    if (!candidate) return;
    const res = await fetch('/api/stats', { headers: { Authorization: `Bearer ${candidate}` } });
    if (!res.ok) {
      setAuthError(res.status === 401 ? 'Token rejected. Check it and try again.' : `Server error (${res.status}).`);
      return;
    }
    localStorage.setItem('jobos_token', candidate);
    setAuthError('');
    setApiToken(candidate);
  };

  const handleScoreReferrer = async () => {
    const res = await fetch('/api/referral/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(referrerInput),
    }).then((r) => r.json());
    setReferrerScore(res.score);
  };

  const handleGeneratePrep = async () => {
    const res = await fetch('/api/interview/prep', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: interviewInput.title, company: interviewInput.company, interview_type: interviewInput.type }),
    }).then((r) => r.json());
    setInterviewPrepResult(res);
  };

  const handleStatusNudge = async () => {
    const res = await fetch('/api/followup/nudge?company=Stripe&role=Staff+AI+Engineer&days_since=5').then((r) => r.json());
    setNudgeResult(res);
  };

  const handleExecuteAction = async (id: string) => {
    setExecutingId(id);
    try {
      const res = await fetch(`/api/actions/${id}/execute`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiToken}` },
      });
      const body = await res.json();
      setLastExecuteResult(body);
      setBandBActions(bandBActions.filter((a) => a.action_id !== id));
      setPendingActions(pendingActions.filter((a) => a.action_id !== id));
    } finally {
      setExecutingId(null);
    }
  };

  const handleInboxActed = (actionId: string) => {
    setPendingActions(pendingActions.filter((a) => a.action_id !== actionId));
    setBandBActions(bandBActions.filter((a) => a.action_id !== actionId));
  };

  const handleToggleShadowMode = async () => {
    const next = !shadowModeReal;
    const res = await fetch(`/api/shadow-mode?enabled=${next}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiToken}` },
    }).then((r) => r.json());
    setShadowModeReal(res.enabled);
  };

  if (!apiToken) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div style={{ padding: '32px', maxWidth: '520px', width: '100%', border: '1px solid var(--border-color)', borderRadius: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <div style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', padding: '10px', borderRadius: '12px', display: 'flex' }}>
              <Cpu size={24} color="#fff" />
            </div>
            <h1 style={{ fontSize: '1.4rem' }}>JOBOS</h1>
          </div>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '20px' }}>
            Paste your API token to continue. Mint one with:
          </p>
          <code style={{ display: 'block', background: 'rgba(0,0,0,0.35)', padding: '10px 12px', borderRadius: '8px', fontSize: '0.75rem', color: '#06b6d4', marginBottom: '20px', overflowX: 'auto' }}>
            jobos --user-id &lt;your-uuid&gt; token create --name browser
          </code>
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSignIn(); }}
            placeholder="jobos_..."
            style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.05)', color: '#fff', fontSize: '0.9rem', marginBottom: '12px' }}
          />
          {authError && <p style={{ color: '#f87171', fontSize: '0.8rem', marginBottom: '12px' }}>{authError}</p>}
          <button
            onClick={handleSignIn}
            style={{ width: '100%', padding: '12px', borderRadius: '8px', border: 'none', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', fontSize: '0.9rem', cursor: 'pointer', fontWeight: 600 }}
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar activeSection={activeSection} onSelect={setActiveSection} />
      <div className="app-content">
        <TopBar
          onSync={fetchAllPhaseData}
          syncing={loading}
          shadowModeReal={shadowModeReal}
          onToggleShadowMode={handleToggleShadowMode}
          onSignOut={() => { localStorage.removeItem('jobos_token'); setApiToken(''); }}
          pendingCount={pendingActions.length}
          onOpenInbox={() => setActiveSection('inbox')}
        />

        {activeSection === 'inbox' && (
          <ReviewInboxPage token={apiToken} pending={pendingActions} onActed={handleInboxActed} />
        )}
        {activeSection === 'profile' && (
          <ProfilePage token={apiToken} careerGraph={careerGraph} onImported={fetchAllPhaseData} />
        )}
        {activeSection === 'matches' && <JobMatchesPage token={apiToken} jobs={jobs} />}
        {activeSection === 'applications' && (
          <ApplicationsPage
            bandBActions={bandBActions}
            executingId={executingId}
            lastExecuteResult={lastExecuteResult}
            onExecute={handleExecuteAction}
            nudgeResult={nudgeResult}
            onGenerateNudge={handleStatusNudge}
          />
        )}
        {activeSection === 'referrals' && (
          <ReferralsPage
            races={races}
            referrerInput={referrerInput}
            referrerScore={referrerScore}
            onReferrerInputChange={setReferrerInput}
            onScoreReferrer={handleScoreReferrer}
          />
        )}
        {activeSection === 'interview-prep' && (
          <InterviewPrepPage
            interviewInput={interviewInput}
            interviewPrepResult={interviewPrepResult}
            onInterviewInputChange={setInterviewInput}
            onGeneratePrep={handleGeneratePrep}
          />
        )}
        {activeSection === 'calendar' && (
          <CalendarIntegrationsPage
            integrationsStatus={integrationsStatus}
            securityStatus={securityStatus}
            ghostJobs={ghostJobs}
          />
        )}
      </div>
    </div>
  );
}

export default App;
