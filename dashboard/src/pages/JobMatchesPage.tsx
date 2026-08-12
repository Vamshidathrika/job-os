import { useState } from 'react';
import { authFetch } from '../api';
import type { Job } from '../types';

interface JobMatchesPageProps {
  token: string;
  jobs: Job[];
}

export function JobMatchesPage({ token, jobs }: JobMatchesPageProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{ web_view_link?: string; detail?: string } | null>(null);

  const scored = jobs.filter((j) => j.tier != null);

  const generateResume = async (job: Job) => {
    setGenerating(true);
    setResult(null);
    try {
      const res = await authFetch<{ web_view_link?: string }>(
        `/api/jobs/${job.id}/generate-resume`,
        token,
        { method: 'POST' }
      );
      setResult(res ?? { detail: 'Generation failed — see server logs.' });
    } finally {
      setGenerating(false);
    }
  };

  if (scored.length === 0) {
    return (
      <div>
        <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Job Matches</h2>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No jobs scored yet — run <code>jobos match</code>.
        </span>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Job Matches</h2>
      <div className="scroll-x" style={{ display: 'grid', gap: '10px' }}>
        {scored.map((j, idx) => (
          <div
            key={idx}
            style={{
              padding: '14px',
              background: 'rgba(255,255,255,0.03)',
              borderRadius: '10px',
              border: '1px solid var(--border-color)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer',
              }}
              onClick={() => setOpenIdx(openIdx === idx ? null : idx)}
            >
              <div>
                <strong style={{ fontSize: '1rem' }}>{j.title}</strong>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {j.company} • {j.location}
                </div>
              </div>
              <span className="badge badge-band-a">
                Tier {j.tier} (EV ${j.ev_score?.toLocaleString()})
              </span>
            </div>
            {openIdx === idx && (
              <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
                <button
                  onClick={() => generateResume(j)}
                  disabled={generating}
                  style={{
                    background: 'var(--accent-indigo)',
                    color: '#fff',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {generating ? 'Generating…' : 'Generate tailored resume'}
                </button>
                {result && (
                  <div style={{ marginTop: '10px', fontSize: '0.8rem' }}>
                    {result.web_view_link ? (
                      <a href={result.web_view_link} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-cyan)' }}>
                        Open in Drive
                      </a>
                    ) : (
                      <span style={{ color: '#f87171' }}>{result.detail}</span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
