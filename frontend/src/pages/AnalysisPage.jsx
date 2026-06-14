import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Grid, Paper, Stack, Divider,
  Button, Select, MenuItem, FormControl, InputLabel, TextField, List,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Chip, Card, CardContent,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Tooltip,
} from '@mui/material';
import {
  Analytics, DirectionsCar, People, Shield, Warning,
  FileDownload, Search, CalendarMonth, Videocam, OpenInNew, Close,
  LocalFireDepartment, Person, GpsFixed, Groups, Refresh,
  Work, Pets, NoPhotography, Login, Notifications, SensorOccupied,
} from '@mui/icons-material';

const API = 'http://localhost:5050';

// ── Feature metadata: ALL features in one place ─────────────────────────────
const FEATURE_META = {
  fire_smoke:          { label: 'Fire & Smoke',        color: '#ff3d00', icon: <LocalFireDepartment fontSize="inherit" /> },
  intrusion:           { label: 'Intrusion',           color: '#ff6d00', icon: <Shield fontSize="inherit" /> },
  no_go_zone:          { label: 'No-Go Zone',          color: '#ff1744', icon: <NoPhotography fontSize="inherit" /> },
  loitering:           { label: 'Loitering',           color: '#ffd600', icon: <Person fontSize="inherit" /> },
  perimeter:           { label: 'Perimeter Breach',    color: '#ff4081', icon: <Login fontSize="inherit" /> },
  crowd:               { label: 'Crowd Alert',         color: '#76ff03', icon: <Groups fontSize="inherit" /> },
  missing_person:      { label: 'Missing Person',      color: '#e040fb', icon: <Person fontSize="inherit" /> },
  personal_monitoring: { label: 'Personal Monitor',    color: '#00e5ff', icon: <GpsFixed fontSize="inherit" /> },
  tampering:           { label: 'Tampering',           color: '#aa00ff', icon: <Videocam fontSize="inherit" /> },
  weapon_detection:    { label: 'Weapon Detected',     color: '#ff1744', icon: <Warning fontSize="inherit" /> },
  criminal_face:       { label: 'Watchlist Match',     color: '#ff6d00', icon: <SensorOccupied fontSize="inherit" /> },
  animal_detection:    { label: 'Animal Alert',        color: '#22c822', icon: <Pets fontSize="inherit" /> },
  vehicle_detection:   { label: 'Vehicle Detection',   color: '#00ffff', icon: <DirectionsCar fontSize="inherit" /> },
  abandoned_object:    { label: 'Left Luggage',        color: '#ff6be6', icon: <Work fontSize="inherit" /> },
  footfall:            { label: 'Footfall Count',      color: '#00b0ff', icon: <People fontSize="inherit" /> },
  anpr:                { label: 'License Plate (ANPR)',color: '#00ffcc', icon: <DirectionsCar fontSize="inherit" /> },
};

// Side navigation items — all groups
const SIDE_ITEMS = [
  { key: 'overview',   label: 'Overview Hub',          icon: <Analytics fontSize="small" />,           group: null },
  { key: 'anpr',       label: 'ANPR — Plates',         icon: <DirectionsCar fontSize="small" />,       group: 'Data Analytics' },
  { key: 'vehicles',   label: 'Vehicle Counting',      icon: <DirectionsCar fontSize="small" />,       group: 'Data Analytics' },
  { key: 'footfall',   label: 'Footfall Counting',     icon: <People fontSize="small" />,              group: 'Data Analytics' },
  { key: 'fire_smoke', label: 'Fire & Smoke',          icon: <LocalFireDepartment fontSize="small" />, group: 'Security Events' },
  { key: 'intrusion',  label: 'Intrusion',             icon: <Shield fontSize="small" />,              group: 'Security Events' },
  { key: 'no_go_zone', label: 'No-Go Zone',            icon: <NoPhotography fontSize="small" />,       group: 'Security Events' },
  { key: 'loitering',  label: 'Loitering',             icon: <Person fontSize="small" />,              group: 'Security Events' },
  { key: 'perimeter',  label: 'Perimeter Breach',      icon: <Login fontSize="small" />,               group: 'Security Events' },
  { key: 'crowd',      label: 'Crowd Alert',           icon: <Groups fontSize="small" />,              group: 'Security Events' },
  { key: 'tampering',  label: 'Tampering',             icon: <Videocam fontSize="small" />,            group: 'Security Events' },
  { key: 'weapon_detection',    label: 'Weapon Detected',   icon: <Warning fontSize="small" />,            group: 'Security Events' },
  { key: 'criminal_face',       label: 'Watchlist Match',   icon: <SensorOccupied fontSize="small" />,     group: 'Security Events' },
  { key: 'missing_person',      label: 'Missing Person',    icon: <Person fontSize="small" />,             group: 'Security Events' },
  { key: 'personal_monitoring', label: 'Personal Monitor',  icon: <GpsFixed fontSize="small" />,           group: 'Security Events' },
  { key: 'animal_detection',    label: 'Animal Alert',      icon: <Pets fontSize="small" />,               group: 'Security Events' },
  { key: 'abandoned_object',    label: 'Left Luggage',      icon: <Work fontSize="small" />,               group: 'Security Events' },
];

// ── Custom SVG Donut Chart ───────────────────────────────────────────────────
function DonutChart({ data, size = 160 }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return (
    <Box display="flex" alignItems="center" justifyContent="center" height={size}>
      <Typography color="text.disabled" variant="caption">No data yet</Typography>
    </Box>
  );
  let cumPercent = 0;
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} style={{ display: 'block', flexShrink: 0 }}>
      {data.map((item, i) => {
        const pct = (item.value / total) * 100;
        const da = `${pct} ${100 - pct}`;
        const offset = 100 - cumPercent + 25;
        cumPercent += pct;
        return (
          <circle key={i} cx="50" cy="50" r="32"
            fill="transparent" stroke={item.color} strokeWidth="10"
            strokeDasharray={da} strokeDashoffset={offset}
            style={{ transition: 'stroke-width 0.15s', cursor: 'pointer' }}
            onMouseEnter={e => e.target.style.strokeWidth = '13'}
            onMouseLeave={e => e.target.style.strokeWidth = '10'}
          />
        );
      })}
      <circle cx="50" cy="50" r="25" fill="#111827" />
      <text x="50" y="47" textAnchor="middle" fill="#fff" fontSize="9" fontWeight="bold">{total}</text>
      <text x="50" y="57" textAnchor="middle" fill="#64748b" fontSize="4.5">Alerts</text>
    </svg>
  );
}

// ── Custom SVG Bar Chart ─────────────────────────────────────────────────────
function BarChart({ data }) {
  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  const W = 400, H = 100, bw = Math.max(8, Math.floor((W - 20) / data.length) - 6), gap = Math.floor((W - 20) / data.length);
  return (
    <svg viewBox={`0 0 ${W} ${H + 28}`} width="100%" height="100%">
      {data.map((d, i) => {
        const bh = (d.value / max) * H;
        const x = 10 + i * gap + (gap - bw) / 2;
        const y = H - bh;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={bh} fill={d.color || '#00ffcc'} rx="2"
              style={{ cursor: 'pointer', transition: 'opacity 0.15s' }}
              onMouseEnter={e => e.target.style.opacity = '0.75'}
              onMouseLeave={e => e.target.style.opacity = '1'} />
            {d.value > 0 && <text x={x + bw / 2} y={y - 3} textAnchor="middle" fill="#fff" fontSize="5" fontWeight="bold">{d.value}</text>}
            <text x={x + bw / 2} y={H + 18} textAnchor="middle" fill="#64748b" fontSize="4.5"
              style={{ fontFamily: 'sans-serif' }}>{d.label.substring(0, 8).replace(/_/g, ' ')}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Custom SVG Line Chart ────────────────────────────────────────────────────
function LineChart({ data, color = '#00ffcc' }) {
  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  const W = 500, H = 100, padL = 30, padR = 10, padT = 10, padB = 24;
  const innerW = W - padL - padR, innerH = H;
  const pts = data.map((d, i) => ({
    x: padL + (i / Math.max(data.length - 1, 1)) * innerW,
    y: padT + innerH - (d.value / max) * innerH,
    label: d.label, value: d.value,
  }));
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  const area = pts.length > 1 ? `${path} L ${pts[pts.length - 1].x} ${padT + innerH} L ${padL} ${padT + innerH} Z` : '';
  return (
    <svg viewBox={`0 0 ${W} ${H + padT + padB}`} width="100%" height="100%">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map((r, i) => {
        const y = padT + r * innerH;
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="1" strokeDasharray="3 2" />
            <text x={padL - 4} y={y + 3} textAnchor="end" fill="#475569" fontSize="6">{Math.round(max * (1 - r))}</text>
          </g>
        );
      })}
      {area && <path d={area} fill="url(#lg)" />}
      {path && <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />}
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r="3" fill="#111827" stroke={color} strokeWidth="1.5" />
          <text x={p.x} y={padT + innerH + padB - 4} textAnchor="middle" fill="#475569" fontSize="6">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ── CSV Helper ───────────────────────────────────────────────────────────────
const exportCSV = (headers, rows, name) => {
  const csv = [headers, ...rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`))].map(r => r.join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = name;
  a.click();
};

// ── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, color, sub }) {
  return (
    <Card sx={{ borderLeft: `3px solid ${color}`, bgcolor: 'background.paper', borderRadius: 1.5, height: '100%' }}>
      <CardContent sx={{ p: '10px 14px !important' }}>
        <Typography variant="caption" color="text.secondary" fontWeight={700} sx={{ fontSize: '0.65rem', letterSpacing: 0.5 }}>
          {label}
        </Typography>
        <Typography variant="h4" fontWeight={900} sx={{ color, lineHeight: 1.2, my: '2px', fontSize: '2rem' }}>
          {value}
        </Typography>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>{sub}</Typography>
      </CardContent>
    </Card>
  );
}

// ── Feature Alert Table (reusable for each feature section) ──────────────────
function FeatureAlertTable({ alerts, feature, onZoom }) {
  const meta = FEATURE_META[feature] || { label: feature, color: '#00ffcc' };
  const rows = alerts.filter(a => a.feature === feature);
  const handleExport = () => {
    exportCSV(
      ['Time', 'Camera', 'Severity', 'Message'],
      rows.map(r => [new Date(r.timestamp).toLocaleString(), r.cam_id, r.severity, r.message || '']),
      `${feature}_${new Date().toISOString().slice(0, 10)}.csv`
    );
  };
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5, borderBottom: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box sx={{ color: meta.color, fontSize: 18, lineHeight: 1, display: 'flex', alignItems: 'center' }}>{meta.icon}</Box>
          <Typography fontWeight={800} fontSize="0.9rem">{meta.label} — Logs</Typography>
          <Chip label={`${rows.length}`} size="small" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, bgcolor: `${meta.color}18`, color: meta.color }} />
        </Stack>
        <Button size="small" startIcon={<FileDownload fontSize="small" />} onClick={handleExport}
          sx={{ fontSize: '0.72rem', px: 1.5, py: 0.4, border: `1px solid ${meta.color}44`, color: meta.color, borderRadius: 1, '&:hover': { bgcolor: `${meta.color}10` } }}>
          CSV
        </Button>
      </Stack>
      {rows.length === 0 ? (
        <Box flex={1} display="flex" alignItems="center" justifyContent="center">
          <Typography color="text.disabled" fontSize="0.85rem">No {meta.label} alerts found for this period.</Typography>
        </Box>
      ) : (
        <TableContainer sx={{ flex: 1, overflowY: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {['Time', 'Camera', 'Severity', 'Message', 'Snap'].map(h => (
                  <TableCell key={h} sx={{ fontWeight: 800, fontSize: '0.7rem', py: 0.8, bgcolor: 'background.paper' }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r, i) => {
                const sevColor = r.severity === 'CRITICAL' ? '#ff1744' : r.severity === 'HIGH' ? '#ff6d00' : r.severity === 'MEDIUM' ? '#ffd600' : '#00b0ff';
                return (
                  <TableRow key={i} hover>
                    <TableCell sx={{ fontSize: '0.72rem', py: 0.6, whiteSpace: 'nowrap' }}>{new Date(r.timestamp).toLocaleString()}</TableCell>
                    <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{r.cam_id}</TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Chip label={r.severity || '—'} size="small"
                        sx={{ height: 16, fontSize: '0.58rem', fontWeight: 800, color: sevColor, bgcolor: `${sevColor}18`, border: `1px solid ${sevColor}44` }} />
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.72rem', py: 0.6, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.message}</TableCell>
                    <TableCell sx={{ py: 0.6 }} align="center">
                      {r.snapshot_path ? (
                        <IconButton size="small" onClick={() => onZoom(`${API}/clips/${r.snapshot_path}`)} sx={{ color: meta.color, p: 0.3 }}>
                          <OpenInNew sx={{ fontSize: 14 }} />
                        </IconButton>
                      ) : <Typography color="text.disabled" fontSize="0.7rem">—</Typography>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
export default function AnalysisPage() {
  const [section, setSection] = useState('overview');
  const [alerts, setAlerts] = useState([]);
  const [vehicleStats, setVehicleStats] = useState({});
  const [footfallStats, setFootfallStats] = useState({});
  const [backendOnline, setBackendOnline] = useState(false);
  const [loading, setLoading] = useState(false);

  // Filters
  const [camFilter, setCamFilter] = useState('all');
  const [dateRange, setDateRange] = useState('7days');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [search, setSearch] = useState('');

  // Image zoom dialog
  const [zoomImg, setZoomImg] = useState(null);

  // Load data from backend (non-blocking — UI renders immediately)
  const fetchData = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/api/alerts?limit=500`).then(r => r.json()).catch(() => []),
      fetch(`${API}/api/analytics/vehicles`).then(r => r.json()).catch(() => ({})),
      fetch(`${API}/api/analytics/footfall`).then(r => r.json()).catch(() => ({})),
    ]).then(([a, v, f]) => {
      setAlerts(Array.isArray(a) ? a : []);
      setVehicleStats(v || {});
      setFootfallStats(f || {});
      setBackendOnline(true);
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, []);

  // ── Filter helper ────────────────────────────────────────────────────────
  const filtered = alerts.filter(a => {
    if (camFilter !== 'all' && a.cam_id !== camFilter) return false;
    const t = new Date(a.timestamp);
    const now = new Date();
    if (dateRange === 'today') {
      if (t < new Date(now.getFullYear(), now.getMonth(), now.getDate())) return false;
    } else if (dateRange === '7days') {
      if (t < new Date(now - 7 * 86400000)) return false;
    } else if (dateRange === 'custom') {
      if (startDate && t < new Date(startDate)) return false;
      if (endDate) { const e = new Date(endDate); e.setHours(23, 59, 59, 999); if (t > e) return false; }
    }
    return true;
  });

  const cameraIds = [...new Set(alerts.map(a => a.cam_id))].filter(Boolean);

  // ── Overview calc ─────────────────────────────────────────────────────────
  const breakdown = filtered.reduce((acc, a) => { acc[a.feature] = (acc[a.feature] || 0) + 1; return acc; }, {});
  const pieData = Object.entries(breakdown).map(([k, v]) => ({ label: FEATURE_META[k]?.label || k, value: v, color: FEATURE_META[k]?.color || '#999' }));
  const barData = Object.entries(breakdown)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([k, v]) => ({ label: FEATURE_META[k]?.label || k, value: v, color: FEATURE_META[k]?.color || '#999' }));

  const now = new Date();
  const trendData = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now); d.setDate(d.getDate() - (6 - i));
    const label = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    const value = filtered.filter(a => new Date(a.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' }) === label).length;
    return { label, value };
  });

  // ANPR
  const anprRows = filtered.filter(a => a.feature === 'anpr').map(a => ({
    timestamp: a.timestamp, cam_id: a.cam_id,
    plate: a.plate_text || a.detections?.[0]?.plate_text || 'UNKNOWN',
    confidence: a.confidence || 0,
  })).filter(r => !search || r.plate.toLowerCase().includes(search.toLowerCase()));

  // Vehicle
  const vehicleRows = Object.entries(vehicleStats).flatMap(([cam_id, c]) => {
    if (camFilter !== 'all' && cam_id !== camFilter) return [];
    return Object.entries(c.by_type || {}).map(([vtype, cnt]) => ({ cam_id, vtype, in: cnt.in || 0, out: cnt.out || 0, reset: c.last_reset_date || '—' }));
  });

  // Footfall
  const footfallRows = Object.entries(footfallStats).flatMap(([cam_id, c]) => {
    if (camFilter !== 'all' && cam_id !== camFilter) return [];
    return [{ cam_id, in: c.count_in || 0, out: c.count_out || 0, occ: c.occupancy || 0, reset: c.last_reset_date || '—' }];
  });

  const ACCENT = '#00ffcc';
  const SIDEBAR_W = 200;

  // Group side items
  const groups = {};
  SIDE_ITEMS.forEach(item => {
    const g = item.group || '';
    if (!groups[g]) groups[g] = [];
    groups[g].push(item);
  });

  return (
    <Box sx={{ display: 'flex', width: '100%', height: '100%', overflow: 'hidden', bgcolor: 'background.default' }}>

      {/* ══ SIDEBAR ══════════════════════════════════════════════════════════ */}
      <Box sx={{
        width: SIDEBAR_W, flexShrink: 0, bgcolor: 'background.paper',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', flexDirection: 'column',
        overflowY: 'auto', overflowX: 'hidden',
      }}>
        {Object.entries(groups).map(([groupName, items]) => (
          <Box key={groupName}>
            {groupName && (
              <Typography variant="caption" sx={{ px: 1.5, pt: 1.5, pb: 0.5, display: 'block', color: 'text.disabled', fontSize: '0.6rem', fontWeight: 800, letterSpacing: 1, textTransform: 'uppercase' }}>
                {groupName}
              </Typography>
            )}
            <List disablePadding>
              {items.map(item => {
                const active = section === item.key;
                const meta = FEATURE_META[item.key];
                const accentColor = meta?.color || ACCENT;
                return (
                  <ListItem key={item.key} disablePadding>
                    <ListItemButton
                      selected={active}
                      onClick={() => { setSection(item.key); setSearch(''); }}
                      sx={{
                        py: 0.7, px: 1.5, minHeight: 0,
                        borderLeft: active ? `3px solid ${accentColor}` : '3px solid transparent',
                        bgcolor: active ? `${accentColor}10` : 'transparent',
                        '&:hover': { bgcolor: `${accentColor}08` },
                        transition: 'all 0.15s',
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 28, color: active ? accentColor : 'text.disabled', fontSize: 16 }}>
                        {item.icon}
                      </ListItemIcon>
                      <ListItemText
                        primary={item.label}
                        primaryTypographyProps={{
                          fontSize: '0.75rem',
                          fontWeight: active ? 700 : 500,
                          color: active ? accentColor : 'text.secondary',
                          lineHeight: 1.3,
                          noWrap: true,
                        }}
                      />
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
          </Box>
        ))}
      </Box>

      {/* ══ MAIN AREA ════════════════════════════════════════════════════════ */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* ── Filter bar ──────────────────────────────────────────────────── */}
        <Box sx={{
          px: 1.5, py: 0.75,
          display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          bgcolor: 'background.paper', flexShrink: 0,
        }}>
          {/* Camera filter */}
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel sx={{ fontSize: '0.72rem' }}>Camera</InputLabel>
            <Select value={camFilter} label="Camera" onChange={e => setCamFilter(e.target.value)}
              sx={{ fontSize: '0.72rem', '& .MuiSelect-select': { py: '5px' } }}>
              <MenuItem value="all" sx={{ fontSize: '0.8rem' }}>All Cameras</MenuItem>
              {cameraIds.map(c => <MenuItem key={c} value={c} sx={{ fontSize: '0.8rem' }}>{c}</MenuItem>)}
            </Select>
          </FormControl>

          {/* Date range */}
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel sx={{ fontSize: '0.72rem' }}>Date Range</InputLabel>
            <Select value={dateRange} label="Date Range" onChange={e => setDateRange(e.target.value)}
              sx={{ fontSize: '0.72rem', '& .MuiSelect-select': { py: '5px' } }}>
              <MenuItem value="today" sx={{ fontSize: '0.8rem' }}>Today</MenuItem>
              <MenuItem value="7days" sx={{ fontSize: '0.8rem' }}>Last 7 Days</MenuItem>
              <MenuItem value="custom" sx={{ fontSize: '0.8rem' }}>Custom</MenuItem>
            </Select>
          </FormControl>

          {dateRange === 'custom' && (
            <>
              <TextField size="small" type="date" label="From" value={startDate}
                onChange={e => setStartDate(e.target.value)} InputLabelProps={{ shrink: true }}
                sx={{ '& .MuiInputBase-input': { py: '5px', fontSize: '0.72rem' }, width: 130 }} />
              <TextField size="small" type="date" label="To" value={endDate}
                onChange={e => setEndDate(e.target.value)} InputLabelProps={{ shrink: true }}
                sx={{ '& .MuiInputBase-input': { py: '5px', fontSize: '0.72rem' }, width: 130 }} />
            </>
          )}

          <Button size="small" startIcon={<Refresh sx={{ fontSize: '14px !important' }} />} onClick={fetchData}
            disabled={loading}
            sx={{
              fontSize: '0.72rem', px: 1.5, py: '4px', fontWeight: 700, borderRadius: 1,
              bgcolor: 'rgba(0,255,204,0.08)', color: ACCENT,
              border: '1px solid rgba(0,255,204,0.25)',
              '&:hover': { bgcolor: 'rgba(0,255,204,0.15)' },
            }}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>

          <Box sx={{ ml: 'auto', display: 'flex', alignItems: 'center', gap: 1 }}>
            {!backendOnline && (
              <Chip label="Backend offline — cached data" size="small"
                sx={{ fontSize: '0.62rem', height: 18, bgcolor: '#ff6d0018', color: '#ff9100', border: '1px solid #ff9100' }} />
            )}
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>
              {filtered.length} alerts
            </Typography>
          </Box>
        </Box>

        {/* ── Content area ────────────────────────────────────────────────── */}
        <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

          {/* ─── OVERVIEW ─────────────────────────────────────────────────── */}
          {section === 'overview' && (
            <Box sx={{ flex: 1, overflowY: 'auto', p: 1.5 }}>
              {/* KPI Row */}
              <Grid container spacing={1.5} mb={1.5}>
                {[
                  { label: 'CRITICAL ALERTS', value: filtered.filter(a => a.severity === 'CRITICAL').length, color: '#ff1744', sub: 'Fires & violations' },
                  { label: 'HIGH ALERTS',     value: filtered.filter(a => a.severity === 'HIGH').length,     color: '#ff6d00', sub: 'Intrusions & threats' },
                  { label: 'ANPR SCANS',      value: filtered.filter(a => a.feature === 'anpr').length,      color: ACCENT,    sub: 'Plates recognized' },
                  { label: 'TOTAL FOOTFALL',  value: Object.values(footfallStats).reduce((s, c) => s + (c.count_in || 0) + (c.count_out || 0), 0), color: '#00b0ff', sub: 'Crossings logged' },
                  { label: 'VEHICLE VOLUME',  value: Object.values(vehicleStats).reduce((s, c) => s + (c.total?.in || 0) + (c.total?.out || 0), 0), color: '#ff9100', sub: 'Monitored crossings' },
                  { label: 'TOTAL ALERTS',    value: filtered.length,                                         color: '#76ff03', sub: 'All events combined' },
                ].map((kpi, i) => (
                  <Grid key={i} item xs={6} sm={4} md={2}>
                    <StatCard {...kpi} />
                  </Grid>
                ))}
              </Grid>

              {/* Charts row */}
              <Grid container spacing={1.5}>
                {/* Donut + legend */}
                <Grid item xs={12} md={4}>
                  <Paper sx={{ p: 1.5, height: 260, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 1.5, display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="caption" fontWeight={800} color="text.secondary" sx={{ fontSize: '0.65rem', letterSpacing: 0.5, mb: 1 }}>BREAKDOWN BY FEATURE</Typography>
                    <Box sx={{ display: 'flex', flex: 1, alignItems: 'center', gap: 1.5, overflow: 'hidden' }}>
                      <DonutChart data={pieData} size={130} />
                      <Box sx={{ flex: 1, overflowY: 'auto', maxHeight: 220 }}>
                        {pieData.sort((a, b) => b.value - a.value).map((d, i) => (
                          <Stack key={i} direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.5 }}>
                            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: d.color, flexShrink: 0 }} />
                            <Typography fontSize="0.65rem" color="text.secondary" noWrap sx={{ flex: 1 }}>{d.label}</Typography>
                            <Typography fontSize="0.65rem" fontWeight={800} color={d.color}>{d.value}</Typography>
                          </Stack>
                        ))}
                      </Box>
                    </Box>
                  </Paper>
                </Grid>

                {/* Line trend */}
                <Grid item xs={12} md={5}>
                  <Paper sx={{ p: 1.5, height: 260, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 1.5, display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="caption" fontWeight={800} color="text.secondary" sx={{ fontSize: '0.65rem', letterSpacing: 0.5, mb: 1 }}>ALERT FREQUENCY — LAST 7 DAYS</Typography>
                    <Box sx={{ flex: 1 }}>
                      <LineChart data={trendData} color={ACCENT} />
                    </Box>
                  </Paper>
                </Grid>

                {/* Bar chart */}
                <Grid item xs={12} md={3}>
                  <Paper sx={{ p: 1.5, height: 260, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 1.5, display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="caption" fontWeight={800} color="text.secondary" sx={{ fontSize: '0.65rem', letterSpacing: 0.5, mb: 1 }}>TOP FEATURES (BAR)</Typography>
                    <Box sx={{ flex: 1 }}>
                      <BarChart data={barData.slice(0, 8)} />
                    </Box>
                  </Paper>
                </Grid>

                {/* Recent alerts mini-feed */}
                <Grid item xs={12}>
                  <Paper sx={{ bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 1.5, overflow: 'hidden' }}>
                    <Box sx={{ px: 1.5, py: 1, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <Typography variant="caption" fontWeight={800} color="text.secondary" sx={{ fontSize: '0.65rem', letterSpacing: 0.5 }}>
                        RECENT ALERTS
                      </Typography>
                    </Box>
                    <TableContainer sx={{ maxHeight: 220 }}>
                      <Table size="small" stickyHeader>
                        <TableHead>
                          <TableRow>
                            {['Time', 'Camera', 'Feature', 'Severity', 'Message'].map(h => (
                              <TableCell key={h} sx={{ fontWeight: 800, fontSize: '0.65rem', py: 0.6, bgcolor: 'background.paper' }}>{h}</TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {filtered.slice(0, 30).map((a, i) => {
                            const meta = FEATURE_META[a.feature] || { label: a.feature, color: '#00ffcc' };
                            const sc = a.severity === 'CRITICAL' ? '#ff1744' : a.severity === 'HIGH' ? '#ff6d00' : a.severity === 'MEDIUM' ? '#ffd600' : '#00b0ff';
                            return (
                              <TableRow key={i} hover>
                                <TableCell sx={{ fontSize: '0.68rem', py: 0.5, whiteSpace: 'nowrap' }}>{new Date(a.timestamp).toLocaleString()}</TableCell>
                                <TableCell sx={{ fontSize: '0.68rem', py: 0.5 }}>{a.cam_id}</TableCell>
                                <TableCell sx={{ fontSize: '0.68rem', py: 0.5, fontWeight: 700, color: meta.color }}>{meta.label}</TableCell>
                                <TableCell sx={{ py: 0.5 }}>
                                  <Chip label={a.severity || '—'} size="small" sx={{ height: 15, fontSize: '0.55rem', fontWeight: 800, color: sc, bgcolor: `${sc}18` }} />
                                </TableCell>
                                <TableCell sx={{ fontSize: '0.68rem', py: 0.5, maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.message}</TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Paper>
                </Grid>
              </Grid>
            </Box>
          )}

          {/* ─── ANPR ─────────────────────────────────────────────────────── */}
          {section === 'anpr' && (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <Box sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
                <TextField size="small" placeholder="Filter by plate…" value={search} onChange={e => setSearch(e.target.value)}
                  InputProps={{ startAdornment: <Search sx={{ fontSize: 16, color: 'text.secondary', mr: 0.5 }} /> }}
                  sx={{ '& .MuiInputBase-input': { py: '5px', fontSize: '0.75rem' }, width: 200 }} />
                <Chip label={`${anprRows.length} scans`} size="small" sx={{ fontSize: '0.65rem', bgcolor: '#00ffcc18', color: ACCENT }} />
                <Button size="small" startIcon={<FileDownload fontSize="small" />}
                  onClick={() => exportCSV(['Time', 'Camera', 'Plate', 'Confidence'], anprRows.map(r => [new Date(r.timestamp).toLocaleString(), r.cam_id, r.plate, `${(r.confidence * 100).toFixed(0)}%`]), `anpr_${new Date().toISOString().slice(0, 10)}.csv`)}
                  sx={{ fontSize: '0.72rem', px: 1.2, py: '4px', border: '1px solid #00ffcc44', color: ACCENT, borderRadius: 1, '&:hover': { bgcolor: '#00ffcc0a' } }}>CSV</Button>
              </Box>
              <TableContainer sx={{ flex: 1, overflowY: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {['Time', 'Camera', 'License Plate', 'Confidence'].map(h => (
                        <TableCell key={h} sx={{ fontWeight: 800, fontSize: '0.7rem', py: 0.7, bgcolor: 'background.paper' }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {anprRows.length === 0 ? (
                      <TableRow><TableCell colSpan={4} align="center" sx={{ py: 6, color: 'text.disabled', fontSize: '0.85rem' }}>No ANPR plates detected yet.</TableCell></TableRow>
                    ) : anprRows.map((r, i) => (
                      <TableRow key={i} hover>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{new Date(r.timestamp).toLocaleString()}</TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{r.cam_id}</TableCell>
                        <TableCell sx={{ py: 0.6 }}>
                          <Typography sx={{ fontFamily: 'monospace', fontWeight: 800, fontSize: '0.85rem', color: ACCENT, letterSpacing: 1 }}>{r.plate}</Typography>
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{(r.confidence * 100).toFixed(0)}%</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {/* ─── VEHICLE COUNTING ─────────────────────────────────────────── */}
          {section === 'vehicles' && (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <Box sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
                <Typography fontWeight={800} fontSize="0.85rem">Vehicle Traffic Distribution</Typography>
                <Button size="small" startIcon={<FileDownload fontSize="small" />}
                  onClick={() => exportCSV(['Camera', 'Type', 'IN', 'OUT', 'Reset'], vehicleRows.map(r => [r.cam_id, r.vtype, r.in, r.out, r.reset]), `vehicles_${new Date().toISOString().slice(0, 10)}.csv`)}
                  sx={{ fontSize: '0.72rem', ml: 'auto', px: 1.2, py: '4px', border: '1px solid #00ffcc44', color: ACCENT, borderRadius: 1 }}>CSV</Button>
              </Box>
              <TableContainer sx={{ flex: 1, overflowY: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {['Camera', 'Vehicle Type', 'IN ↑', 'OUT ↓', 'Last Reset'].map(h => (
                        <TableCell key={h} sx={{ fontWeight: 800, fontSize: '0.7rem', py: 0.7, bgcolor: 'background.paper' }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vehicleRows.length === 0 ? (
                      <TableRow><TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.disabled' }}>No vehicle counts yet. Enable Vehicle Detection in Settings.</TableCell></TableRow>
                    ) : vehicleRows.map((r, i) => (
                      <TableRow key={i} hover>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{r.cam_id}</TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6, textTransform: 'capitalize', fontWeight: 600 }}>{r.vtype}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.6, fontWeight: 800, color: '#00e676' }}>{r.in}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.6, fontWeight: 800, color: '#ff6d00' }}>{r.out}</TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{r.reset}</TableCell>
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
              <Box sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
                <Typography fontWeight={800} fontSize="0.85rem">Footfall Crossings & Occupancy</Typography>
                <Button size="small" startIcon={<FileDownload fontSize="small" />}
                  onClick={() => exportCSV(['Camera', 'IN', 'OUT', 'Occupancy', 'Reset'], footfallRows.map(r => [r.cam_id, r.in, r.out, r.occ, r.reset]), `footfall_${new Date().toISOString().slice(0, 10)}.csv`)}
                  sx={{ fontSize: '0.72rem', ml: 'auto', px: 1.2, py: '4px', border: '1px solid #00b0ff44', color: '#00b0ff', borderRadius: 1 }}>CSV</Button>
              </Box>
              <TableContainer sx={{ flex: 1, overflowY: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {['Camera', 'Entries (IN)', 'Exits (OUT)', 'Occupancy', 'Last Reset'].map(h => (
                        <TableCell key={h} sx={{ fontWeight: 800, fontSize: '0.7rem', py: 0.7, bgcolor: 'background.paper' }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {footfallRows.length === 0 ? (
                      <TableRow><TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.disabled' }}>No footfall data yet. Enable Footfall Counting in Settings.</TableCell></TableRow>
                    ) : footfallRows.map((r, i) => (
                      <TableRow key={i} hover>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{r.cam_id}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.6, fontWeight: 800, color: '#00e676' }}>{r.in}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.6, fontWeight: 800, color: '#ff6d00' }}>{r.out}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', py: 0.6, fontWeight: 800, color: '#00e5ff' }}>{r.occ}</TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', py: 0.6 }}>{r.reset}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {/* ─── ANY FEATURE ALERT TABLE ──────────────────────────────────── */}
          {!['overview', 'anpr', 'vehicles', 'footfall'].includes(section) && (
            <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <FeatureAlertTable alerts={filtered} feature={section} onZoom={setZoomImg} />
            </Box>
          )}

        </Box>
      </Box>

      {/* ══ ZOOM DIALOG ══════════════════════════════════════════════════════ */}
      <Dialog open={!!zoomImg} onClose={() => setZoomImg(null)} maxWidth="lg" PaperProps={{ sx: { bgcolor: 'background.paper' } }}>
        <DialogTitle sx={{ p: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography fontWeight={800} fontSize="0.9rem">Alert Snapshot</Typography>
          <IconButton size="small" onClick={() => setZoomImg(null)}><Close fontSize="small" /></IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 0, bgcolor: '#000' }}>
          {zoomImg && <img src={zoomImg} alt="Snapshot" style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain', display: 'block' }} />}
        </DialogContent>
        <DialogActions sx={{ p: 1, bgcolor: 'background.paper' }}>
          <Button size="small" onClick={() => setZoomImg(null)} sx={{ color: ACCENT, fontWeight: 700, fontSize: '0.75rem' }}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
