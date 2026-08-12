import { User, Target, Send, Users, Calendar, Settings } from 'lucide-react';

const SECTIONS = [
  { id: 'profile', label: 'Profile & LinkedIn', icon: User },
  { id: 'matches', label: 'Job Matches', icon: Target },
  { id: 'applications', label: 'Applications', icon: Send },
  { id: 'referrals', label: 'Referrals', icon: Users },
  { id: 'interview-prep', label: 'Interview Prep', icon: Calendar },
  { id: 'calendar', label: 'Calendar & Integrations', icon: Settings },
];

interface SidebarProps {
  activeSection: string;
  onSelect: (id: string) => void;
}

export function Sidebar({ activeSection, onSelect }: SidebarProps) {
  return (
    <nav className="sidebar">
      {SECTIONS.map((s) => {
        const Icon = s.icon;
        const isActive = activeSection === s.id;
        return (
          <button
            key={s.id}
            className={`nav-item${isActive ? ' active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <Icon size={18} />
            <span className="nav-label">{s.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
