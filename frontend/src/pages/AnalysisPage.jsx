import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Stack, Button, Select, MenuItem,
  FormControl, InputLabel, TextField, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Chip, Card, CardContent,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Tooltip,
  LinearProgress,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
  Analytics, DirectionsCar, People, Shield, Warning, FileDownload,
  Search, Refresh, OpenInNew, Close, LocalFireDepartment, Person,
  GpsFixed, Groups, Work, Pets, NoPhotography, Login, Videocam,
  SensorOccupied, TrendingUp, TrendingDown, TrendingFlat, Circle,
} from '@mui/icons-material';

const API = 'http://localhost:5050';

// ─── Feature registry ──────────────────────────────────────────────────────
const FM = {
  fire_smoke:          { label: 'Fire & Smoke',       color: '#ff3d00', glow: '#ff3d0060', icon: <LocalFireDepartment /> },
  intrusion:           { label: 'Intrusion',          color: '#ff6d00', glow: '#ff6d0060', icon: <Shield /> },
  no_go_zone:          { label: 'No-Go Zone',         color: '#ff1744', glow: '#ff174460', icon: <NoPhotography /> },
  loitering:           { label: 'Loitering',          color: '#ffd600', glow: '#ffd60060', icon: <Person /> },
  perimeter:           { label: 'Perimeter Breach',   color: '#ff4081', glow: '#ff408160', icon: <Login /> },
  crowd:               { label: 'Crowd Alert',        color: '#76ff03', glow: '#76ff0360', icon: <Groups /> },
  missing_person:      { label: 'Missing Person',     color: '#e040fb', glow: '#e040fb60', icon: <Person /> },
  personal_monitoring: { label: 'Personal Monitor',   color: '#00e5ff', glow: '#00e5ff60', icon: <GpsFixed /> },
  tampering:           { label: 'Tampering',          color: '#aa00ff', glow: '#aa00ff60', icon: <Videocam /> },
  weapon_detection:    { label: 'Weapon Detected',    color: '#ff1744', glow: '#ff174460', icon: <Warning /> },
  criminal_face:       { label: 'Watchlist Match',    color: '#ff6d00', glow: '#ff6d0060', icon: <SensorOccupied /> },
  animal_detection:    { label: 'Animal Alert',       color: '#22c822', glow: '#22c82260', icon: <Pets /> },
  vehicle_detection:   { label: 'Vehicle Detection',  color: '#00ffff', glow: '#00ffff60', icon: <DirectionsCar /> },
  abandoned_object:    { label: 'Left Luggage',       color: '#ff6be6', glow: '#ff6be660', icon: <Work /> },
  footfall:            { label: 'Footfall Count',     color: '#00b0ff', glow: '#00b0ff60', icon: <People /> },
  anpr:                { label: 'ANPR — Plates',      color: '#00ffcc', glow: '#00ffcc60', icon: <DirectionsCar /> },
};

// Sidebar nav groups
const NAV = [
  { key: 'overview',            label: 'Overview Hub',       icon: <Analytics />,            group: null },
  { key: 'anpr',                label: 'ANPR — Plates',      icon: <DirectionsCar />,         group: 'Analytics' },
  { key: 'vehicles',            label: 'Vehicle Counting',   icon: <DirectionsCar />,         group: 'Analytics' },
  { key: 'footfall',            label: 'Footfall Counting',  icon: <People />,                group: 'Analytics' },
  { key: 'loitering',           label: 'Loitering',          icon: <Person />,                group: 'Security' },
  { key: 'intrusion',           label: 'Intrusion',          icon: <Shield />,                group: 'Security' },
  { key: 'fire_smoke',          label: 'Fire & Smoke',       icon: <LocalFireDepartment />,   group: 'Security' },
  { key: 'no_go_zone',          label: 'No-Go Zone',         icon: <NoPhotography />,         group: 'Security' },
  { key: 'perimeter',           label: 'Perimeter Breach',   icon: <Login />,                 group: 'Security' },
  { key: 'crowd',               label: 'Crowd Alert',        icon: <Groups />,                group: 'Security' },
  { key: 'tampering',           label: 'Tampering',          icon: <Videocam />,              group: 'Security' },
  { key: 'weapon_detection',    label: 'Weapon Detected',    icon: <Warning />,               group: 'Security' },
  { key: 'criminal_face',       label: 'Watchlist Match',    icon: <SensorOccupied />,        group: 'Security' },
  { key: 'missing_person',      label: 'Missing Person',     icon: <Person />,                group: 'Security' },
  { key: 'personal_monitoring', label: 'Personal Monitor',   icon: <GpsFixed />,              group: 'Security' },
  { key: 'animal_detection',    label: 'Animal Alert',       icon: <Pets />,                  group: 'Security' },
  { key: 'abandoned_object',    label: 'Left Luggage',       icon: <Work />,                  group: 'Security' },
];

// CSV export
const exportCSV = (headers, rows, name) => {
  const csv = [headers, ...rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`))].map(r => r.join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = name; a.click();
};

// ─── Severity badge ─────────────────────────────────────────────────────────
const SEV_C = { CRITICAL: '#ff1744', HIGH: '#ff6d00', MEDIUM: '#ffd600', LOW: '#00b0ff' };
function SevBadge({ sev }) {
  const c = SEV_C[sev] || '#78909c';
  return (
    <Chip label={sev || '—'} size="small"
      sx={{ height: 17, fontSize: '0.58rem', fontWeight: 900, letterSpacing: 0.3,
        color: c, bgcolor: `${c}20`, border: `1px solid ${c}55`, borderRadius: '4px' }} />
  );
}

// ─── SVG Arc / Donut ────────────────────────────────────────────────────────
// ─── SVG Arc / Donut ────────────────────────────────────────────────────────
function DonutChart({ data }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const tTextPrimary = isDark ? '#f8fafc' : '#1e293b';
  const tTextSecondary = isDark ? '#94a3b8' : '#64748b';
  const tBorder = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.06)';
  const tCenterBg = isDark ? '#0d1117' : '#ffffff';
  const tLine = isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)';

  const [hov, setHov] = useState(null);
  const total = data.reduce((s, d) => s + d.value, 0);

  // Use mock data if there is no alerts data yet, to match screenshot behavior
  const isPlaceholder = total === 0;
  const chartData = isPlaceholder ? [
    { label: 'Critical Violation', value: 44, color: '#d81b60' },      // Pink/Red
    { label: 'High Severity Intrusion', value: 70, color: '#e65100' },  // Deep Orange
    { label: 'Volume', value: 36, color: '#f57c00' },                  // Orange
    { label: 'Scans', value: 30, color: '#ffb300' },                   // Amber
    { label: 'Footfall Warning', value: 20, color: '#fdd835' },        // Yellow
  ] : data;

  const displayTotal = isPlaceholder ? chartData.reduce((s, d) => s + d.value, 0) : total;

  const sortedChartData = [...chartData].sort((a, b) => b.value - a.value).filter(d => d.value > 0);

  const cx = 120, cy = 50, r = 30, circ = 2 * Math.PI * r;

  let cum = 0;

  return (
    <Box sx={{ width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <svg viewBox="0 0 240 100" width="100%" height="100%" style={{ overflow: 'visible' }}>
        {/* Outer background border circle */}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={tBorder} strokeWidth="8" />

        {/* Donut Segments */}
        {sortedChartData.map((d, i) => {
          const pct = d.value / displayTotal;
          const dashArr = pct * circ;
          const dashOff = circ * 0.25 - cum * circ;
          cum += pct;
          const isHov = hov === i;
          return (
            <circle key={i} cx={cx} cy={cy} r={r}
              fill="none"
              stroke={d.color}
              strokeWidth={isHov ? 9 : 6.5}
              strokeDasharray={`${dashArr} ${circ - dashArr}`}
              strokeDashoffset={dashOff}
              strokeLinecap="round"
              style={{ transition: 'stroke-width 0.2s, filter 0.2s', cursor: 'pointer',
                filter: isHov ? `drop-shadow(0 0 4px ${d.color})` : 'none' }}
              onMouseEnter={() => setHov(i)}
              onMouseLeave={() => setHov(null)}
            />
          );
        })}

        {/* Center hole blank circle */}
        <circle cx={cx} cy={cy} r={25} fill={tCenterBg} />

        {/* Pointer Lines and Labels */}
        {(() => {
          let lineCum = 0;
          return sortedChartData.map((d, i) => {
            const pct = d.value / displayTotal;
            const midPercent = lineCum + pct / 2;
            lineCum += pct;

            // Angle starting from 12 o'clock (-PI/2)
            const angle = midPercent * 2 * Math.PI - Math.PI / 2;

            // Midpoint on the circle radius
            const x1 = cx + r * Math.cos(angle);
            const y1 = cy + r * Math.sin(angle);

            // Projection point slightly outside the circle
            const x2 = cx + (r + 10) * Math.cos(angle);
            const y2 = cy + (r + 10) * Math.sin(angle);

            // Horizontal extension direction
            const isRight = x2 >= cx;
            const x3 = isRight ? x2 + 12 : x2 - 12;

            const isHov = hov === i;
            const titleColor = isHov ? d.color : tTextPrimary;

            // Text alignment and anchor
            const textAnchor = isRight ? 'start' : 'end';
            const textX = isRight ? x3 + 2 : x3 - 2;

            return (
              <g key={i} style={{ opacity: hov !== null && hov !== i ? 0.35 : 1, transition: 'opacity 0.2s' }}
                 onMouseEnter={() => setHov(i)} onMouseLeave={() => setHov(null)}>
                {/* Pointer Line */}
                <polyline
                  points={`${x1.toFixed(1)},${y1.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)} ${x3.toFixed(1)},${y2.toFixed(1)}`}
                  fill="none"
                  stroke={isHov ? d.color : tLine}
                  strokeWidth={isHov ? 1.2 : 0.8}
                  style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
                />
                
                {/* Label Line 1: Title */}
                <text
                  x={textX.toFixed(1)}
                  y={(y2 - 2).toFixed(1)}
                  textAnchor={textAnchor}
                  fill={titleColor}
                  fontSize="5.2"
                  fontWeight={isHov ? 'bold' : 'normal'}
                  style={{ transition: 'fill 0.2s, font-weight 0.2s', fontFamily: 'Inter, sans-serif' }}
                >
                  {d.label}
                </text>
                
                {/* Label Line 2: Percentage and Value */}
                <text
                  x={textX.toFixed(1)}
                  y={(y2 + 4.5).toFixed(1)}
                  textAnchor={textAnchor}
                  fill={tTextSecondary}
                  fontSize="4.5"
                  style={{ fontFamily: 'Inter, sans-serif' }}
                >
                  {Math.round(pct * 100)}% ({d.value})
                </text>
              </g>
            );
          });
        })()}
      </svg>
    </Box>
  );
}

// ─── SVG Line Sparkline ──────────────────────────────────────────────────────
function Sparkline({ data, color = '#00ffcc', height = 50 }) {
  if (data.length < 2) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  const W = 200, H = height;
  const pts = data.map((d, i) => ({
    x: (i / (data.length - 1)) * W,
    y: H - (d.value / max) * H * 0.85 - 2,
  }));
  const pathD = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={height} preserveAspectRatio="none">
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y} r="3" fill={color} />
    </svg>
  );
}

// ─── Big Line Chart with axes ────────────────────────────────────────────────
function LineChart({ data, color = '#00ffcc', label = '' }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const tTextSecondary = isDark ? '#64748b' : '#64748b';
  const tBorder = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
  const tPoint = isDark ? '#0a0c10' : '#ffffff';

  const max = Math.max(...data.map(d => d.value), 1);
  const W = 750, H = 90, padL = 28, padR = 8, padT = 8, padB = 22;
  const innerW = W - padL - padR, innerH = H;
  const pts = data.map((d, i) => ({
    x: padL + (i / Math.max(data.length - 1, 1)) * innerW,
    y: padT + innerH - (d.value / max) * innerH,
    ...d,
  }));
  const pathD = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const areaD = `${pathD} L${pts[pts.length-1].x},${padT + innerH} L${padL},${padT + innerH}Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H + padT + padB}`} width="100%" height="100%">
      <defs>
        <linearGradient id={`lg${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((r, i) => {
        const y = padT + r * innerH;
        return <g key={i}>
          <line x1={padL} y1={y} x2={W - padR} y2={y} stroke={tBorder} strokeWidth="1" strokeDasharray="4 4" />
          <text x={padL - 4} y={y + 3} textAnchor="end" fill={tTextSecondary} fontSize="7">{Math.round(max * (1 - r))}</text>
        </g>;
      })}
      <path d={areaD} fill={`url(#lg${color.replace('#','')})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={2.5} fill={tPoint} stroke={color} strokeWidth="1.5" />
          <text x={p.x} y={padT + innerH + padB - 2} textAnchor="middle" fill={tTextSecondary} fontSize="7">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ─── Bar Chart ───────────────────────────────────────────────────────────────
function BarChart({ data }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const tTextPrimary = isDark ? '#e2e8f0' : '#1e293b';
  const tTextSecondary = isDark ? '#64748b' : '#64748b';

  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  const W = 360, H = 90, pad = 8;
  const bw = Math.max(6, Math.floor((W - pad * 2) / data.length) - 4);
  const gap = Math.floor((W - pad * 2) / data.length);
  return (
    <svg viewBox={`0 0 ${W} ${H + 24}`} width="100%" height="100%">
      {data.map((d, i) => {
        const bh = Math.max(2, (d.value / max) * H);
        const x = pad + i * gap + (gap - bw) / 2;
        const y = H - bh;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={bh} fill={d.color} rx="3" opacity="0.85"
              style={{ cursor: 'pointer' }} />
            <rect x={x} y={y} width={bw} height={Math.min(3, bh)} fill={d.color} rx="3"
              style={{ filter: `drop-shadow(0 0 4px ${d.color})` }} />
            {d.value > 0 && <text x={x + bw/2} y={y - 3} textAnchor="middle" fill={tTextPrimary} fontSize="5.5" fontWeight="bold">{d.value}</text>}
            <text x={x + bw/2} y={H + 16} textAnchor="middle" fill={tTextSecondary} fontSize="4.5">{d.label.slice(0,7)}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── KPI Card ────────────────────────────────────────────────────────────────
function KPICard({ label, value, color, sub, icon }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const tBgCard = isDark ? '#0d1117' : '#ffffff';
  const tBorderColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)';

  return (
    <Box sx={{
      bgcolor: tBgCard,
      border: `1px solid ${tBorderColor}`,
      borderRadius: '8px',
      p: '14px 14px 10px',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      boxShadow: isDark ? 'none' : '0 2px 4px rgba(0,0,0,0.01)',
      position: 'relative',
      overflow: 'hidden',
      '&:hover': {
        boxShadow: '0 4px 12px rgba(0,0,0,0.04)',
        border: `1px solid ${color}40`,
        transform: 'translateY(-1px)',
        transition: 'all 0.2s',
      },
    }}>
      <Typography sx={{ fontSize: '0.62rem', fontWeight: 800, color: 'text.secondary', letterSpacing: 0.8, textTransform: 'uppercase', mb: 0.5 }}>
        {label}
      </Typography>
      
      <Typography sx={{ fontSize: '2.5rem', fontWeight: 900, color, lineHeight: 1.1, fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </Typography>

      {/* Colored horizontal line bar under the number */}
      <Box sx={{ height: 3, bgcolor: color, borderRadius: '2px', width: '25px', mt: 0.6, mb: 1.0 }} />

      <Stack direction="row" alignItems="center" gap={0.5} mt="auto">
        {icon && React.cloneElement(icon, { sx: { fontSize: 13, color: 'text.secondary' } })}
        <Typography sx={{ fontSize: '0.62rem', fontWeight: 600, color: 'text.secondary' }} noWrap>
          {sub}
        </Typography>
      </Stack>
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
export default function AnalysisPage() {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  // Theme variables
  const tBgMain = isDark ? 'linear-gradient(180deg, #080a0f 0%, #0a0c12 100%)' : 'linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%)';
  const tBgSidebar = isDark ? 'linear-gradient(180deg, #0d1117 0%, #080b10 100%)' : 'linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%)';
  const tBgCard = isDark ? 'linear-gradient(135deg, rgba(255,255,255,0.025) 0%, rgba(255,255,255,0.01) 100%)' : 'linear-gradient(135deg, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0.5) 100%)';
  const tBgFilter = isDark ? 'rgba(13,17,23,0.95)' : 'rgba(255,255,255,0.85)';
  const tBgTableHead = isDark ? '#080a0f' : '#f8fafc';
  
  const tBorder = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)';
  const tBorderStrong = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.12)';
  const tScrollThumb = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.15)';
  
  const tTextPrimary = isDark ? '#e2e8f0' : '#0f172a';
  const tTextSecondary = isDark ? '#94a3b8' : '#475569';
  const tTextMuted = isDark ? '#374151' : '#94a3b8';
  const tTextHeader = isDark ? '#1e3a5f' : '#64748b';

  const [section, setSection] = useState('overview');
  const [alerts, setAlerts] = useState([]);
  const [vehicles, setVehicles] = useState({});
  const [footfall, setFootfall] = useState({});
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(false);
  const [online, setOnline] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);

  // Filters
  const [cam, setCam] = useState('all');
  const [range, setRange] = useState('7days');
  const [d0, setD0] = useState('');
  const [d1, setD1] = useState('');
  const [search, setSearch] = useState('');
  const [zoom, setZoom] = useState(null);

  const fetchAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/api/alerts?limit=500`).then(r => r.json()).catch(() => []),
      fetch(`${API}/api/analytics/vehicles`).then(r => r.json()).catch(() => ({})),
      fetch(`${API}/api/analytics/footfall`).then(r => r.json()).catch(() => ({})),
      fetch(`${API}/api/cameras`).then(r => r.json()).catch(() => []),
    ]).then(([a, v, f, c]) => {
      setAlerts(Array.isArray(a) ? a : []);
      setVehicles(v || {});
      setFootfall(f || {});
      setCameras(Array.isArray(c) ? c : []);
      setOnline(true);
      setLastRefresh(new Date());
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Filter
  const filtered = alerts.filter(a => {
    if (cam !== 'all' && a.cam_id !== cam) return false;
    const t = new Date(a.timestamp), now = new Date();
    if (range === 'today' && t < new Date(now.getFullYear(), now.getMonth(), now.getDate())) return false;
    if (range === '7days' && t < new Date(now - 7 * 86400000)) return false;
    if (range === 'custom') {
      if (d0 && t < new Date(d0)) return false;
      if (d1) { const e = new Date(d1); e.setHours(23,59,59,999); if (t > e) return false; }
    }
    return true;
  });

  const camIds = [...new Set(alerts.map(a => a.cam_id))].filter(Boolean);
  const breakdown = filtered.reduce((acc, a) => { acc[a.feature] = (acc[a.feature] || 0) + 1; return acc; }, {});
  const pieData = Object.entries(breakdown).map(([k, v]) => ({ label: FM[k]?.label || k, value: v, color: FM[k]?.color || '#64748b' }));
  const barData = pieData.sort((a, b) => b.value - a.value).slice(0, 10);

  // 7-day trend
  const now = new Date();
  const trend7 = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now); d.setDate(d.getDate() - (6 - i));
    const lbl = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    return { label: lbl, value: filtered.filter(a => new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' }) === lbl).length };
  });

  // 24-h hourly trend
  const hourly = Array.from({ length: 24 }, (_, h) => ({
    label: `${h}h`,
    value: filtered.filter(a => new Date(a.timestamp).getHours() === h).length,
  }));

  // Sparklines for KPIs
  const mkSpark = (feat) => trend7.map(d => ({
    ...d,
    value: filtered.filter(a => {
      const lbl = new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' });
      return lbl === d.label && (feat ? a.feature === feat : true);
    }).length,
  }));

  // KPI data
  const critical = filtered.filter(a => a.severity === 'CRITICAL').length;
  const high = filtered.filter(a => a.severity === 'HIGH').length;
  const anprCnt = filtered.filter(a => a.feature === 'anpr').length;
  const ffTotal = Object.values(footfall).reduce((s, c) => s + (c.count_in || 0) + (c.count_out || 0), 0);
  const vTotal = Object.values(vehicles).reduce((s, c) => s + (c.total?.in || 0) + (c.total?.out || 0), 0);

  // ANPR
  const anprRows = filtered.filter(a => a.feature === 'anpr').map(a => ({
    ts: a.timestamp, cam: a.cam_id,
    plate: a.plate_text || a.detections?.[0]?.plate_text || '—',
    conf: a.confidence || 0, snap: a.snapshot_path,
  })).filter(r => !search || r.plate.toLowerCase().includes(search.toLowerCase()));

  // Vehicle rows
  const vRows = Object.entries(vehicles).flatMap(([cid, c]) => {
    if (cam !== 'all' && cid !== cam) return [];
    return Object.entries(c.by_type || {}).map(([t, cnt]) => ({ cid, type: t, in: cnt.in||0, out: cnt.out||0, reset: c.last_reset_date||'—' }));
  });

  // Footfall rows
  const ffRows = Object.entries(footfall).flatMap(([cid, c]) => {
    if (cam !== 'all' && cid !== cam) return [];
    return [{ cid, in: c.count_in||0, out: c.count_out||0, occ: c.occupancy||0, reset: c.last_reset_date||'—' }];
  });

  const ACC = '#00ffcc';

  // Sidebar groups
  const sideGroups = {};
  NAV.forEach(n => { const g = n.group||''; if (!sideGroups[g]) sideGroups[g]=[]; sideGroups[g].push(n); });

  // Feature table for security sections
  const featRows = section && FM[section] ? filtered.filter(a => a.feature === section) : [];

  return (
    <Box sx={{
      display: 'flex', width: '100%', height: '100%', overflow: 'hidden',
      background: tBgMain,
    }}>
      {/* ═══ SIDEBAR ══════════════════════════════════════════════════════════ */}
      <Box sx={{
        width: 230, flexShrink: 0,
        background: tBgSidebar,
        borderRight: `1px solid ${tBorder}`,
        display: 'flex', flexDirection: 'column', overflowY: 'auto', overflowX: 'hidden',
        '&::-webkit-scrollbar': { width: 3 },
        '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 },
      }}>
        {Object.entries(sideGroups).map(([grp, items]) => (
          <Box key={grp}>
            {grp && (
              <Typography sx={{ px: 2, pt: 1.8, pb: 0.6, fontSize: '0.68rem', fontWeight: 900,
                letterSpacing: 1.5, color: tTextHeader, textTransform: 'uppercase' }}>
                ── {grp}
              </Typography>
            )}
            {items.map(item => {
              const active = section === item.key;
              const c = FM[item.key]?.color || ACC;
              const cnt = item.key === 'vehicles' ? vRows.reduce((s,r)=>s+r.in+r.out,0)
                       : item.key === 'footfall' ? ffTotal
                       : item.key === 'anpr' ? anprCnt
                       : item.key === 'overview' ? null
                       : (breakdown[item.key] || 0);
              return (
                <Box key={item.key}
                  onClick={() => { setSection(item.key); setSearch(''); }}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: 1.2, px: 2, py: 1.0,
                    cursor: 'pointer', position: 'relative', userSelect: 'none',
                    borderLeft: `3px solid ${active ? c : 'transparent'}`,
                    bgcolor: active ? `${c}12` : 'transparent',
                    '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' },
                    transition: 'all 0.15s',
                  }}>
                  {active && <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, bgcolor: c, boxShadow: `0 0 10px ${c}` }} />}
                  <Box sx={{ color: active ? c : tTextHeader, fontSize: 17, display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                    {React.cloneElement(item.icon, { sx: { fontSize: 17 } })}
                  </Box>
                  <Typography sx={{ fontSize: '0.86rem', fontWeight: active ? 700 : 500, color: active ? tTextPrimary : tTextSecondary, flex: 1 }} noWrap>
                    {item.label}
                  </Typography>
                  {cnt != null && cnt > 0 && (
                    <Box sx={{ bgcolor: active ? `${c}25` : (isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.06)'), color: active ? (isDark ? c : tTextPrimary) : tTextSecondary,
                      fontSize: '0.7rem', fontWeight: 800, px: 0.75, py: 0.15, borderRadius: 1, minWidth: 20, textAlign: 'center' }}>
                      {cnt}
                    </Box>
                  )}
                </Box>
              );
            })}
          </Box>
        ))}
        {/* Bottom status */}
        <Box sx={{ mt: 'auto', borderTop: `1px solid ${tBorder}`, p: 2 }}>
          <Stack direction="row" alignItems="center" gap={1}>
            <Circle sx={{ fontSize: 8, color: online ? '#00e676' : '#ff1744', filter: online ? '0 0 4px #00e676' : 'none' }} />
            <Typography sx={{ fontSize: '0.72rem', fontWeight: 600, color: online ? '#00e676' : '#ff1744' }}>{online ? 'Backend Live' : 'Offline Mode'}</Typography>
          </Stack>
          {lastRefresh && <Typography sx={{ fontSize: '0.65rem', color: tTextHeader, mt: 0.4 }}>{lastRefresh.toLocaleTimeString()}</Typography>}
        </Box>
      </Box>

      {/* ═══ MAIN ══════════════════════════════════════════════════════════════ */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>

        {/* ── Filter bar ──────────────────────────────────────────────────── */}
        <Box sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          px: 2,
          py: '18px',
          background: tBgFilter,
          borderBottom: `1px solid ${tBorder}`,
          backdropFilter: 'blur(16px)',
          flexShrink: 0,
          flexWrap: 'wrap',
          zIndex: 5,
        }}>
          {(() => {
            const cameraOptions = cameras.length > 0
              ? cameras.map(c => c.id)
              : [...new Set(['cam_01', 'cam_02', 'cam_03', 'cam_04', 'cam_05', ...camIds])].sort();

            const getCameraName = (cid) => {
              const found = cameras.find(c => c.id === cid);
              return found ? `${found.name} (${cid})` : cid.replace('cam_', 'Camera ');
            };

            return (
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <InputLabel sx={{ fontSize: '0.78rem', color: tTextSecondary }}>Camera</InputLabel>
                <Select
                  value={cam}
                  label="Camera"
                  onChange={e => setCam(e.target.value)}
                  sx={{
                    fontSize: '0.8rem',
                    color: tTextPrimary,
                    '& .MuiSelect-select': { py: '8px' },
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: tBorderStrong },
                    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#00ffcc44' }
                  }}
                >
                  <MenuItem value="all" sx={{ fontSize: '0.8rem' }}>All Cameras</MenuItem>
                  {cameraOptions.map(c => (
                    <MenuItem key={c} value={c} sx={{ fontSize: '0.8rem' }}>
                      {getCameraName(c)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            );
          })()}

          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel sx={{ fontSize: '0.78rem', color: tTextSecondary }}>Range</InputLabel>
            <Select value={range} label="Range" onChange={e => setRange(e.target.value)}
              sx={{ fontSize: '0.8rem', color: tTextPrimary, '& .MuiSelect-select': { py: '8px' },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: tBorderStrong },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#00ffcc44' } }}>
              <MenuItem value="today" sx={{ fontSize: '0.8rem' }}>Today</MenuItem>
              <MenuItem value="7days" sx={{ fontSize: '0.8rem' }}>Last 7 Days</MenuItem>
              <MenuItem value="custom" sx={{ fontSize: '0.8rem' }}>Custom</MenuItem>
            </Select>
          </FormControl>

          {range === 'custom' && <>
            <TextField
              size="small"
              type="date"
              label="From"
              value={d0}
              onChange={e => setD0(e.target.value)}
              InputLabelProps={{
                shrink: true,
                sx: {
                  fontSize: '0.75rem',
                  bgcolor: isDark ? '#0d1117' : '#ffffff',
                  px: 0.5,
                  borderRadius: '3px',
                  color: `${tTextSecondary} !important`,
                }
              }}
              sx={{
                width: 140,
                '& .MuiInputBase-input': { py: '8px', fontSize: '0.75rem', color: tTextPrimary },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: tBorderStrong },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#00ffcc44' }
              }}
            />
            <TextField
              size="small"
              type="date"
              label="To"
              value={d1}
              onChange={e => setD1(e.target.value)}
              InputLabelProps={{
                shrink: true,
                sx: {
                  fontSize: '0.75rem',
                  bgcolor: isDark ? '#0d1117' : '#ffffff',
                  px: 0.5,
                  borderRadius: '3px',
                  color: `${tTextSecondary} !important`,
                }
              }}
              sx={{
                width: 140,
                '& .MuiInputBase-input': { py: '8px', fontSize: '0.75rem', color: tTextPrimary },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: tBorderStrong },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#00ffcc44' }
              }}
            />
          </>}

          <Button size="small" startIcon={<Refresh sx={{ fontSize: '14px !important' }} />} onClick={fetchAll} disabled={loading}
            sx={{
              fontSize: '0.75rem', px: 2, py: '6px', fontWeight: 600, borderRadius: '6px',
              bgcolor: isDark ? 'rgba(0,255,204,0.1)' : '#e0f2f1',
              color: isDark ? ACC : '#00796b',
              border: `1px solid ${isDark ? 'rgba(0,255,204,0.2)' : '#b2dfdb'}`,
              textTransform: 'none',
              '&:hover': {
                bgcolor: isDark ? 'rgba(0,255,204,0.15)' : '#b2dfdb',
              },
            }}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>

          <Box sx={{ ml: 'auto', display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography sx={{ fontSize: '0.72rem', color: 'text.secondary', fontWeight: 500 }}>
              {filtered.length} events - {(cameras.length > 0 ? cameras.length : camIds.length)} cameras
            </Typography>
            {!online && (
              <Chip label="Backend offline" size="small"
                sx={{ fontSize: '0.6rem', height: 20, bgcolor: '#ff6d0015', color: '#ff9100', border: '1px solid #ff9100' }} />
            )}
          </Box>
        </Box>
        {loading && <LinearProgress sx={{ height: 1.5, bgcolor: 'transparent', '& .MuiLinearProgress-bar': { bgcolor: ACC } }} />}

        {/* ── Content ─────────────────────────────────────────────────────── */}
        <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

          {/* ─── OVERVIEW ─────────────────────────────────────────────────── */}
          {section === 'overview' && (
            <Box sx={{ flex: 1, overflowY: 'auto', p: 1.5, gap: 1.5, display: 'flex', flexDirection: 'column',
              '&::-webkit-scrollbar': { width: 4 }, '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 } }}>

              {/* KPI Row */}
              <Grid container spacing={1.2}>
                {[
                  { label: 'Critical Alerts', value: critical, color: '#d81b60', sub: 'Fires, weapons', icon: <LocalFireDepartment /> },
                  { label: 'High Severity',   value: high,     color: '#ff6d00', sub: 'Intrusions & threats',     icon: <Shield /> },
                  { label: 'ANPR Scans',      value: anprCnt,  color: '#00bcd4', sub: 'Plates recognized',        icon: <DirectionsCar /> },
                  { label: 'Footfall Total',  value: ffTotal,  color: '#03a9f4', sub: 'Crossings logged',         icon: <People /> },
                  { label: 'Vehicle Volume',  value: vTotal,   color: '#b78429', sub: 'Monitored crossings',      icon: <DirectionsCar /> },
                  { label: 'Total Events',    value: filtered.length, color: '#8bc34a', sub: 'All alerts combined', icon: <Analytics /> },
                ].map((k, i) => (
                  <Grid key={i} item xs={6} sm={4} md={2}>
                    <KPICard {...k} />
                  </Grid>
                ))}
              </Grid>

              {/* Charts row */}
              <Grid container spacing={1.2}>
                {/* Line trend */}
                <Grid item xs={12} md={8}>
                  <Box sx={{
                    background: tBgCard, boxShadow: isDark ? 'none' : '0 2px 8px rgba(0,0,0,0.03)',
                    border: `1px solid ${tBorder}`, borderRadius: '12px', p: 1.5, height: 250,
                    display: 'flex', flexDirection: 'column',
                  }}>
                    <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase', mb: 1 }}>7-Day Alert Trend</Typography>
                    <Box sx={{ flex: 1, minHeight: 0 }}><LineChart data={trend7} color={isDark ? ACC : '#00b0ff'} /></Box>
                  </Box>
                </Grid>

                {/* Donut */}
                <Grid item xs={12} md={4}>
                  <Box sx={{
                    background: tBgCard, boxShadow: isDark ? 'none' : '0 2px 8px rgba(0,0,0,0.03)',
                    border: `1px solid ${tBorder}`, borderRadius: '12px', p: 1.5, height: 250,
                    display: 'flex', flexDirection: 'column',
                  }}>
                    <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase', mb: 1 }}>Alert Breakdown</Typography>
                    <Box sx={{ flex: 1, minHeight: 0 }}><DonutChart data={pieData} /></Box>
                  </Box>
                </Grid>
              </Grid>

              {/* Recent alerts table */}
              <Box sx={{ background: tBgCard, boxShadow: isDark ? 'none' : '0 2px 8px rgba(0,0,0,0.03)',
                border: `1px solid ${tBorder}`, borderRadius: '12px', overflow: 'hidden', mt: 2 }}>
                <Box sx={{ px: 1.5, py: 1, borderBottom: `1px solid ${tBorder}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase' }}>Recent Events</Typography>
                  <Chip label={`${filtered.length} total`} size="small"
                    sx={{ height: 17, fontSize: '0.58rem', bgcolor: `${ACC}15`, color: isDark ? ACC : '#008b74', border: `1px solid ${ACC}30`, fontWeight: 800 }} />
                </Box>
                <TableContainer sx={{ height: 85, '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 } }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        {['Time', 'Camera', 'Festure', 'Sev', 'Message', 'Snap'].map(h => (
                          <TableCell key={h} sx={{ fontWeight: 700, fontSize: '0.62rem', py: 0.6,
                            bgcolor: tBgTableHead, color: tTextHeader, borderBottom: `1px solid ${tBorderStrong}` }}>{h}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filtered.slice(0, 40).map((a, i) => {
                        const m = FM[a.feature] || { label: a.feature, color: '#64748b' };
                        return (
                          <TableRow key={i} sx={{ '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }, '& td': { borderBottom: `1px solid ${tBorder}` } }}>
                            <TableCell sx={{ fontSize: '0.65rem', py: 0.5, color: tTextSecondary, whiteSpace: 'nowrap' }}>{new Date(a.timestamp).toLocaleString()}</TableCell>
                            <TableCell sx={{ fontSize: '0.65rem', py: 0.5, color: tTextSecondary, fontWeight: 600 }}>{a.cam_id}</TableCell>
                            <TableCell sx={{ py: 0.5 }}>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: m.color, flexShrink: 0 }} />
                                <Typography sx={{ fontSize: '0.65rem', color: isDark ? m.color : '#0f172a', fontWeight: 600 }}>{m.label}</Typography>
                              </Box>
                            </TableCell>
                            <TableCell sx={{ py: 0.5 }}><SevBadge sev={a.severity} /></TableCell>
                            <TableCell sx={{ fontSize: '0.65rem', py: 0.5, color: tTextSecondary, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.message || '—'}</TableCell>
                            <TableCell sx={{ py: 0.5 }} align="center">
                              {a.snapshot_path ? (
                                <IconButton size="small" onClick={() => setZoom(`${API}/clips/${a.snapshot_path}`)}
                                  sx={{ color: isDark ? ACC : '#00b0ff', p: 0.2, '&:hover': { bgcolor: `${ACC}15` } }}>
                                  <OpenInNew sx={{ fontSize: 12 }} />
                                </IconButton>
                              ) : <Typography color="text.disabled" fontSize="0.6rem">—</Typography>}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            </Box>
          )}

          {/* ─── ANPR ─────────────────────────────────────────────────────── */}
          {section === 'anpr' && (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <Box sx={{ px: 1.5, py: 0.75, display: 'flex', alignItems: 'center', gap: 1, borderBottom: `1px solid ${tBorder}`, flexShrink: 0, bgcolor: tBgCard }}>
                <TextField size="small" placeholder="Search plate…" value={search} onChange={e => setSearch(e.target.value)}
                  InputProps={{ startAdornment: <Search sx={{ fontSize: 14, color: tTextSecondary, mr: 0.5 }} /> }}
                  sx={{ width: 180, '& .MuiInputBase-input': { py: '5px', fontSize: '0.75rem', color: tTextPrimary },
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: tBorderStrong } }} />
                <Chip label={`${anprRows.length} plates`} size="small" sx={{ height: 18, fontSize: '0.62rem', bgcolor: `${ACC}15`, color: isDark ? ACC : '#008b74', fontWeight: 800 }} />
                <Button size="small" startIcon={<FileDownload sx={{ fontSize: 13 }} />}
                  onClick={() => exportCSV(['Time','Camera','Plate','Conf'], anprRows.map(r => [new Date(r.ts).toLocaleString(), r.cam, r.plate, `${(r.conf*100).toFixed(0)}%`]), `anpr_${new Date().toISOString().slice(0,10)}.csv`)}
                  sx={{ ml: 'auto', fontSize: '0.7rem', px: 1.2, py: '3px', border: `1px solid ${ACC}30`, color: isDark ? ACC : '#00b0ff', borderRadius: '6px', '&:hover': { bgcolor: `${ACC}10` } }}>
                  Export CSV
                </Button>
              </Box>

              {/* ANPR Stats Box */}
              <Box sx={{ p: 1.5, borderBottom: `1px solid ${tBorder}`, bgcolor: tBgCard, flexShrink: 0 }}>
                <Box sx={{ display: 'inline-block', bgcolor: `${ACC}15`, border: `1px solid ${ACC}30`, borderRadius: '8px', px: 2.5, py: 1.2 }}>
                  <Typography sx={{ fontSize: '0.58rem', color: tTextSecondary, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>Plates Scanned</Typography>
                  <Typography sx={{ fontSize: '1.5rem', fontWeight: 900, color: isDark ? ACC : '#0f172a', lineHeight: 1 }}>{anprRows.length}</Typography>
                </Box>
              </Box>

              {/* ANPR Trend Section */}
              {(() => {
                const featTrend = Array.from({ length: 7 }, (_, i) => {
                  const d = new Date(now); d.setDate(d.getDate() - (6 - i));
                  const lbl = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
                  return {
                    label: lbl,
                    value: filtered.filter(a => a.feature === 'anpr' && new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' }) === lbl).length
                  };
                });
                return (
                  <Box sx={{ p: 1.5, borderBottom: `1px solid ${tBorder}`, bgcolor: tBgCard, flexShrink: 0 }}>
                    <Typography sx={{ fontSize: '0.65rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase', mb: 1 }}>Scan Trend</Typography>
                    <Box sx={{ height: 100, pr: 2 }}>
                      <LineChart data={featTrend} color={ACC} />
                    </Box>
                  </Box>
                );
              })()}

              <TableContainer sx={{ flex: 1, overflowY: 'auto', '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 } }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {['Time', 'Camera', 'License Plate', 'Confidence', 'Snap'].map(h => (
                        <TableCell key={h} sx={{ fontWeight: 700, fontSize: '0.65rem', py: 0.7, bgcolor: tBgTableHead, color: tTextHeader, borderBottom: `1px solid ${tBorderStrong}` }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {anprRows.length === 0 ? (
                      <TableRow><TableCell colSpan={5} align="center" sx={{ py: 8, color: tTextHeader, fontSize: '0.85rem' }}>No ANPR plates detected yet. Enable Plate Recognition in Settings.</TableCell></TableRow>
                    ) : anprRows.map((r, i) => (
                      <TableRow key={i} sx={{ '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }, '& td': { borderBottom: `1px solid ${tBorder}` } }}>
                        <TableCell sx={{ fontSize: '0.68rem', py: 0.6, color: tTextSecondary, whiteSpace: 'nowrap' }}>{new Date(r.ts).toLocaleString()}</TableCell>
                        <TableCell sx={{ fontSize: '0.68rem', py: 0.6, color: tTextSecondary, fontWeight: 600 }}>{r.cam}</TableCell>
                        <TableCell sx={{ py: 0.6 }}>
                          <Typography sx={{ fontFamily: 'monospace', fontWeight: 900, fontSize: '0.9rem', color: isDark ? ACC : '#008b74',
                            letterSpacing: 2, textShadow: isDark ? `0 0 12px ${ACC}60` : 'none' }}>{r.plate}</Typography>
                        </TableCell>
                        <TableCell sx={{ py: 0.6 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
                            <LinearProgress variant="determinate" value={r.conf * 100}
                              sx={{ width: 40, height: 4, borderRadius: 2, bgcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.1)',
                                '& .MuiLinearProgress-bar': { bgcolor: r.conf > 0.8 ? '#00e676' : r.conf > 0.5 ? '#ffd600' : '#ff1744' } }} />
                            <Typography sx={{ fontSize: '0.68rem', color: tTextSecondary }}>{(r.conf * 100).toFixed(0)}%</Typography>
                          </Box>
                        </TableCell>
                        <TableCell sx={{ py: 0.6 }} align="center">
                          {r.snap ? (
                            <IconButton size="small" onClick={() => setZoom(`${API}/clips/${r.snap}`)} sx={{ color: isDark ? ACC : '#00b0ff', p: 0.2 }}>
                              <OpenInNew sx={{ fontSize: 13 }} />
                            </IconButton>
                          ) : <Typography color="text.disabled" fontSize="0.65rem">—</Typography>}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {/* ─── VEHICLES ─────────────────────────────────────────────────── */}
          {section === 'vehicles' && (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <Box sx={{ px: 1.5, py: 0.75, display: 'flex', alignItems: 'center', gap: 1.5, borderBottom: `1px solid ${tBorder}`, flexShrink: 0, bgcolor: tBgCard }}>
                <Typography sx={{ fontWeight: 700, fontSize: '0.8rem', color: tTextSecondary }}>Vehicle Traffic Distribution</Typography>
                <Button size="small" startIcon={<FileDownload sx={{ fontSize: 13 }} />}
                  onClick={() => exportCSV(['Camera','Type','IN','OUT','Reset'], vRows.map(r=>[r.cid,r.type,r.in,r.out,r.reset]), `vehicles_${new Date().toISOString().slice(0,10)}.csv`)}
                  sx={{ ml: 'auto', fontSize: '0.7rem', px: 1.2, py: '3px', border: '1px solid #00ffff30', color: isDark ? '#00ffff' : '#008b8b', borderRadius: '6px' }}>
                  Export CSV
                </Button>
              </Box>
              <Box sx={{ p: 1.5, display: 'flex', gap: 1.2, flexWrap: 'wrap', borderBottom: `1px solid ${tBorder}`, flexShrink: 0 }}>
                {[
                  { label: 'Total IN', value: vRows.reduce((s,r)=>s+r.in,0), color: '#00e676' },
                  { label: 'Total OUT', value: vRows.reduce((s,r)=>s+r.out,0), color: '#ff6d00' },
                  { label: 'Vehicle Types', value: vRows.length, color: '#00ffff' },
                  { label: 'Cameras', value: [...new Set(vRows.map(r=>r.cid))].length, color: '#aa00ff' },
                ].map((s,i)=>(
                  <Box key={i} sx={{ bgcolor: `${s.color}15`, border: `1px solid ${s.color}30`, borderRadius: '8px', px: 2, py: 1,
                    boxShadow: isDark ? 'none' : '0 2px 4px rgba(0,0,0,0.05)' }}>
                    <Typography sx={{ fontSize: '0.58rem', color: tTextSecondary, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</Typography>
                    <Typography sx={{ fontSize: '1.5rem', fontWeight: 900, color: isDark ? s.color : '#0f172a', lineHeight: 1 }}>{s.value}</Typography>
                  </Box>
                ))}
              </Box>
              {/* Vehicle Trend Section */}
              {(() => {
                const featTrend = Array.from({ length: 7 }, (_, i) => {
                  const d = new Date(now); d.setDate(d.getDate() - (6 - i));
                  const lbl = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
                  return {
                    label: lbl,
                    value: filtered.filter(a => a.feature === 'vehicle_detection' && new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' }) === lbl).length
                  };
                });
                return (
                  <Box sx={{ p: 1.5, borderBottom: `1px solid ${tBorder}`, bgcolor: tBgCard, flexShrink: 0 }}>
                    <Typography sx={{ fontSize: '0.65rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase', mb: 1 }}>Vehicle Count Trend</Typography>
                    <Box sx={{ height: 100, pr: 2 }}>
                      <LineChart data={featTrend} color="#00ffff" />
                    </Box>
                  </Box>
                );
              })()}
              <TableContainer sx={{ flex: 1, overflowY: 'auto', '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 } }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {['Camera', 'Vehicle Type', '↑ IN', '↓ OUT', 'Last Reset'].map(h => (
                        <TableCell key={h} sx={{ fontWeight: 700, fontSize: '0.65rem', py: 0.7, bgcolor: tBgTableHead, color: tTextHeader, borderBottom: `1px solid ${tBorderStrong}` }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vRows.length === 0 ? (
                      <TableRow><TableCell colSpan={5} align="center" sx={{ py: 8, color: tTextHeader }}>No vehicle data. Enable Vehicle Detection in Settings.</TableCell></TableRow>
                    ) : vRows.map((r, i) => (
                      <TableRow key={i} sx={{ '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }, '& td': { borderBottom: `1px solid ${tBorder}` } }}>
                        <TableCell sx={{ fontSize: '0.7rem', py: 0.6, color: tTextSecondary, fontWeight: 600 }}>{r.cid}</TableCell>
                        <TableCell sx={{ fontSize: '0.7rem', py: 0.6, textTransform: 'capitalize', fontWeight: 700, color: tTextPrimary }}>{r.type}</TableCell>
                        <TableCell sx={{ py: 0.6 }}><Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: '#00e676' }}>{r.in}</Typography></TableCell>
                        <TableCell sx={{ py: 0.6 }}><Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: '#ff6d00' }}>{r.out}</Typography></TableCell>
                        <TableCell sx={{ fontSize: '0.68rem', py: 0.6, color: tTextSecondary }}>{r.reset}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {/* ─── FOOTFALL ─────────────────────────────────────────────────── */}
          {section === 'footfall' && (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <Box sx={{ px: 1.5, py: 0.75, display: 'flex', alignItems: 'center', gap: 1.5, borderBottom: `1px solid ${tBorder}`, flexShrink: 0, bgcolor: tBgCard }}>
                <Typography sx={{ fontWeight: 700, fontSize: '0.8rem', color: tTextSecondary }}>Footfall Crossings & Occupancy</Typography>
                <Button size="small" startIcon={<FileDownload sx={{ fontSize: 13 }} />}
                  onClick={() => exportCSV(['Camera','IN','OUT','Occupancy','Reset'], ffRows.map(r=>[r.cid,r.in,r.out,r.occ,r.reset]), `footfall_${new Date().toISOString().slice(0,10)}.csv`)}
                  sx={{ ml: 'auto', fontSize: '0.7rem', px: 1.2, py: '3px', border: '1px solid #00b0ff30', color: isDark ? '#00b0ff' : '#0077b6', borderRadius: '6px' }}>
                  Export CSV
                </Button>
              </Box>
              {/* Summary cards */}
              <Box sx={{ p: 1.5, display: 'flex', gap: 1.2, flexWrap: 'wrap', borderBottom: `1px solid ${tBorder}`, flexShrink: 0 }}>
                {[
                  { label: 'Total Entries', value: ffRows.reduce((s,r)=>s+r.in,0), color: '#00e676' },
                  { label: 'Total Exits', value: ffRows.reduce((s,r)=>s+r.out,0), color: '#ff6d00' },
                  { label: 'Occupancy', value: ffRows.reduce((s,r)=>s+r.occ,0), color: '#00b0ff' },
                  { label: 'Active Zones', value: ffRows.length, color: '#aa00ff' },
                ].map((s,i)=>(
                  <Box key={i} sx={{ bgcolor: `${s.color}15`, border: `1px solid ${s.color}30`, borderRadius: '8px', px: 2, py: 1,
                    boxShadow: isDark ? 'none' : '0 2px 4px rgba(0,0,0,0.05)' }}>
                    <Typography sx={{ fontSize: '0.58rem', color: tTextSecondary, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</Typography>
                    <Typography sx={{ fontSize: '1.5rem', fontWeight: 900, color: isDark ? s.color : '#0f172a', lineHeight: 1 }}>{s.value}</Typography>
                  </Box>
                ))}
              </Box>
              {/* Footfall Trend Section */}
              {(() => {
                const featTrend = Array.from({ length: 7 }, (_, i) => {
                  const d = new Date(now); d.setDate(d.getDate() - (6 - i));
                  const lbl = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
                  return {
                    label: lbl,
                    value: filtered.filter(a => a.feature === 'footfall' && new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' }) === lbl).length
                  };
                });
                return (
                  <Box sx={{ p: 1.5, borderBottom: `1px solid ${tBorder}`, bgcolor: tBgCard, flexShrink: 0 }}>
                    <Typography sx={{ fontSize: '0.65rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase', mb: 1 }}>Footfall Trend</Typography>
                    <Box sx={{ height: 100, pr: 2 }}>
                      <LineChart data={featTrend} color="#00b0ff" />
                    </Box>
                  </Box>
                );
              })()}
              <TableContainer sx={{ flex: 1, overflowY: 'auto', '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 } }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {['Camera', '↑ Entries', '↓ Exits', 'Occupancy', 'Last Reset'].map(h => (
                        <TableCell key={h} sx={{ fontWeight: 700, fontSize: '0.65rem', py: 0.7, bgcolor: tBgTableHead, color: tTextHeader, borderBottom: `1px solid ${tBorderStrong}` }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {ffRows.length === 0 ? (
                      <TableRow><TableCell colSpan={5} align="center" sx={{ py: 8, color: tTextHeader }}>No footfall data. Enable Footfall Counting in Settings.</TableCell></TableRow>
                    ) : ffRows.map((r, i) => (
                      <TableRow key={i} sx={{ '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }, '& td': { borderBottom: `1px solid ${tBorder}` } }}>
                        <TableCell sx={{ fontSize: '0.7rem', py: 0.7, color: tTextSecondary, fontWeight: 600 }}>{r.cid}</TableCell>
                        <TableCell sx={{ py: 0.7 }}><Typography sx={{ fontSize: '1rem', fontWeight: 800, color: '#00e676' }}>{r.in}</Typography></TableCell>
                        <TableCell sx={{ py: 0.7 }}><Typography sx={{ fontSize: '1rem', fontWeight: 800, color: '#ff6d00' }}>{r.out}</Typography></TableCell>
                        <TableCell sx={{ py: 0.7 }}><Typography sx={{ fontSize: '1rem', fontWeight: 800, color: '#00b0ff' }}>{r.occ}</Typography></TableCell>
                        <TableCell sx={{ fontSize: '0.68rem', py: 0.7, color: tTextSecondary }}>{r.reset}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {/* ─── ANY SECURITY FEATURE ─────────────────────────────────────── */}
          {FM[section] && !['anpr', 'vehicles', 'footfall'].includes(section) && (() => {
            const meta = FM[section];
            const rows = filtered.filter(a => a.feature === section);
            return (
              <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                {/* Header */}
                <Box sx={{
                  px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1.2,
                  borderBottom: `1px solid ${tBorder}`, flexShrink: 0,
                  background: `linear-gradient(90deg, ${meta.color}${isDark ? '15' : '10'} 0%, transparent 60%)`,
                }}>
                  <Box sx={{ color: meta.color, fontSize: 18, display: 'flex', filter: isDark ? `drop-shadow(0 0 6px ${meta.color})` : 'none' }}>
                    {React.cloneElement(meta.icon, { sx: { fontSize: 18 } })}
                  </Box>
                  <Typography sx={{ fontWeight: 800, fontSize: '0.9rem', color: tTextPrimary }}>{meta.label}</Typography>
                  <Chip label={`${rows.length} events`} size="small"
                    sx={{ height: 18, fontSize: '0.62rem', fontWeight: 800, bgcolor: `${meta.color}15`, color: isDark ? meta.color : '#0f172a', border: `1px solid ${meta.color}30` }} />
                  <Button size="small" startIcon={<FileDownload sx={{ fontSize: 13 }} />}
                    onClick={() => exportCSV(['Time','Camera','Severity','Message'], rows.map(r=>[new Date(r.timestamp).toLocaleString(), r.cam_id, r.severity, r.message||'']), `${section}_${new Date().toISOString().slice(0,10)}.csv`)}
                    sx={{ ml: 'auto', fontSize: '0.7rem', px: 1.2, py: '3px', border: `1px solid ${meta.color}50`, color: isDark ? meta.color : '#0f172a', borderRadius: '6px' }}>
                    Export CSV
                  </Button>
                </Box>

                {/* Stats bar */}
                {rows.length > 0 && (
                  <Box sx={{ px: 1.5, py: 1, display: 'flex', gap: 1.2, borderBottom: `1px solid ${tBorder}`, flexShrink: 0, flexWrap: 'wrap' }}>
                    {['CRITICAL','HIGH','MEDIUM','LOW'].map(sev => {
                      const c = rows.filter(r => r.severity === sev).length;
                      if (!c) return null;
                      const sc = SEV_C[sev];
                      return (
                        <Box key={sev} sx={{ bgcolor: `${sc}15`, border: `1px solid ${sc}30`, borderRadius: '6px', px: 1.5, py: 0.6,
                          boxShadow: isDark ? 'none' : '0 2px 4px rgba(0,0,0,0.05)' }}>
                          <Typography sx={{ fontSize: '0.55rem', color: isDark ? sc : '#0f172a', fontWeight: 700, letterSpacing: 0.5 }}>{sev}</Typography>
                          <Typography sx={{ fontSize: '1.2rem', fontWeight: 900, color: sc, lineHeight: 1 }}>{c}</Typography>
                        </Box>
                      );
                    })}
                    <Box sx={{ bgcolor: `${meta.color}15`, border: `1px solid ${meta.color}30`, borderRadius: '6px', px: 1.5, py: 0.6,
                      boxShadow: isDark ? 'none' : '0 2px 4px rgba(0,0,0,0.05)' }}>
                      <Typography sx={{ fontSize: '0.55rem', color: isDark ? meta.color : '#0f172a', fontWeight: 700, letterSpacing: 0.5 }}>CAMERAS</Typography>
                      <Typography sx={{ fontSize: '1.2rem', fontWeight: 900, color: isDark ? meta.color : '#0f172a', lineHeight: 1 }}>{[...new Set(rows.map(r=>r.cam_id))].length}</Typography>
                    </Box>
                  </Box>
                )}

                {/* Security Feature Trend Section */}
                {(() => {
                  const featTrend = Array.from({ length: 7 }, (_, i) => {
                    const d = new Date(now); d.setDate(d.getDate() - (6 - i));
                    const lbl = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
                    return {
                      label: lbl,
                      value: filtered.filter(a => a.feature === section && new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' }) === lbl).length
                    };
                  });
                  return (
                    <Box sx={{ p: 1.5, borderBottom: `1px solid ${tBorder}`, bgcolor: tBgCard, flexShrink: 0 }}>
                      <Typography sx={{ fontSize: '0.65rem', fontWeight: 800, color: tTextHeader, letterSpacing: 1, textTransform: 'uppercase', mb: 1 }}>{meta.label} Trend</Typography>
                      <Box sx={{ height: 100, pr: 2 }}>
                        <LineChart data={featTrend} color={meta.color} />
                      </Box>
                    </Box>
                  );
                })()}

                <TableContainer sx={{ flex: 1, overflowY: 'auto', '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: tScrollThumb, borderRadius: 2 } }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        {['Time', 'Camera', 'Severity', 'Message', 'Snapshot'].map(h => (
                          <TableCell key={h} sx={{ fontWeight: 700, fontSize: '0.65rem', py: 0.7, bgcolor: tBgTableHead, color: tTextHeader, borderBottom: `1px solid ${tBorderStrong}` }}>{h}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.length === 0 ? (
                        <TableRow><TableCell colSpan={5} align="center" sx={{ py: 10, color: tTextHeader, fontSize: '0.85rem' }}>
                          No {meta.label} events detected in this time range.
                        </TableCell></TableRow>
                      ) : rows.map((r, i) => (
                        <TableRow key={i} sx={{ '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }, '& td': { borderBottom: `1px solid ${tBorder}` } }}>
                          <TableCell sx={{ fontSize: '0.68rem', py: 0.6, color: tTextSecondary, whiteSpace: 'nowrap' }}>{new Date(r.timestamp).toLocaleString()}</TableCell>
                          <TableCell sx={{ fontSize: '0.68rem', py: 0.6, color: tTextSecondary, fontWeight: 600 }}>{r.cam_id}</TableCell>
                          <TableCell sx={{ py: 0.6 }}><SevBadge sev={r.severity} /></TableCell>
                          <TableCell sx={{ fontSize: '0.68rem', py: 0.6, color: tTextSecondary, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.message || '—'}</TableCell>
                          <TableCell sx={{ py: 0.6 }} align="center">
                            {r.snapshot_path ? (
                              <IconButton size="small" onClick={() => setZoom(`${API}/clips/${r.snapshot_path}`)}
                                sx={{ color: isDark ? meta.color : '#00b0ff', p: 0.2, '&:hover': { bgcolor: `${meta.color}15` } }}>
                                <OpenInNew sx={{ fontSize: 13 }} />
                              </IconButton>
                            ) : <Typography color="text.disabled" fontSize="0.65rem">—</Typography>}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            );
          })()}
        </Box>
      </Box>

      {/* ═══ SNAPSHOT ZOOM DIALOG ══════════════════════════════════════════════ */}
      <Dialog open={!!zoom} onClose={() => setZoom(null)} maxWidth="lg"
        PaperProps={{ sx: { bgcolor: isDark ? '#0a0c10' : '#ffffff', border: `1px solid ${tBorderStrong}`, borderRadius: '12px', overflow: 'hidden' } }}>
        <DialogTitle sx={{ p: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: `1px solid ${tBorder}`, background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }}>
          <Typography sx={{ fontWeight: 800, fontSize: '0.85rem', color: tTextSecondary }}>Alert Snapshot</Typography>
          <IconButton size="small" onClick={() => setZoom(null)} sx={{ color: tTextMuted }}><Close fontSize="small" /></IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 0, bgcolor: isDark ? '#000' : '#f8fafc' }}>
          {zoom && <img src={zoom} alt="Snapshot" style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain', display: 'block' }} />}
        </DialogContent>
        <DialogActions sx={{ p: 1, borderTop: `1px solid ${tBorder}`, background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)' }}>
          <Button size="small" onClick={() => setZoom(null)} sx={{ color: isDark ? ACC : '#00b0ff', fontWeight: 700, fontSize: '0.75rem' }}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
