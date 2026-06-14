import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Grid, Paper, Stack, CircularProgress, Alert, Divider,
  Button, Select, MenuItem, FormControl, InputLabel, TextField, List,
  ListItem, ListItemButton, ListItemIcon, ListItemText, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, Chip, Card, CardContent,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton
} from '@mui/material';
import {
  Analytics, DirectionsCar, People, Notifications, Shield, Warning,
  Timeline, FileDownload, Search, CalendarMonth, Videocam, OpenInNew, Close
} from '@mui/icons-material';

const API = 'http://localhost:5050';

const FEATURE_COLORS = {
  fire_smoke: '#ff1744',
  intrusion: '#ff6d00',
  loitering: '#ffd600',
  no_go_zone: '#ff1744',
  crowd: '#76ff03',
  footfall: '#00b0ff',
  perimeter: '#ff4081',
  missing_person: '#e040fb',
  personal_monitoring: '#00e5ff',
  tampering: '#aa00ff',
  weapon_detection: '#ff1744',
  criminal_face: '#ff6d00',
  animal_detection: '#22c822',
  vehicle_detection: '#00ffff',
  abandoned_object: '#ff6be6',
  anpr: '#00ffcc',
};

const FEATURE_LABELS = {
  fire_smoke: 'Fire & Smoke',
  intrusion: 'Intrusion Detection',
  loitering: 'Loitering Alert',
  no_go_zone: 'No-Go Zone Violation',
  crowd: 'Crowd Detection',
  footfall: 'Footfall Counting',
  perimeter: 'Perimeter Breached',
  missing_person: 'Missing Person',
  personal_monitoring: 'Personal Monitor',
  tampering: 'Tampering Alert',
  weapon_detection: 'Weapon Detected',
  criminal_face: 'Watchlist Match',
  animal_detection: 'Animal Spotted',
  vehicle_detection: 'Vehicle Log',
  abandoned_object: 'Left Luggage',
  anpr: 'License Plate (ANPR)',
};

// ── Custom Interactive SVG Donut Chart ──────────────────────────────────────
function DonutChart({ data, colors }) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height={220}>
        <Typography color="text.secondary" variant="body2">No data to display</Typography>
      </Box>
    );
  }

  let accumulatedPercent = 0;
  return (
    <svg viewBox="0 0 100 100" width="100%" height="220" style={{ display: 'block' }}>
      {data.map((item, index) => {
        const percent = (item.value / total) * 100;
        const strokeDasharray = `${percent} ${100 - percent}`;
        const strokeDashoffset = 100 - accumulatedPercent + 25; // +25 starts at 12 o'clock
        accumulatedPercent += percent;
        const color = colors[item.label] || '#999';
        return (
          <circle
            key={index}
            cx="50"
            cy="50"
            r="32"
            fill="transparent"
            stroke={color}
            strokeWidth="11"
            strokeDasharray={strokeDasharray}
            strokeDashoffset={strokeDashoffset}
            style={{ transition: 'stroke-width 0.2s, opacity 0.2s', cursor: 'pointer' }}
            onMouseEnter={(e) => { e.target.style.strokeWidth = '13'; }}
            onMouseLeave={(e) => { e.target.style.strokeWidth = '11'; }}
          />
        );
      })}
      <circle cx="50" cy="50" r="25" fill="#1e293b" />
      <text x="50" y="47" textAnchor="middle" fill="#fff" fontSize="8" fontWeight="bold">
        {total}
      </text>
      <text x="50" y="56" textAnchor="middle" fill="#94a3b8" fontSize="4.5">
        Alerts
      </text>
    </svg>
  );
}

// ── Custom Responsive SVG Bar Chart ──────────────────────────────────────────
function BarChart({ data, colors }) {
  const maxVal = Math.max(...data.map(d => d.value), 1);
  const chartHeight = 130;
  const barWidth = 14;
  const gap = 16;
  const totalWidth = Math.max(300, data.length * (barWidth + gap) + gap);

  return (
    <Box sx={{ width: '100%', overflowX: 'auto', py: 1 }}>
      <svg viewBox={`0 0 ${totalWidth} ${chartHeight + 35}`} width="100%" height="220">
        {/* Horizontal grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
          const y = 10 + ratio * chartHeight;
          return (
            <line key={idx} x1="0" y1={y} x2={totalWidth} y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
          );
        })}

        {data.map((item, index) => {
          const valPercent = item.value / maxVal;
          const barHeight = valPercent * chartHeight;
          const x = gap + index * (barWidth + gap);
          const y = chartHeight - barHeight + 10;
          const color = colors[item.label] || '#00ffcc';

          return (
            <g key={index}>
              {/* Bar */}
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                fill={color}
                rx="3.5"
                style={{ transition: 'all 0.3s ease-in-out', cursor: 'pointer' }}
                onMouseEnter={(e) => { e.target.style.opacity = '0.80'; }}
                onMouseLeave={(e) => { e.target.style.opacity = '1.0'; }}
              />
              {/* Value top label */}
              <text x={x + barWidth / 2} y={y - 4} textAnchor="middle" fill="#fff" fontSize="6.5" fontWeight="800">
                {item.value}
              </text>
              {/* Axis label */}
              <text
                x={x + barWidth / 2}
                y={chartHeight + 22}
                textAnchor="middle"
                fill="#94a3b8"
                fontSize="5.5"
                fontWeight="500"
                style={{ textTransform: 'capitalize' }}
              >
                {item.label.substring(0, 10).replace(/_/g, ' ')}
              </text>
            </g>
          );
        })}
      </svg>
    </Box>
  );
}

// ── Custom SVG Line Trend Chart ──────────────────────────────────────────────
function LineChart({ data, color = '#00ffcc' }) {
  const maxVal = Math.max(...data.map(d => d.value), 1);
  const chartHeight = 110;
  const chartWidth = 500;
  const padding = 35;

  const points = data.map((item, index) => {
    const x = padding + (index * (chartWidth - padding * 2)) / (data.length - 1 || 1);
    const y = chartHeight + padding - (item.value / maxVal) * chartHeight;
    return { x, y, label: item.label, value: item.value };
  });

  const pathD = points.reduce((acc, p, idx) => {
    return idx === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`;
  }, '');

  const areaD = points.length
    ? `${pathD} L ${points[points.length - 1].x} ${chartHeight + padding} L ${points[0].x} ${chartHeight + padding} Z`
    : '';

  return (
    <svg viewBox={`0 0 ${chartWidth} ${chartHeight + padding + 20}`} width="100%" height="220">
      <defs>
        <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
        const y = padding + ratio * chartHeight;
        const gridVal = Math.round(maxVal * (1 - ratio));
        return (
          <g key={idx}>
            <line x1={padding} y1={y} x2={chartWidth - padding} y2={y} stroke="rgba(255,255,255,0.04)" strokeWidth="1" strokeDasharray="3 3" />
            <text x={padding - 8} y={y + 3} textAnchor="end" fill="#64748b" fontSize="7" fontWeight="500">{gridVal}</text>
          </g>
        );
      })}

      {/* Filled Area */}
      {areaD && <path d={areaD} fill={`url(#lineGrad)`} />}

      {/* Main Trend Line */}
      {pathD && <path d={pathD} fill="transparent" stroke={color} strokeWidth="2.5" strokeLinecap="round" />}

      {/* Nodes */}
      {points.map((p, idx) => (
        <g key={idx}>
          <circle cx={p.x} cy={p.y} r="3.5" fill="#1e293b" stroke={color} strokeWidth="1.5" style={{ cursor: 'pointer' }} />
          <text x={p.x} y={chartHeight + padding + 15} textAnchor="middle" fill="#64748b" fontSize="6.5" fontWeight="500">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ── Native Browser CSV Export Helper ─────────────────────────────────────────
const exportToCSV = (headers, rows, filename) => {
  const csvRows = [headers.join(',')];
  for (const row of rows) {
    const values = row.map(val => {
      const escaped = ('' + (val ?? '')).replace(/"/g, '""');
      return `"${escaped}"`;
    });
    csvRows.push(values.join(','));
  }
  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

export default function AnalysisPage() {
  const [selectedSection, setSelectedSection] = useState('overview');
  const [alerts, setAlerts] = useState([]);
  const [vehicleStats, setVehicleStats] = useState({});
  const [footfallStats, setFootfallStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters state
  const [camFilter, setCamFilter] = useState('all');
  const [dateRange, setDateRange] = useState('7days'); // today, 7days, custom
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Dialog Image Zoom
  const [zoomImg, setZoomImg] = useState(null);

  const fetchData = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/api/alerts?limit=200`).then(r => r.json()),
      fetch(`${API}/api/analytics/vehicles`).then(r => r.json()).catch(() => ({})),
      fetch(`${API}/api/analytics/footfall`).then(r => r.json()).catch(() => ({})),
    ])
      .then(([alertsData, vehiclesData, footfallsData]) => {
        setAlerts(Array.isArray(alertsData) ? alertsData : []);
        setVehicleStats(vehiclesData || {});
        setFootfallStats(footfallsData || {});
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Filter alert helper
  const getFilteredAlerts = () => {
    return alerts.filter(a => {
      // Camera ID Filter
      if (camFilter !== 'all' && a.cam_id !== camFilter) return false;

      // Date Range Filter
      const alertTime = new Date(a.timestamp);
      const now = new Date();
      if (dateRange === 'today') {
        const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (alertTime < todayStart) return false;
      } else if (dateRange === '7days') {
        const lastWeek = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        if (alertTime < lastWeek) return false;
      } else if (dateRange === 'custom') {
        if (startDate) {
          const sDate = new Date(startDate);
          if (alertTime < sDate) return false;
        }
        if (endDate) {
          const eDate = new Date(endDate);
          eDate.setHours(23, 59, 59, 999);
          if (alertTime > eDate) return false;
        }
      }
      return true;
    });
  };

  if (loading) return <Box p={6} textAlign="center"><CircularProgress size={50} sx={{ color: '#00ffcc' }} /></Box>;
  if (error) return <Box p={4}><Alert severity="error">Backend unavailable: {error}</Alert></Box>;

  const filteredAlerts = getFilteredAlerts();
  const cameraList = Array.from(new Set(alerts.map(a => a.cam_id)));

  // ── Overview Data Calculations ─────────────────────────────────────────────
  const alertBreakdown = filteredAlerts.reduce((acc, a) => {
    acc[a.feature] = (acc[a.feature] || 0) + 1;
    return acc;
  }, {});

  const pieData = Object.entries(alertBreakdown).map(([key, val]) => ({
    label: FEATURE_LABELS[key] || key,
    value: val,
  }));

  // Trend data: last 7 days alert counts
  const last7DaysLabels = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - i);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }).reverse();

  const trendData = last7DaysLabels.map(label => {
    const count = filteredAlerts.filter(a => {
      const aLabel = new Date(a.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      return aLabel === label;
    }).length;
    return { label, value: count };
  });

  // ── ANPR Scan Logs view helper ─────────────────────────────────────────────
  const anprAlerts = filteredAlerts
    .filter(a => a.feature === 'anpr')
    .map(a => {
      const det = a.detections?.[0] || {};
      return {
        timestamp: a.timestamp,
        cam_id: a.cam_id,
        plate: a.plate_text || det.plate_text || 'UNKNOWN',
        confidence: a.confidence || det.confidence || 0.0,
      };
    })
    .filter(a => {
      if (!searchQuery) return true;
      return a.plate.toLowerCase().includes(searchQuery.toLowerCase());
    });

  const handleANPRExport = () => {
    const headers = ['Timestamp', 'Camera ID', 'License Plate', 'Confidence'];
    const rows = anprAlerts.map(a => [
      new Date(a.timestamp).toLocaleString(),
      a.cam_id,
      a.plate,
      `${(a.confidence * 100).toFixed(0)}%`,
    ]);
    exportToCSV(headers, rows, `anpr_scans_${new Date().toISOString().split('T')[0]}.csv`);
  };

  // ── Vehicle counting view helper ──────────────────────────────────────────
  const vehicleList = [];
  Object.entries(vehicleStats).forEach(([cam_id, camData]) => {
    if (camFilter !== 'all' && cam_id !== camFilter) return;
    Object.entries(camData.by_type || {}).forEach(([vtype, counts]) => {
      vehicleList.push({
        cam_id,
        vehicle_type: vtype,
        in: counts.in || 0,
        out: counts.out || 0,
        last_reset: camData.last_reset_date || '—',
      });
    });
  });

  const handleVehicleExport = () => {
    const headers = ['Camera ID', 'Vehicle Type', 'Entries (IN)', 'Exits (OUT)', 'Last Reset'];
    const rows = vehicleList.map(v => [
      v.cam_id,
      v.vehicle_type,
      v.in,
      v.out,
      v.last_reset,
    ]);
    exportToCSV(headers, rows, `vehicle_counts_${new Date().toISOString().split('T')[0]}.csv`);
  };

  // ── Footfall counting view helper ─────────────────────────────────────────
  const footfallList = [];
  Object.entries(footfallStats).forEach(([cam_id, camData]) => {
    if (camFilter !== 'all' && cam_id !== camFilter) return;
    footfallList.push({
      cam_id,
      in: camData.count_in || 0,
      out: camData.count_out || 0,
      occupancy: camData.occupancy || 0,
      last_reset: camData.last_reset_date || '—',
    });
  });

  const handleFootfallExport = () => {
    const headers = ['Camera ID', 'Entries (IN)', 'Exits (OUT)', 'Current Occupancy', 'Last Reset'];
    const rows = footfallList.map(f => [
      f.cam_id,
      f.in,
      f.out,
      f.occupancy,
      f.last_reset,
    ]);
    exportToCSV(headers, rows, `footfall_counts_${new Date().toISOString().split('T')[0]}.csv`);
  };

  // ── Security Violations view helper ───────────────────────────────────────
  const securityAlerts = filteredAlerts.filter(a =>
    ['intrusion', 'no_go_zone', 'fire_smoke', 'tampering', 'weapon_detection', 'criminal_face', 'animal_detection', 'abandoned_object', 'crowd', 'loitering', 'perimeter'].includes(a.feature)
  );

  const handleSecurityExport = () => {
    const headers = ['Timestamp', 'Camera ID', 'Feature', 'Severity', 'Message'];
    const rows = securityAlerts.map(s => [
      new Date(s.timestamp).toLocaleString(),
      s.cam_id,
      FEATURE_LABELS[s.feature] || s.feature,
      s.severity,
      s.message || '',
    ]);
    exportToCSV(headers, rows, `security_incidents_${new Date().toISOString().split('T')[0]}.csv`);
  };

  return (
    <Box sx={{ display: 'flex', width: '100%', height: 'calc(100vh - 60px)', overflow: 'hidden', bgcolor: 'background.default', mt: '60px' }}>
      
      {/* ══ SIDE PANEL NAVIGATION ══ */}
      <Paper square sx={{ width: 220, bgcolor: 'background.paper', borderRight: '1px solid rgba(255,255,255,0.06)' }}>
        <List sx={{ py: 2 }}>
          <ListItem disablePadding>
            <ListItemButton selected={selectedSection === 'overview'} onClick={() => setSelectedSection('overview')}
              sx={{ py: 1.5, '&.Mui-selected': { bgcolor: 'rgba(0, 255, 204, 0.08)', borderLeft: '4px solid #00ffcc' } }}>
              <ListItemIcon><Analytics sx={{ color: selectedSection === 'overview' ? '#00ffcc' : 'text.secondary' }} /></ListItemIcon>
              <ListItemText primary="Overview Hub" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: selectedSection === 'overview' ? 700 : 500 }} />
            </ListItemButton>
          </ListItem>
          <ListItem disablePadding>
            <ListItemButton selected={selectedSection === 'anpr'} onClick={() => { setSelectedSection('anpr'); setSearchQuery(''); }}
              sx={{ py: 1.5, '&.Mui-selected': { bgcolor: 'rgba(0, 255, 204, 0.08)', borderLeft: '4px solid #00ffcc' } }}>
              <ListItemIcon><DirectionsCar sx={{ color: selectedSection === 'anpr' ? '#00ffcc' : 'text.secondary' }} /></ListItemIcon>
              <ListItemText primary="License Plate (ANPR)" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: selectedSection === 'anpr' ? 700 : 500 }} />
            </ListItemButton>
          </ListItem>
          <ListItem disablePadding>
            <ListItemButton selected={selectedSection === 'vehicles'} onClick={() => setSelectedSection('vehicles')}
              sx={{ py: 1.5, '&.Mui-selected': { bgcolor: 'rgba(0, 255, 204, 0.08)', borderLeft: '4px solid #00ffcc' } }}>
              <ListItemIcon><DirectionsCar sx={{ color: selectedSection === 'vehicles' ? '#00ffcc' : 'text.secondary' }} /></ListItemIcon>
              <ListItemText primary="Vehicle Counting" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: selectedSection === 'vehicles' ? 700 : 500 }} />
            </ListItemButton>
          </ListItem>
          <ListItem disablePadding>
            <ListItemButton selected={selectedSection === 'footfall'} onClick={() => setSelectedSection('footfall')}
              sx={{ py: 1.5, '&.Mui-selected': { bgcolor: 'rgba(0, 255, 204, 0.08)', borderLeft: '4px solid #00ffcc' } }}>
              <ListItemIcon><People sx={{ color: selectedSection === 'footfall' ? '#00ffcc' : 'text.secondary' }} /></ListItemIcon>
              <ListItemText primary="Footfall Counting" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: selectedSection === 'footfall' ? 700 : 500 }} />
            </ListItemButton>
          </ListItem>
          <ListItem disablePadding>
            <ListItemButton selected={selectedSection === 'violations'} onClick={() => setSelectedSection('violations')}
              sx={{ py: 1.5, '&.Mui-selected': { bgcolor: 'rgba(0, 255, 204, 0.08)', borderLeft: '4px solid #00ffcc' } }}>
              <ListItemIcon><Shield sx={{ color: selectedSection === 'violations' ? '#00ffcc' : 'text.secondary' }} /></ListItemIcon>
              <ListItemText primary="Security Incidents" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: selectedSection === 'violations' ? 700 : 500 }} />
            </ListItemButton>
          </ListItem>
        </List>
      </Paper>

      {/* ══ MAIN WORKSPACE ══ */}
      <Box sx={{ flex: 1, p: 3, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>

        {/* ══ HEADER & FILTERS PANEL ══ */}
        <Paper sx={{ p: 2, mb: 3, bgcolor: 'background.paper', borderRadius: 2, border: '1px solid rgba(255,255,255,0.06)' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2} flexWrap="wrap">
            <Typography variant="h6" fontWeight={800} display="flex" alignItems="center">
              <Analytics sx={{ mr: 1, color: '#00ffcc' }} />
              Executive Analytics Dashboard
            </Typography>

            <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
              {/* Camera filter dropdown */}
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel sx={{ fontSize: '0.8rem' }}><Videocam sx={{ mr: 0.5, fontSize: 16, verticalAlign: 'middle' }} /> Camera</InputLabel>
                <Select value={camFilter} label="Camera" onChange={e => setCamFilter(e.target.value)} sx={{ fontSize: '0.8rem', borderRadius: 1.5 }}>
                  <MenuItem value="all">All Cameras</MenuItem>
                  {cameraList.map(cid => <MenuItem key={cid} value={cid}>{cid}</MenuItem>)}
                </Select>
              </FormControl>

              {/* Date selection dropdown */}
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel sx={{ fontSize: '0.8rem' }}><CalendarMonth sx={{ mr: 0.5, fontSize: 16, verticalAlign: 'middle' }} /> Date Range</InputLabel>
                <Select value={dateRange} label="Date Range" onChange={e => setDateRange(e.target.value)} sx={{ fontSize: '0.8rem', borderRadius: 1.5 }}>
                  <MenuItem value="today">Today</MenuItem>
                  <MenuItem value="7days">Last 7 Days</MenuItem>
                  <MenuItem value="custom">Custom Range</MenuItem>
                </Select>
              </FormControl>

              {/* Custom Date Pickers */}
              {dateRange === 'custom' && (
                <Stack direction="row" spacing={1} alignItems="center">
                  <TextField size="small" type="date" label="Start" value={startDate} onChange={e => setStartDate(e.target.value)} InputLabelProps={{ shrink: true }} sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 1 } }} />
                  <Typography variant="caption" color="text.secondary">to</Typography>
                  <TextField size="small" type="date" label="End" value={endDate} onChange={e => setEndDate(e.target.value)} InputLabelProps={{ shrink: true }} sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 1 } }} />
                </Stack>
              )}

              <Button size="small" variant="contained" onClick={fetchData} sx={{ bgcolor: 'rgba(0, 255, 204, 0.1)', color: '#00ffcc', border: '1px solid rgba(0, 255, 204, 0.3)', borderRadius: 1.5, fontWeight: 700, fontSize: '0.72rem', px: 2, py: 0.8, '&:hover': { bgcolor: 'rgba(0, 255, 204, 0.2)' } }}>
                Refresh
              </Button>
            </Stack>
          </Stack>
        </Paper>

        {/* ══ SECTION CONTENT ══ */}

        {/* --- SECTION 1: OVERVIEW HUB --- */}
        {selectedSection === 'overview' && (
          <Grid container spacing={3}>
            {/* KPI Cards */}
            <Grid item xs={12} sm={3}>
              <Card sx={{ borderLeft: '3px solid #ff1744', bgcolor: 'background.paper', borderRadius: 2 }}>
                <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={700}>CRITICAL ALERTS</Typography>
                  <Typography variant="h4" fontWeight={900} sx={{ color: '#ff1744', my: 0.5 }}>
                    {filteredAlerts.filter(a => a.severity === 'CRITICAL').length}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">Fires &amp; violations</Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Card sx={{ borderLeft: '3px solid #00ffcc', bgcolor: 'background.paper', borderRadius: 2 }}>
                <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={700}>ANPR SCAN RATE</Typography>
                  <Typography variant="h4" fontWeight={900} sx={{ color: '#00ffcc', my: 0.5 }}>
                    {filteredAlerts.filter(a => a.feature === 'anpr').length}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">Scanned license plates</Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Card sx={{ borderLeft: '3px solid #00b0ff', bgcolor: 'background.paper', borderRadius: 2 }}>
                <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={700}>TOTAL FOOTFALL</Typography>
                  <Typography variant="h4" fontWeight={900} sx={{ color: '#00b0ff', my: 0.5 }}>
                    {Object.values(footfallStats).reduce((sum, c) => sum + (c.count_in || 0) + (c.count_out || 0), 0)}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">Total crossings logged</Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Card sx={{ borderLeft: '3px solid #ff9100', bgcolor: 'background.paper', borderRadius: 2 }}>
                <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={700}>VEHICLE VOLUME</Typography>
                  <Typography variant="h4" fontWeight={900} sx={{ color: '#ff9100', my: 0.5 }}>
                    {Object.values(vehicleStats).reduce((sum, c) => sum + (c.total?.in || 0) + (c.total?.out || 0), 0)}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">Crossings monitored</Typography>
                </CardContent>
              </Card>
            </Grid>

            {/* Charts row */}
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2, height: '100%' }}>
                <Typography variant="subtitle2" fontWeight={800} mb={2} color="text.secondary">
                  ALERTS BREAKDOWN BY FEATURE
                </Typography>
                <DonutChart data={pieData} colors={FEATURE_COLORS} />
              </Paper>
            </Grid>

            <Grid item xs={12} md={8}>
              <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2, height: '100%' }}>
                <Typography variant="subtitle2" fontWeight={800} mb={2} color="text.secondary">
                  ALERT FREQUENCY TREND
                </Typography>
                <LineChart data={trendData} color="#00ffcc" />
              </Paper>
            </Grid>
          </Grid>
        )}

        {/* --- SECTION 2: ANPR LICENSE PLATES --- */}
        {selectedSection === 'anpr' && (
          <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2.5} flexWrap="wrap" gap={1.5}>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Typography variant="subtitle1" fontWeight={800}>ANPR Scanned Vehicle Logs</Typography>
                <Chip label={`${anprAlerts.length} scans`} size="small" sx={{ bgcolor: 'rgba(0, 255, 204, 0.12)', color: '#00ffcc', fontWeight: 700 }} />
              </Stack>

              <Stack direction="row" spacing={1.5} alignItems="center">
                <TextField
                  size="small"
                  placeholder="Filter by plate..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  InputProps={{ startAdornment: <Search fontSize="small" sx={{ color: 'text.secondary', mr: 1 }} /> }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem', py: 0.8 } }}
                />
                <Button size="small" startIcon={<FileDownload />} onClick={handleANPRExport} variant="outlined" sx={{ borderColor: '#00ffcc55', color: '#00ffcc', fontSize: '0.75rem', px: 2, py: 0.7, '&:hover': { borderColor: '#00ffcc', bgcolor: 'rgba(0, 255, 204, 0.04)' } }}>
                  Export CSV
                </Button>
              </Stack>
            </Stack>

            {anprAlerts.length === 0 ? (
              <Box py={6} textAlign="center"><Typography color="text.secondary">No scanned license plates matching criteria.</Typography></Box>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ borderBottom: '2px solid rgba(255,255,255,0.06)' }}>
                      <TableCell sx={{ fontWeight: 800 }}>Time</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>License Plate</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Confidence</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {anprAlerts.map((a, i) => (
                      <TableRow key={i} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                        <TableCell>{new Date(a.timestamp).toLocaleString()}</TableCell>
                        <TableCell>{a.cam_id}</TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight={800} sx={{ fontFamily: 'monospace', letterSpacing: 0.5, color: '#00ffcc' }}>
                            {a.plate}
                          </Typography>
                        </TableCell>
                        <TableCell>{(a.confidence * 100).toFixed(0)}%</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        )}

        {/* --- SECTION 3: VEHICLE COUNTING --- */}
        {selectedSection === 'vehicles' && (
          <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2.5} flexWrap="wrap" gap={1.5}>
              <Typography variant="subtitle1" fontWeight={800}>Vehicle Traffic Distribution</Typography>
              <Button size="small" startIcon={<FileDownload />} onClick={handleVehicleExport} variant="outlined" sx={{ borderColor: '#00ffcc55', color: '#00ffcc', fontSize: '0.75rem', px: 2, py: 0.7, '&:hover': { borderColor: '#00ffcc', bgcolor: 'rgba(0, 255, 204, 0.04)' } }}>
                Export CSV
              </Button>
            </Stack>

            {vehicleList.length === 0 ? (
              <Box py={6} textAlign="center"><Typography color="text.secondary">No vehicle counts logged yet.</Typography></Box>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ borderBottom: '2px solid rgba(255,255,255,0.06)' }}>
                      <TableCell sx={{ fontWeight: 800 }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Vehicle Type</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Entries (IN)</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Exits (OUT)</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Last Reset</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vehicleList.map((v, i) => (
                      <TableRow key={i} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                        <TableCell>{v.cam_id}</TableCell>
                        <TableCell sx={{ textTransform: 'capitalize', fontWeight: 600 }}>{v.vehicle_type}</TableCell>
                        <TableCell sx={{ color: '#00e676', fontWeight: 700 }}>{v.in}</TableCell>
                        <TableCell sx={{ color: '#ff6d00', fontWeight: 700 }}>{v.out}</TableCell>
                        <TableCell>{v.last_reset}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        )}

        {/* --- SECTION 4: FOOTFALL COUNTING --- */}
        {selectedSection === 'footfall' && (
          <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2.5} flexWrap="wrap" gap={1.5}>
              <Typography variant="subtitle1" fontWeight={800}>Footfall Crossings &amp; Occupancy</Typography>
              <Button size="small" startIcon={<FileDownload />} onClick={handleFootfallExport} variant="outlined" sx={{ borderColor: '#00ffcc55', color: '#00ffcc', fontSize: '0.75rem', px: 2, py: 0.7, '&:hover': { borderColor: '#00ffcc', bgcolor: 'rgba(0, 255, 204, 0.04)' } }}>
                Export CSV
              </Button>
            </Stack>

            {footfallList.length === 0 ? (
              <Box py={6} textAlign="center"><Typography color="text.secondary">No footfall counts logged yet.</Typography></Box>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ borderBottom: '2px solid rgba(255,255,255,0.06)' }}>
                      <TableCell sx={{ fontWeight: 800 }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Entries (IN)</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Exits (OUT)</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Current Occupancy</TableCell>
                      <TableCell sx={{ fontWeight: 800 }}>Last Reset</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {footfallList.map((f, i) => (
                      <TableRow key={i} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                        <TableCell>{f.cam_id}</TableCell>
                        <TableCell sx={{ color: '#00e676', fontWeight: 700 }}>{f.in}</TableCell>
                        <TableCell sx={{ color: '#ff6d00', fontWeight: 700 }}>{f.out}</TableCell>
                        <TableCell sx={{ fontWeight: 700, color: '#00e5ff' }}>{f.occupancy}</TableCell>
                        <TableCell>{f.last_reset}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        )}

        {/* --- SECTION 5: SECURITY INCIDENTS LIST --- */}
        {selectedSection === 'violations' && (
          <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2.5} flexWrap="wrap" gap={1.5}>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Typography variant="subtitle1" fontWeight={800}>Security Violation Incidents</Typography>
                <Chip label={`${securityAlerts.length} alerts`} size="small" sx={{ bgcolor: 'rgba(255, 23, 68, 0.12)', color: '#ff1744', fontWeight: 700 }} />
              </Stack>

              <Button size="small" startIcon={<FileDownload />} onClick={handleSecurityExport} variant="outlined" sx={{ borderColor: '#00ffcc55', color: '#00ffcc', fontSize: '0.75rem', px: 2, py: 0.7, '&:hover': { borderColor: '#00ffcc', bgcolor: 'rgba(0, 255, 204, 0.04)' } }}>
                Export CSV
              </Button>
            </Stack>

            {securityAlerts.length === 0 ? (
              <Box py={6} textAlign="center"><Typography color="text.secondary">No security incidents logged in this timeframe.</Typography></Box>
            ) : (
              <TableContainer sx={{ maxHeight: 'calc(100vh - 350px)' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 800, bgcolor: 'background.paper' }}>Time</TableCell>
                      <TableCell sx={{ fontWeight: 800, bgcolor: 'background.paper' }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 800, bgcolor: 'background.paper' }}>Feature</TableCell>
                      <TableCell sx={{ fontWeight: 800, bgcolor: 'background.paper' }}>Severity</TableCell>
                      <TableCell sx={{ fontWeight: 800, bgcolor: 'background.paper' }}>Incident Message</TableCell>
                      <TableCell sx={{ fontWeight: 800, bgcolor: 'background.paper' }} align="center">Snapshot</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {securityAlerts.map((s, i) => {
                      const sColor = FEATURE_COLORS[s.feature] || '#ff6d00';
                      return (
                        <TableRow key={i} hover>
                          <TableCell>{new Date(s.timestamp).toLocaleString()}</TableCell>
                          <TableCell>{s.cam_id}</TableCell>
                          <TableCell sx={{ fontWeight: 700, color: sColor }}>{FEATURE_LABELS[s.feature] || s.feature}</TableCell>
                          <TableCell>
                            <Chip
                              label={s.severity}
                              size="small"
                              sx={{
                                fontSize: '0.58rem',
                                fontWeight: 800,
                                height: 18,
                                color: s.severity === 'CRITICAL' ? '#ff1744' : s.severity === 'HIGH' ? '#ff6d00' : s.severity === 'MEDIUM' ? '#ffd600' : '#00b0ff',
                                bgcolor: s.severity === 'CRITICAL' ? '#ff174418' : s.severity === 'HIGH' ? '#ff6d0018' : s.severity === 'MEDIUM' ? '#ffd60018' : '#00b0ff18',
                                border: `1px solid ${s.severity === 'CRITICAL' ? '#ff174455' : s.severity === 'HIGH' ? '#ff6d0055' : s.severity === 'MEDIUM' ? '#ffd60055' : '#00b0ff55'}`,
                              }}
                            />
                          </TableCell>
                          <TableCell sx={{ fontSize: '0.8rem' }}>{s.message}</TableCell>
                          <TableCell align="center">
                            {s.snapshot_path ? (
                              <IconButton
                                size="small"
                                onClick={() => setZoomImg(`${API}/clips/${s.snapshot_path}`)}
                                sx={{ color: '#00ffcc', '&:hover': { bgcolor: 'rgba(0, 255, 204, 0.1)' } }}
                              >
                                <OpenInNew fontSize="small" />
                              </IconButton>
                            ) : (
                              <Typography variant="caption" color="text.disabled">—</Typography>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        )}

      </Box>

      {/* ══ DIALOG FOR IMAGE SNAPSHOT ZOOM ══ */}
      <Dialog open={!!zoomImg} onClose={() => setZoomImg(null)} maxWidth="lg">
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, bgcolor: 'background.paper' }}>
          <Typography variant="subtitle1" fontWeight={800}>Annotated Alert Snapshot</Typography>
          <IconButton size="small" onClick={() => setZoomImg(null)} sx={{ color: 'text.secondary' }}>
            <Close />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 0, bgcolor: '#000', display: 'flex', justifyContent: 'center' }}>
          {zoomImg && (
            <img src={zoomImg} alt="Alert Zoom" style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain' }} />
          )}
        </DialogContent>
        <DialogActions sx={{ p: 1.5, bgcolor: 'background.paper' }}>
          <Button onClick={() => setZoomImg(null)} size="small" sx={{ color: '#00ffcc', fontWeight: 700 }}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
