import { useRef, useState } from 'react';

interface ProfilePageProps {
  token: string;
  careerGraph: { bullets_total: number; bullets_verified: number; linkedin_connections: number } | null;
  onImported: () => void;
}

export function ProfilePage({ token, careerGraph, onImported }: ProfilePageProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/onboarding/linkedin-import', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        setError(`Import failed (${res.status}).`);
        return;
      }
      onImported();
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Profile & LinkedIn</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Upload your LinkedIn data export (Settings → Data privacy → Get a copy of your data, on
        linkedin.com). Live LinkedIn login isn't supported — the export is the only source that
        doesn't risk your account.
      </p>

      <div
        style={{
          border: '1px dashed var(--border-color)',
          borderRadius: '10px',
          padding: '24px',
          textAlign: 'center',
          marginBottom: '20px',
        }}
      >
        <input
          ref={fileInput}
          type="file"
          accept=".zip"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUpload(file);
          }}
        />
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          style={{
            background: 'var(--accent-indigo)',
            color: '#fff',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '8px',
            fontWeight: 600,
            fontSize: '0.85rem',
          }}
        >
          {uploading ? 'Importing…' : 'Upload LinkedIn export (.zip)'}
        </button>
        {error && <p style={{ color: '#f87171', fontSize: '0.8rem', marginTop: '10px' }}>{error}</p>}
      </div>

      {careerGraph ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '10px' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{careerGraph.bullets_total}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Career Graph bullets</div>
          </div>
          <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '14px', borderRadius: '10px' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#34d399' }}>
              {careerGraph.bullets_verified}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Verified (tailoring-eligible)</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '10px' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{careerGraph.linkedin_connections}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>LinkedIn connections imported</div>
          </div>
        </div>
      ) : (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No profile imported yet.</span>
      )}
    </div>
  );
}
