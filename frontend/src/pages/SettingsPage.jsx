import React, { useRef, useState, useCallback, useEffect } from 'react';
import { useTheme } from '@mui/material/styles';
import {
  Box, Typography, Stack, Paper, Switch, Button, Chip,
  Divider, Alert, Snackbar, IconButton, Tooltip, Dialog,
  DialogTitle, DialogContent, DialogActions, TextField,
  List, ListItem, ListItemButton, ListItemText, Slider,
} from '@mui/material';
import {
  Draw, CheckCircle, Undo, PlayArrow, Settings,
  WarningAmber, HighlightOff, Cancel, Refresh, Warning,
  Add, Delete, Videocam, AccessTime, Person, Groups,
  Timeline, Shield, CameraAlt, DirectionsWalk, Visibility,
} from '@mui/icons-material';

const API = 'http://localhost:5050';
const W = 1280, H = 720;

const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

const ALL_FEATURES = [
  { key: 'no_go_zone',          label: 'No-Go Zone',           desc: 'CRITICAL: Alert when anyone enters a danger area.',               color: '#ff1744', shape: 'polygon', sev: 'CRITICAL', needsDraw: true,  icon: Shield        },
  { key: 'intrusion',           label: 'Intrusion Zone',       desc: 'Alert when anyone enters the restricted zone.',                    color: '#ff6d00', shape: 'polygon', sev: 'HIGH',     needsDraw: true,  icon: Warning       },
  { key: 'loitering',           label: 'Loitering',            desc: 'Alert if person lingers in zone beyond dwell time.',              color: '#ffd600', shape: 'polygon', sev: 'MEDIUM',   needsDraw: true,  icon: DirectionsWalk },
  { key: 'missing_person',      label: 'Person Missing',       desc: 'Alert when expected persons absent longer than threshold.',        color: '#e040fb', shape: 'polygon', sev: 'HIGH',     needsDraw: true,  icon: Person        },
  { key: 'crowd',               label: 'Crowd Estimation',     desc: 'Real-time head count. Alert when crowd limit is exceeded.',        color: '#76ff03', shape: 'polygon', sev: 'MEDIUM',   needsDraw: true,  icon: Groups        },
  { key: 'personal_monitoring', label: 'Personal Monitor',     desc: 'Track staff presence at a designated post.',                       color: '#00e5ff', shape: 'polygon', sev: 'MEDIUM',   needsDraw: true,  icon: Visibility    },
  { key: 'footfall',            label: 'Footfall Count',       desc: 'Count people crossing a line: IN / OUT / Net Occupancy.',         color: '#00b0ff', shape: 'line',    sev: 'LOW',      needsDraw: true,  icon: Timeline      },
  { key: 'perimeter',           label: 'Perimeter Guard',      desc: 'Tripwire alert when someone crosses the boundary inward.',        color: '#ff4081', shape: 'line',    sev: 'HIGH',     needsDraw: true,  icon: Shield        },
  { key: 'tampering',           label: 'Camera Tampering',     desc: 'Detects occlusion, spray, blur or camera repositioning.',         color: '#b388ff', shape: null,      sev: 'HIGH',     needsDraw: false, icon: CameraAlt     },
  { key: 'fire_smoke',          label: 'Fire & Smoke',         desc: 'Whole-frame scan — no zone needed.',                               color: '#ff3d00', shape: null,      sev: 'CRITICAL', needsDraw: false, icon: Warning       },
  { key: 'weapon_detection',    label: 'Weapon Detection',     desc: 'Detects guns, knives & firearms in real-time.',                   color: '#ff1744', shape: null,      sev: 'CRITICAL', needsDraw: false, icon: Warning       },
  { key: 'criminal_face',       label: 'Criminal Face ID',     desc: 'Matches faces against the criminal watchlist.',                   color: '#ff6d00', shape: null,      sev: 'CRITICAL', needsDraw: false, icon: Person        },
];

const SEV_COLOR  = { CRITICAL: '#ff1744', HIGH: '#ff6d00', MEDIUM: '#ffd600', LOW: '#00b0ff' };

// Features that support drawing MULTIPLE zones
const MULTI_ZONE_KEYS = new Set(['intrusion', 'no_go_zone', 'loitering', 'crowd', 'missing_person', 'perimeter']);
const FOOTFALL_VIEWS = [
  { key: 'left_right', label: 'Left ↔ Right',  desc: 'Side-view crossing line' },
  { key: 'overhead',   label: 'Overhead',       desc: 'Top-down head count'     },
  { key: 'angled',     label: 'Angled',         desc: 'Right-side position track' },
];

// ── Default feature-specific configs ──────────────────────────────────────
function defaultFeatureConfig() {
  return {
    no_go_zone:          { schedule: { enabled: false, days: [0,1,2,3,4,5,6], start: '00:00', end: '23:59' } },
    intrusion:           { schedule: { enabled: false, days: [0,1,2,3,4,5,6], start: '00:00', end: '23:59' } },
    loitering:           { dwell_seconds: 15, schedule: { enabled: false, days: [0,1,2,3,4,5,6], start: '22:00', end: '06:00' } },
    missing_person:      { timeout_minutes: 1, target_count: 1 },
    crowd:               { max_threshold: 5 },
    personal_monitoring: { timeout_seconds: 30 },
    footfall:            { view_type: 'left_right', invert: false },
    perimeter:           { schedule: { enabled: false, days: [0,1,2,3,4,5,6], start: '00:00', end: '23:59' } },
    tampering:           { sensitivity: 60 },
    fire_smoke:          {},
    weapon_detection:    {},
    criminal_face:       {},
    full_frame:          false,
  };
}

function initState() {
  const s = {};
  ALL_FEATURES.forEach(f => {
    s[f.key] = {
      enabled: false, points: [], configured: false,
      ...(MULTI_ZONE_KEYS.has(f.key) ? { multiZone: false, extraZones: [] } : {}),
    };
  });
  return s;
}

function loadCameraConfigToState(cam) {
  const s = {};
  ALL_FEATURES.forEach(f => {
    const isEnabled = cam.features ? cam.features.includes(f.key) : false;
    let points = [], isConfigured = false, extraZones = [];

    if (f.key === 'footfall' && cam.counting_line) {
      points = cam.counting_line; isConfigured = true;
    } else if (f.key === 'perimeter') {
      if (cam.perimeter_line) { points = cam.perimeter_line; isConfigured = true; }
      // Extra perimeter lines stored as zones with type='perimeter'
      if (cam.zones) {
        extraZones = cam.zones
          .filter(z => z.type === 'perimeter')
          .map((z, i) => ({ id: z.id || `zone_perimeter_extra_${i}`, points: z.line || [], configured: (z.line || []).length >= 2 }));
      }
    } else if (cam.zones) {
      const allOfType = cam.zones.filter(z => z.type === f.key);
      if (allOfType.length > 0) {
        const first = allOfType[0];
        points = first.polygon || first.line || [];
        isConfigured = points.length > 0;
        extraZones = allOfType.slice(1).map((z, i) => ({
          id: z.id || `zone_${f.key}_extra_${i}`,
          points: z.polygon || z.line || [],
          configured: (z.polygon || z.line || []).length >= (f.shape === 'line' ? 2 : 3),
        }));
      }
    }

    s[f.key] = {
      enabled: isEnabled, points, configured: isConfigured,
      ...(MULTI_ZONE_KEYS.has(f.key) ? { multiZone: extraZones.length > 0, extraZones } : {}),
    };
  });
  return s;
}

function loadExtraConfig(cam) {
  const d = defaultFeatureConfig();
  // Loitering
  if (cam.loitering_timeout_seconds) d.loitering.dwell_seconds = cam.loitering_timeout_seconds;
  // Crowd
  if (cam.crowd_threshold)           d.crowd.max_threshold = cam.crowd_threshold;
  // Missing person
  if (cam.missing_person_timeout_seconds) d.missing_person.timeout_minutes = Math.max(1, Math.round(cam.missing_person_timeout_seconds / 60));
  if (cam.missing_person_target_count)    d.missing_person.target_count = cam.missing_person_target_count;
  // Footfall
  if (cam.footfall_view_type)  d.footfall.view_type = cam.footfall_view_type;
  if (cam.footfall_invert !== undefined) d.footfall.invert = cam.footfall_invert;
  // Tampering
  if (cam.tampering_sensitivity !== undefined) d.tampering.sensitivity = cam.tampering_sensitivity;
  // Personal monitoring
  if (cam.personal_monitoring_timeout_seconds) d.personal_monitoring.timeout_seconds = cam.personal_monitoring_timeout_seconds;
  // Camera-level feature schedules
  if (cam.loitering_schedule)           d.loitering.schedule           = cam.loitering_schedule;
  if (cam.crowd_schedule)               d.crowd.schedule               = cam.crowd_schedule;
  if (cam.missing_person_schedule)      d.missing_person.schedule      = cam.missing_person_schedule;
  if (cam.footfall_schedule)            d.footfall.schedule            = cam.footfall_schedule;
  if (cam.tampering_schedule)           d.tampering.schedule           = cam.tampering_schedule;
  if (cam.personal_monitoring_schedule) d.personal_monitoring.schedule = cam.personal_monitoring_schedule;
  if (cam.perimeter_schedule)           d.perimeter.schedule           = cam.perimeter_schedule;
  // Zone-level schedules (intrusion, no_go_zone)
  if (cam.zones) {
    cam.zones.forEach(z => {
      if (z.schedule && d[z.type]?.schedule) {
        d[z.type].schedule = { ...d[z.type].schedule, ...z.schedule };
      }
    });
  }
  // Full-frame
  if (cam.full_frame_analytics !== undefined) d.full_frame = cam.full_frame_analytics;
  return d;
}


function canvasXY(e, canvas) {
  const r = canvas.getBoundingClientRect();
  return [
    Math.round((e.clientX - r.left) * (W / r.width)),
    Math.round((e.clientY - r.top)  * (H / r.height)),
  ];
}

// ── Reusable schedule config block ─────────────────────────────────────────
function SchedulePanel({ value, onChange, accentColor }) {
  const sched = value || { enabled: false, days: [0,1,2,3,4,5,6], start: '00:00', end: '23:59' };
  const toggleDay = (d) => {
    const next = sched.days.includes(d) ? sched.days.filter(x => x !== d) : [...sched.days, d].sort();
    onChange({ ...sched, days: next });
  };
  return (
    <Box sx={{ mt: 1, p: 1, borderRadius: 1, bgcolor: 'rgba(0,0,0,0.3)', border: `1px solid ${accentColor}22` }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={sched.enabled ? 1 : 0}>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <AccessTime sx={{ fontSize: 11, color: accentColor }} />
          <Typography variant="caption" sx={{ fontSize: '0.62rem', color: accentColor, fontWeight: 600 }}>
            Time Schedule
          </Typography>
        </Stack>
        <Switch size="small" checked={sched.enabled}
          onChange={e => onChange({ ...sched, enabled: e.target.checked })}
          sx={{ '& .MuiSwitch-thumb': { width: 10, height: 10, bgcolor: sched.enabled ? accentColor : '#555' } }} />
      </Stack>
      {sched.enabled && (
        <>
          <Stack direction="row" spacing={0.5} mb={0.75} flexWrap="wrap" gap={0.25}>
            {DAYS.map((d, i) => (
              <Box key={i} onClick={() => toggleDay(i)}
                sx={{
                  px: 0.75, py: 0.2, borderRadius: 0.5, cursor: 'pointer', fontSize: '0.58rem',
                  fontWeight: 700, userSelect: 'none',
                  bgcolor: sched.days.includes(i) ? accentColor + '33' : 'rgba(255,255,255,0.05)',
                  color:   sched.days.includes(i) ? accentColor : 'rgba(255,255,255,0.35)',
                  border: `1px solid ${sched.days.includes(i) ? accentColor + '66' : 'rgba(255,255,255,0.07)'}`,
                  transition: 'all 0.15s',
                }}>
                {d}
              </Box>
            ))}
          </Stack>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary', minWidth: 22 }}>From</Typography>
            <input type="time" value={sched.start}
              onChange={e => onChange({ ...sched, start: e.target.value })}
              style={{ background: 'transparent', border: `1px solid ${accentColor}44`, borderRadius: 4,
                color: 'inherit', fontSize: '0.65rem', padding: '2px 4px', width: 72 }} />
            <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary', minWidth: 14 }}>To</Typography>
            <input type="time" value={sched.end}
              onChange={e => onChange({ ...sched, end: e.target.value })}
              style={{ background: 'transparent', border: `1px solid ${accentColor}44`, borderRadius: 4,
                color: 'inherit', fontSize: '0.65rem', padding: '2px 4px', width: 72 }} />
          </Stack>
        </>
      )}
    </Box>
  );
}

// ── Extra config panels per feature ────────────────────────────────────────
function FeatureExtraConfig({ featureKey, config, onChange, accentColor }) {

  const upd = (patch) => onChange({ ...config, ...patch });
  const updSched = (s) => onChange({ ...config, schedule: s });

  if (featureKey === 'loitering') return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={0.75} mb={0.5}>
        <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem', whiteSpace: 'nowrap' }}>Dwell Time:</Typography>
        <TextField type="number" size="small"
          value={Math.round((config.dwell_seconds ?? 60) / 60)}
          onChange={e => upd({ dwell_seconds: Math.max(60, Math.min(3600, (parseInt(e.target.value)||1) * 60)) })}
          inputProps={{ min: 1, max: 60, style: { color: 'inherit', fontSize: '0.68rem', padding: '2px 4px', width: 40, textAlign: 'center' } }}
          sx={{ width: 56, '& .MuiOutlinedInput-root fieldset': { borderColor: accentColor + '44' }, '& .MuiOutlinedInput-root:hover fieldset': { borderColor: accentColor } }} />
        <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.62rem' }}>min</Typography>
      </Stack>
      <SchedulePanel value={config.schedule} onChange={updSched} accentColor={accentColor} />
    </Box>
  );

  if (featureKey === 'no_go_zone' || featureKey === 'intrusion') return (
    <SchedulePanel value={config.schedule} onChange={updSched} accentColor={accentColor} />
  );

  if (featureKey === 'perimeter') return (
    <SchedulePanel value={config.schedule} onChange={updSched} accentColor={accentColor} />
  );

  if (featureKey === 'tampering') return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.25}>
        <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem' }}>Sensitivity</Typography>
        <Typography variant="caption" sx={{ color: 'text.primary', fontSize: '0.62rem', fontWeight: 700 }}>
          {config.sensitivity ?? 60}%
        </Typography>
      </Stack>
      <Slider
        size="small"
        value={config.sensitivity ?? 60}
        onChange={(_, v) => upd({ sensitivity: v })}
        min={10} max={100} step={5}
        sx={{
          color: accentColor, height: 3, py: 0.5,
          '& .MuiSlider-thumb': { width: 10, height: 10 },
          '& .MuiSlider-track': { border: 'none' },
        }}
      />
      <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.57rem' }}>
        High = sensitive to minor shifts · Low = only major occlusions
      </Typography>
    </Box>
  );

  if (featureKey === 'missing_person') return (
    <Box>
      <Stack direction="row" spacing={1} mb={0.75}>
        {/* Timeout */}
        <Box sx={{ flex: 1 }}>
          <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem', display: 'block', mb: 0.25 }}>
            Alert after
          </Typography>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <TextField type="number" size="small"
              value={config.timeout_minutes ?? 1}
              onChange={e => upd({ timeout_minutes: Math.max(1, Math.min(120, parseInt(e.target.value)||1)) })}
              inputProps={{ min: 1, max: 120, style: { color: 'inherit', fontSize: '0.68rem', padding: '2px 4px', width: 36, textAlign: 'center' } }}
              sx={{ width: 52, '& .MuiOutlinedInput-root fieldset': { borderColor: accentColor + '44' }, '& .MuiOutlinedInput-root:hover fieldset': { borderColor: accentColor } }} />
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.62rem' }}>min</Typography>
          </Stack>
        </Box>
        {/* Target count */}
        <Box sx={{ flex: 1 }}>
          <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem', display: 'block', mb: 0.25 }}>
            Target count
          </Typography>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <TextField type="number" size="small"
              value={config.target_count ?? 1}
              onChange={e => upd({ target_count: Math.max(1, Math.min(10, parseInt(e.target.value)||1)) })}
              inputProps={{ min: 1, max: 10, style: { color: 'inherit', fontSize: '0.68rem', padding: '2px 4px', width: 36, textAlign: 'center' } }}
              sx={{ width: 52, '& .MuiOutlinedInput-root fieldset': { borderColor: accentColor + '44' }, '& .MuiOutlinedInput-root:hover fieldset': { borderColor: accentColor } }} />
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.62rem' }}>persons</Typography>
          </Stack>
        </Box>
      </Stack>
      {/* Dynamic tracking slots */}
      {(config.target_count ?? 1) > 1 && (
        <Box sx={{ mt: 0.5, p: 0.75, borderRadius: 1, bgcolor: 'rgba(0,0,0,0.3)', border: `1px solid ${accentColor}22` }}>
          <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.58rem', fontWeight: 600, display: 'block', mb: 0.5 }}>
            Tracking Slots ({config.target_count} expected)
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={0.5}>
            {Array.from({ length: config.target_count }, (_, i) => (
              <Box key={i} sx={{
                display: 'flex', alignItems: 'center', gap: 0.4,
                px: 0.75, py: 0.35, borderRadius: 1,
                bgcolor: accentColor + '12', border: `1px solid ${accentColor}33`,
              }}>
                <Box sx={{ width: 5, height: 5, borderRadius: '50%', bgcolor: accentColor, opacity: 0.7,
                  animation: 'pulse 2s infinite', '@keyframes pulse': { '0%,100%': { opacity: 0.7 }, '50%': { opacity: 0.2 } } }} />
                <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.57rem', fontWeight: 700 }}>
                  P{i + 1}
                </Typography>
                <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.55rem' }}>
                  monitoring
                </Typography>
              </Box>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );

  if (featureKey === 'crowd') return (
    <Stack direction="row" alignItems="center" spacing={0.75}>
      <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem', whiteSpace: 'nowrap' }}>Max threshold:</Typography>
      <TextField type="number" size="small"
        value={config.max_threshold ?? 5}
        onChange={e => upd({ max_threshold: Math.max(1, Math.min(500, parseInt(e.target.value)||5)) })}
        inputProps={{ min: 1, max: 500, style: { color: 'inherit', fontSize: '0.68rem', padding: '2px 4px', width: 40, textAlign: 'center' } }}
        sx={{ width: 60, '& .MuiOutlinedInput-root fieldset': { borderColor: accentColor + '44' }, '& .MuiOutlinedInput-root:hover fieldset': { borderColor: accentColor } }} />
      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.62rem' }}>persons</Typography>
    </Stack>
  );

  if (featureKey === 'footfall') return (
    <Box>
      <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem', display: 'block', mb: 0.5 }}>
        Camera View Type
      </Typography>
      <Stack direction="column" spacing={0.4}>
        {FOOTFALL_VIEWS.map(v => (
          <Box key={v.key} onClick={() => upd({ view_type: v.key })}
            sx={{
              px: 1, py: 0.5, borderRadius: 1, cursor: 'pointer',
              border: `1px solid ${(config.view_type ?? 'left_right') === v.key ? accentColor + '77' : 'rgba(255,255,255,0.07)'}`,
              bgcolor: (config.view_type ?? 'left_right') === v.key ? accentColor + '18' : 'rgba(255,255,255,0.02)',
              display: 'flex', alignItems: 'center', gap: 0.75,
              transition: 'all 0.15s',
            }}>
            <Box sx={{
              width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
              bgcolor: (config.view_type ?? 'left_right') === v.key ? accentColor : 'rgba(255,255,255,0.2)',
            }} />
            <Box>
              <Typography variant="caption" sx={{ color: (config.view_type ?? 'left_right') === v.key ? accentColor : 'rgba(255,255,255,0.6)', fontSize: '0.62rem', fontWeight: 600, display: 'block' }}>
                {v.label}
              </Typography>
              <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.56rem' }}>
                {v.desc}
              </Typography>
            </Box>
          </Box>
        ))}
      </Stack>
      <Box sx={{ mt: 1, p: 1, borderRadius: 1, bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box>
          <Typography variant="caption" sx={{ color: 'text.primary', fontSize: '0.62rem', fontWeight: 600, display: 'block' }}>
            Invert Direction
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.55rem' }}>
            Swaps the IN and OUT counting logic.
          </Typography>
        </Box>
        <Switch size="small" checked={!!config.invert} onChange={e => upd({ invert: e.target.checked })}
          sx={{ '& .MuiSwitch-thumb': { bgcolor: config.invert ? accentColor : '#444' }, '& .Mui-checked + .MuiSwitch-track': { bgcolor: accentColor + '55' } }} />
      </Box>
    </Box>
  );

  if (featureKey === 'personal_monitoring') return (
    <Stack direction="row" alignItems="center" spacing={0.75}>
      <Typography variant="caption" sx={{ color: accentColor, fontSize: '0.62rem', whiteSpace: 'nowrap' }}>Absence alert:</Typography>
      <TextField type="number" size="small"
        value={config.timeout_seconds ?? 30}
        onChange={e => upd({ timeout_seconds: Math.max(10, Math.min(3600, parseInt(e.target.value)||30)) })}
        inputProps={{ min: 10, max: 3600, style: { color: 'inherit', fontSize: '0.68rem', padding: '2px 4px', width: 40, textAlign: 'center' } }}
        sx={{ width: 60, '& .MuiOutlinedInput-root fieldset': { borderColor: accentColor + '44' }, '& .MuiOutlinedInput-root:hover fieldset': { borderColor: accentColor } }} />
      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.62rem' }}>sec</Typography>
    </Stack>
  );

  return null;
}

export default function SettingsPage() {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const canvasRef  = useRef(null);
  const mouseXY    = useRef([0, 0]);
  const rafRef     = useRef(null);

  const [cameras,       setCameras]       = useState([]);
  const [selectedCam,   setSelectedCam]   = useState(null);
  const [camName,       setCamName]       = useState('');
  const [camSource,     setCamSource]     = useState('');
  const [features,      setFeatures]      = useState(initState);
  const [extraConfig,   setExtraConfig]   = useState(defaultFeatureConfig);
  const [fullFrame,     setFullFrame]     = useState(false);
  const [activeDrawing, setActiveDrawing] = useState(null);
  const [drawPts,       setDrawPts]       = useState([]);
  const [snack,         setSnack]         = useState({ open: false, msg: '', sev: 'success' });
  const [applying,      setApplying]      = useState(false);
  const [diagOpen,      setDiagOpen]      = useState(false);

  const [addDialogOpen,  setAddDialogOpen]  = useState(false);
  const [newCamName,     setNewCamName]     = useState('');
  const [newCamSource,   setNewCamSource]   = useState('');
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [camToDelete,       setCamToDelete]       = useState(null);

  const activeFeat = ALL_FEATURES.find(f => f.key === activeDrawing);

  const updExtraConfig = (key, patch) =>
    setExtraConfig(prev => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  // ── Fetch cameras ─────────────────────────────────────────────────────────
  const fetchCameras = useCallback(async (selectId = null) => {
    try {
      const res = await fetch(`${API}/api/cameras`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCameras(data);
      if (data.length > 0) {
        let toSelect = data[0];
        if (selectId) { const m = data.find(c => c.id === selectId); if (m) toSelect = m; }
        selectCamera(toSelect);
      } else { setSelectedCam(null); }
    } catch { toast('Failed to load cameras list.', 'error'); }
  }, []);

  useEffect(() => { fetchCameras(); }, [fetchCameras]);

  const selectCamera = (cam) => {
    cancelDraw();
    setSelectedCam(cam);
    setCamName(cam.name || '');
    setCamSource(cam.source || '');
    setFeatures(loadCameraConfigToState(cam));
    setExtraConfig(loadExtraConfig(cam));
    setFullFrame(!!cam.full_frame_analytics);
  };

  // ── Canvas render loop ────────────────────────────────────────────────────
  // NOTE: Do NOT draw saved/configured zones here — the AI engine already
  // annotates them onto the video stream. Drawing them again on the canvas
  // creates a visible duplicate. Only draw the zone currently being drawn.
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    // Only draw the actively-in-progress zone (not saved ones)
    if (activeDrawing && drawPts.length > 0 && activeFeat)
      drawInProgress(ctx, drawPts, activeFeat.color, activeFeat.shape, mouseXY.current);
    rafRef.current = requestAnimationFrame(renderCanvas);
  }, [activeDrawing, drawPts, activeFeat]);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(renderCanvas);
    return () => cancelAnimationFrame(rafRef.current);
  }, [renderCanvas]);

  // ── Canvas drawing helpers ────────────────────────────────────────────────
  function drawBorderOnly(ctx, pts, color, shape, label) {
    if (!pts.length) return;
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    if (shape === 'polygon' && pts.length >= 3) ctx.closePath();
    ctx.stroke();
    pts.forEach(([x, y]) => { ctx.beginPath(); ctx.fillStyle = color; ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill(); });
    if (pts.length > 0) {
      const [bx, by] = pts.reduce((a, p) => [Math.min(a[0], p[0]), Math.min(a[1], p[1])], [W, H]);
      ctx.font = 'bold 11px Inter, sans-serif';
      const tw = ctx.measureText(label).width, bw = tw + 10, bh = 18;
      const lx = Math.min(bx, W - bw - 4), ly = Math.max(by - 22, 4);
      ctx.fillStyle = color + 'dd'; ctx.beginPath(); ctx.roundRect(lx, ly, bw, bh, 4); ctx.fill();
      ctx.fillStyle = '#000'; ctx.textBaseline = 'middle'; ctx.fillText(label, lx + 5, ly + bh / 2);
    }
    ctx.restore();
  }

  function drawInProgress(ctx, pts, color, shape, mp) {
    if (!pts.length) return;
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.fillStyle = color + '0c'; ctx.setLineDash([8, 5]);
    ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    if (mp && mp[0]) ctx.lineTo(mp[0], mp[1]);
    if (shape === 'polygon' && pts.length >= 2) { ctx.closePath(); ctx.fill(); }
    ctx.stroke();
    if (shape === 'polygon' && pts.length >= 2 && mp && mp[0]) {
      ctx.beginPath(); ctx.setLineDash([4, 8]); ctx.globalAlpha = 0.35;
      ctx.moveTo(mp[0], mp[1]); ctx.lineTo(pts[0][0], pts[0][1]);
      ctx.stroke(); ctx.globalAlpha = 1;
    }
    ctx.setLineDash([]);
    pts.forEach(([x, y], i) => {
      ctx.beginPath(); ctx.fillStyle = '#fff'; ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.fillStyle = color;  ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
      ctx.font = 'bold 9px Inter'; ctx.fillStyle = '#fff';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(i + 1, x, y);
    });
    ctx.restore();
  }

  // ── Drawing interactions ──────────────────────────────────────────────────
  const onMouseMove = useCallback((e) => {
    if (!activeDrawing || !canvasRef.current) return;
    mouseXY.current = canvasXY(e, canvasRef.current);
  }, [activeDrawing]);

  const onClick = useCallback((e) => {
    if (!activeDrawing || !activeFeat) return;
    const pt = canvasXY(e, canvasRef.current);
    const next = [...drawPts, pt];
    setDrawPts(next);
    if (activeFeat.shape === 'line' && next.length === 2) finishDraw(next);
  }, [activeDrawing, activeFeat, drawPts]);

  const onDblClick = useCallback((e) => {
    if (!activeDrawing || activeFeat?.shape !== 'polygon' || drawPts.length < 3) return;
    e.preventDefault(); finishDraw(drawPts);
  }, [activeDrawing, activeFeat, drawPts]);

  // drawingExtra=true means we are adding an EXTRA zone (not replacing the primary)
  const [drawingExtra, setDrawingExtra] = React.useState(false);

  const finishDraw = (pts) => {
    const key = activeDrawing;
    const feat = ALL_FEATURES.find(f => f.key === key);
    if (drawingExtra && MULTI_ZONE_KEYS.has(key)) {
      // Append a new extra zone
      const newId = `zone_${key}_${Date.now()}`;
      setFeatures(prev => ({
        ...prev,
        [key]: { ...prev[key], extraZones: [...(prev[key].extraZones || []), { id: newId, points: pts, configured: true }] },
      }));
      toast(`✔ Zone ${(features[key].extraZones?.length || 0) + 2} saved: ${feat?.label}`, 'success');
    } else {
      setFeatures(prev => ({ ...prev, [key]: { ...prev[key], points: pts, configured: true } }));
      toast(`✔ Zone saved: ${feat?.label}`, 'success');
    }
    setActiveDrawing(null); setDrawPts([]); setDrawingExtra(false); mouseXY.current = [0, 0];
  };
  const cancelDraw = () => { setActiveDrawing(null); setDrawPts([]); setDrawingExtra(false); mouseXY.current = [0, 0]; };
  const undoPt     = () => setDrawPts(p => p.slice(0, -1));
  const startDraw  = (key, extra = false) => { setActiveDrawing(key); setDrawingExtra(extra); setDrawPts([]); mouseXY.current = [0, 0]; };
  const clearZone  = (key) => {
    setFeatures(prev => ({ ...prev, [key]: { ...prev[key], points: [], configured: false } }));
    if (activeDrawing === key) cancelDraw();
  };
  const clearExtraZone = (key, zoneId) => {
    setFeatures(prev => ({
      ...prev,
      [key]: { ...prev[key], extraZones: (prev[key].extraZones || []).filter(z => z.id !== zoneId) },
    }));
  };
  const toggleMultiZone = (key) => {
    setFeatures(prev => ({ ...prev, [key]: { ...prev[key], multiZone: !prev[key].multiZone } }));
  };
  const toggleFeat = (key) => {
    setFeatures(prev => {
      const isCurrentlyOn = prev[key].enabled;
      if (isCurrentlyOn) {
        if (activeDrawing === key) cancelDraw();
        return { ...prev, [key]: { enabled: false, points: [], configured: false, ...(MULTI_ZONE_KEYS.has(key) ? { multiZone: false, extraZones: [] } : {}) } };
      } else {
        return { ...prev, [key]: { ...prev[key], enabled: true } };
      }
    });
  };
  const toast = (msg, sev = 'success') => setSnack({ open: true, msg, sev });

  // ── Save config ───────────────────────────────────────────────────────────
  const handleApply = async () => {
    if (!selectedCam) return;
    setApplying(true);
    const enabledKeys = ALL_FEATURES.filter(f => features[f.key].enabled).map(f => f.key);

    // Build zones array — includes primary zone + all extra zones for multi-zone features
    const zones = [];
    ALL_FEATURES.filter(f => features[f.key].enabled && f.needsDraw && f.key !== 'footfall').forEach(f => {
      const st = features[f.key];
      const ec = extraConfig[f.key] || {};
      const zoneBase = {
        alert_on_intrusion: f.key === 'intrusion',
        alert_on_no_go:     f.key === 'no_go_zone',
        alert_on_loitering: f.key === 'loitering',
        alert_on_crowd:     f.key === 'crowd',
        alert_on_missing:   f.key === 'missing_person',
        alert_on_personal:  f.key === 'personal_monitoring',
        ...(ec.schedule ? { schedule: ec.schedule } : {}),
        ...(f.key === 'loitering' && ec.dwell_seconds ? { dwell_seconds: ec.dwell_seconds } : {}),
      };
      // Primary zone
      if (st.configured) {
        zones.push({
          id: `zone_${f.key}`, name: `${f.label} 1`, type: f.key, shape: f.shape,
          polygon: f.shape === 'polygon' ? st.points : undefined,
          line:    f.shape === 'line'    ? st.points : undefined,
          ...zoneBase,
        });
      }
      // Extra zones (multi-zone mode)
      if (MULTI_ZONE_KEYS.has(f.key) && st.extraZones?.length > 0) {
        st.extraZones.filter(ez => ez.configured).forEach((ez, i) => {
          zones.push({
            id: ez.id, name: `${f.label} ${i + 2}`, type: f.key, shape: f.shape,
            polygon: f.shape === 'polygon' ? ez.points : undefined,
            line:    f.shape === 'line'    ? ez.points : undefined,
            ...zoneBase,
          });
        });
      }
    });

    const ec = extraConfig;
    const payload = {
      name:   camName,
      source: camSource,
      features: enabledKeys,
      zones,
      counting_line:  features.footfall.configured  ? features.footfall.points  : null,
      // For perimeter: primary zone always goes to perimeter_line for AI engine compat
      perimeter_line: features.perimeter.configured ? features.perimeter.points : null,
      // Feature-level settings
      full_frame_analytics:              fullFrame,
      loitering_timeout_seconds:         ec.loitering?.dwell_seconds ?? 15,
      crowd_threshold:                   ec.crowd?.max_threshold ?? 5,
      missing_person_timeout_seconds:    (ec.missing_person?.timeout_minutes ?? 1) * 60,
      missing_person_target_count:       ec.missing_person?.target_count ?? 1,
      footfall_view_type:                ec.footfall?.view_type ?? 'left_right',
      footfall_invert:                   ec.footfall?.invert ?? false,
      tampering_sensitivity:             ec.tampering?.sensitivity ?? 60,
      personal_monitoring_timeout_seconds: ec.personal_monitoring?.timeout_seconds ?? 30,
      // Feature-level schedules (day+time windows)
      loitering_schedule:            ec.loitering?.schedule            ?? null,
      crowd_schedule:                ec.crowd?.schedule                ?? null,
      missing_person_schedule:       ec.missing_person?.schedule       ?? null,
      footfall_schedule:             ec.footfall?.schedule             ?? null,
      tampering_schedule:            ec.tampering?.schedule            ?? null,
      personal_monitoring_schedule:  ec.personal_monitoring?.schedule  ?? null,
      perimeter_schedule:            ec.perimeter?.schedule            ?? null,
    };

    try {
      const res = await fetch(`${API}/api/cameras/${selectedCam.id}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast('✅ Settings applied — AI engine reloads in ~5s', 'success');
      await fetchCameras(selectedCam.id);
    } catch (err) {
      toast(`Error: ${err.message}`, 'error');
    } finally { setApplying(false); }
  };

  // ── Add / Delete cameras ─────────────────────────────────────────────────
  const handleAddCamera = async () => {
    if (!newCamName.trim() || !newCamSource.trim()) { toast('Enter name and source URL.', 'warning'); return; }
    try {
      const res = await fetch(`${API}/api/cameras`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newCamName, source: newCamSource }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const nc = await res.json();
      toast(`➕ Camera "${nc.name}" added`, 'success');
      setAddDialogOpen(false); setNewCamName(''); setNewCamSource('');
      await fetchCameras(nc.id);
    } catch (err) { toast(`Add failed: ${err.message}`, 'error'); }
  };

  const triggerDeleteConfirm = (cam, e) => { e.stopPropagation(); setCamToDelete(cam); setDeleteConfirmOpen(true); };
  const handleDeleteCamera = async () => {
    if (!camToDelete) return;
    try {
      const res = await fetch(`${API}/api/cameras/${camToDelete.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast('🗑 Camera deleted', 'success');
      setDeleteConfirmOpen(false); setCamToDelete(null); await fetchCameras();
    } catch (err) { toast(`Delete failed: ${err.message}`, 'error'); }
  };

  const enabledCount = Object.values(features).filter(s => s.enabled).length;
  // A multi-zone feature is 'configured' if the primary OR any extra zone is configured
  const isFeatConfigured = (key) => {
    const st = features[key];
    return st.configured || (MULTI_ZONE_KEYS.has(key) && (st.extraZones || []).some(z => z.configured));
  };
  const pending      = ALL_FEATURES.filter(f => features[f.key].enabled && f.needsDraw && !isFeatConfigured(f.key));
  const readyToApply = selectedCam && enabledCount > 0 && pending.length === 0;

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 48px)', overflow: 'hidden', bgcolor: 'background.default' }}>

      {/* ══ LEFT: Cameras list ══ */}
      <Box sx={{ width: 265, flexShrink: 0, borderRight: '1px solid', borderColor: 'divider', display: 'flex', flexDirection: 'column', bgcolor: 'background.paper' }}>
        <Box sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ color: 'text.primary', fontSize: '0.88rem' }}>Camera Channels</Typography>
          <Tooltip title="Add Camera">
            <IconButton size="small" onClick={() => setAddDialogOpen(true)}
              sx={{ color: '#00b0ff', bgcolor: 'rgba(0,176,255,0.1)', '&:hover': { bgcolor: 'rgba(0,176,255,0.2)' } }}>
              <Add fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Divider />
        <Box sx={{ flex: 1, overflowY: 'auto', p: 1, '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.2)', borderRadius: 4 } }}>
          {cameras.length === 0 ? (
            <Box sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="caption" color="text.disabled">No cameras configured.</Typography>
            </Box>
          ) : (
            <List disablePadding>
              {cameras.map(c => {
                const isSel = selectedCam?.id === c.id;
                return (
                  <ListItem key={c.id} disablePadding sx={{ mb: 0.5 }}>
                    <ListItemButton selected={isSel} onClick={() => selectCamera(c)}
                      sx={{
                        borderRadius: 1.5, py: 0.9, px: 1.5,
                        bgcolor: isSel ? 'rgba(0,176,255,0.08)' : 'transparent',
                        border: isSel ? '1px solid rgba(0,176,255,0.25)' : '1px solid transparent',
                        '&.Mui-selected': { bgcolor: 'rgba(0,176,255,0.1)', '&:hover': { bgcolor: 'rgba(0,176,255,0.15)' } },
                        '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' },
                      }}>
                      <Videocam sx={{ mr: 1.5, color: isSel ? '#00b0ff' : 'rgba(255,255,255,0.35)', fontSize: 18 }} />
                      <ListItemText
                        primary={c.name}
                        primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: isSel ? 700 : 500, color: isSel ? 'text.primary' : 'text.secondary', noWrap: true }}
                        secondary={c.id}
                        secondaryTypographyProps={{ fontSize: '0.65rem', color: 'text.disabled' }}
                      />
                      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ ml: 0.5 }}>
                        {(c.features?.length > 0) && (
                          <Chip label={c.features.length} size="small"
                            sx={{ height: 15, fontSize: '0.6rem', bgcolor: '#00b0ff18', color: '#00b0ff', border: '1px solid #00b0ff33', fontWeight: 700 }} />
                        )}
                        <IconButton size="small" onClick={(e) => triggerDeleteConfirm(c, e)}
                          sx={{ color: 'rgba(255,255,255,0.18)', '&:hover': { color: '#ff1744' }, p: 0.2 }}>
                          <Delete sx={{ fontSize: 15 }} />
                        </IconButton>
                      </Stack>
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
          )}
        </Box>
      </Box>

      {/* ══ MIDDLE: Video + canvas ══ */}
      {selectedCam ? (
        <Box sx={{ flex: '1 1 0', display: 'flex', flexDirection: 'column', p: 2, overflow: 'hidden', minWidth: 0 }}>
          {/* Name / Source bar */}
          <Paper sx={{ p: 1.25, mb: 1.5, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <TextField label="Camera Name" value={camName} onChange={e => setCamName(e.target.value)}
                variant="outlined" size="small" fullWidth
                InputLabelProps={{ style: { color: isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.6)', fontSize: '0.78rem' } }}
                inputProps={{ style: { color: isDark ? '#fff' : '#000', fontSize: '0.82rem' } }}
                sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.2)' }, '&:hover fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.4)' } } }} />
              <TextField label="RTSP / Source URL" value={camSource} onChange={e => setCamSource(e.target.value)}
                variant="outlined" size="small" fullWidth
                InputLabelProps={{ style: { color: isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.6)', fontSize: '0.78rem' } }}
                inputProps={{ style: { color: isDark ? '#fff' : '#000', fontSize: '0.82rem' } }}
                sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.2)' }, '&:hover fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.4)' } } }} />
              {/* Full-frame toggle */}
              <Tooltip title="Full-Frame 24h Analytics: bypasses zone restrictions, runs selected analytics on entire FOV">
                <Paper sx={{
                  px: 1.25, py: 0.5, flexShrink: 0, borderRadius: 1.5,
                  border: fullFrame ? '1px solid rgba(100,200,255,0.4)' : '1px solid',
                  borderColor: fullFrame ? 'transparent' : 'divider',
                  bgcolor: fullFrame ? 'rgba(100,200,255,0.08)' : (isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'),
                  display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer',
                  transition: 'all 0.2s',
                }} onClick={() => setFullFrame(v => !v)}>
                  <Visibility sx={{ fontSize: 14, color: fullFrame ? '#64c8ff' : 'text.disabled' }} />
                  <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, color: fullFrame ? '#64c8ff' : 'text.secondary', whiteSpace: 'nowrap' }}>
                    24h Full-Frame
                  </Typography>
                  <Switch size="small" checked={fullFrame} onClick={e => e.stopPropagation()}
                    onChange={e => setFullFrame(e.target.checked)}
                    sx={{ ml: 0.25, '& .MuiSwitch-thumb': { width: 10, height: 10, bgcolor: fullFrame ? '#64c8ff' : (isDark ? '#444' : '#ccc') } }} />
                </Paper>
              </Tooltip>
              {activeDrawing && (
                <Chip label={`✏️ ${activeFeat?.label}`} size="small"
                  sx={{ bgcolor: activeFeat?.color + '22', color: activeFeat?.color, border: `1px solid ${activeFeat?.color}55`, fontWeight: 700, height: 26, flexShrink: 0 }} />
              )}
            </Stack>
          </Paper>

          {/* Video + canvas overlay */}
          <Box sx={{
            flex: 1, position: 'relative', borderRadius: 2, overflow: 'hidden',
            border: activeDrawing ? `2px solid ${activeFeat?.color}88` : '2px solid rgba(255,255,255,0.07)',
            bgcolor: '#000', transition: 'border-color 0.2s',
            boxShadow: activeDrawing ? `0 0 20px ${activeFeat?.color}22` : 'none',
          }}>
            <img src={`${API}/api/cameras/${selectedCam.id}/stream`} alt="Camera"
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }} />
            <canvas ref={canvasRef} width={W} height={H}
              onClick={onClick} onDoubleClick={onDblClick} onMouseMove={onMouseMove}
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
                cursor: activeDrawing ? 'crosshair' : 'default', background: 'transparent' }} />
            {activeDrawing && (
              <Box sx={{ position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)',
                bgcolor: 'rgba(0,0,0,0.85)', px: 2.5, py: 0.7, borderRadius: 10,
                border: `1px solid ${activeFeat?.color}55`, pointerEvents: 'none' }}>
                <Typography variant="caption" sx={{ color: activeFeat?.color, fontWeight: 700 }}>
                  {activeFeat?.shape === 'line'
                    ? `Click 2 points to define crossing line (${drawPts.length}/2)`
                    : `Click corners · double-click to finish · ${drawPts.length} pts placed`}
                </Typography>
              </Box>
            )}
            {fullFrame && (
              <Box sx={{ position: 'absolute', top: 8, right: 8, px: 1, py: 0.3, borderRadius: 1,
                bgcolor: 'rgba(100,200,255,0.15)', border: '1px solid rgba(100,200,255,0.3)' }}>
                <Typography variant="caption" sx={{ color: '#64c8ff', fontSize: '0.6rem', fontWeight: 700 }}>
                  ◈ 24H FULL-FRAME OVERRIDE ACTIVE
                </Typography>
              </Box>
            )}
          </Box>

          {/* Drawing toolbar */}
          {activeDrawing && drawPts.length > 0 && (
            <Stack direction="row" spacing={1} mt={1}>
              <Button size="small" variant="outlined" color="warning" startIcon={<Undo />} onClick={undoPt}>Undo</Button>
              {activeFeat?.shape === 'polygon' && drawPts.length >= 3 && (
                <Button size="small" variant="contained"
                  sx={{ bgcolor: activeFeat?.color, '&:hover': { bgcolor: activeFeat?.color + 'bb' } }}
                  onClick={() => finishDraw(drawPts)}>
                  Finish ({drawPts.length} pts)
                </Button>
              )}
              <Button size="small" variant="text" color="error" startIcon={<Cancel />} onClick={cancelDraw}>Cancel</Button>
            </Stack>
          )}
        </Box>
      ) : (
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: 4 }}>
          <Videocam sx={{ fontSize: 72, color: 'rgba(255,255,255,0.04)', mb: 2 }} />
          <Typography color="text.secondary">Select a camera from the sidebar to begin configuration.</Typography>
          <Button variant="outlined" startIcon={<Add />} onClick={() => setAddDialogOpen(true)}
            sx={{ mt: 2, borderColor: 'rgba(255,255,255,0.1)' }}>
            Add Camera
          </Button>
        </Box>
      )}

      {/* ══ RIGHT: Feature config panel ══ */}
      {selectedCam && (
        <Box sx={{ width: 340, flexShrink: 0, borderLeft: '1px solid', borderColor: 'divider', display: 'flex', flexDirection: 'column', bgcolor: 'background.paper' }}>
          <Box sx={{ px: 2, pt: 2, pb: 1 }}>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="subtitle1" fontWeight={700} sx={{ fontSize: '0.9rem' }}>AI Analytics Config</Typography>
                <Typography variant="caption" color="text.secondary">Enable · Configure · Apply per channel.</Typography>
              </Box>
              <Tooltip title="Clear all features">
                <Button size="small" variant="outlined" color="warning"
                  startIcon={<Refresh sx={{ fontSize: 12 }} />}
                  onClick={() => setDiagOpen(true)}
                  sx={{ fontSize: '0.63rem', py: 0.15, px: 0.7 }}>
                  Reset
                </Button>
              </Tooltip>
            </Stack>
          </Box>
          <Divider />

          {/* Feature cards */}
          <Box sx={{ flex: 1, overflowY: 'auto', px: 1.5, py: 1.5,
            '&::-webkit-scrollbar': { width: 3 },
            '&::-webkit-scrollbar-thumb': { bgcolor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.2)', borderRadius: 4 } }}>
            {ALL_FEATURES.map(f => {
              const st       = features[f.key] || { enabled: false, points: [], configured: false };
              const isOn     = st.enabled;
              const isDone   = st.configured;
              const isActive = activeDrawing === f.key;
              const ec       = extraConfig[f.key] || {};
              const FeatIcon = f.icon || Settings;

              return (
                <Paper key={f.key} sx={{
                  mb: 1, p: 1.25, borderRadius: 2,
                  border: isActive ? `1px solid ${f.color}88` : isOn ? `1px solid ${f.color}33` : '1px solid rgba(255,255,255,0.05)',
                  bgcolor: isActive ? `${f.color}12` : isOn ? `${f.color}07` : 'rgba(255,255,255,0.012)',
                  transition: 'all 0.2s', position: 'relative', overflow: 'hidden',
                }}>
                  {/* Color strip */}
                  <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, bgcolor: f.color, opacity: isOn ? 1 : 0.18 }} />

                  <Box sx={{ pl: 1 }}>
                    {/* Header row */}
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ flex: 1, minWidth: 0 }}>
                        <FeatIcon sx={{ fontSize: 13, color: f.color, opacity: isOn ? 1 : 0.4, flexShrink: 0 }} />
                        <Typography variant="body2" fontWeight={isOn ? 800 : 400}
                          sx={{ fontSize: '0.77rem', color: 'text.primary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {f.label}
                        </Typography>
                        <Chip label={f.sev} size="small" sx={{
                          height: 14, fontSize: '0.52rem', fontWeight: 700,
                          bgcolor: SEV_COLOR[f.sev] + '20', color: SEV_COLOR[f.sev],
                          border: `1px solid ${SEV_COLOR[f.sev]}30`, flexShrink: 0,
                        }} />
                      </Stack>
                      <Switch size="small" checked={isOn} onChange={() => toggleFeat(f.key)}
                        sx={{ '& .MuiSwitch-thumb': { bgcolor: isOn ? f.color : '#444', width: 13, height: 13 },
                          '& .Mui-checked + .MuiSwitch-track': { bgcolor: f.color + '55' } }} />
                    </Stack>

                    <Typography variant="caption" color="text.secondary"
                      sx={{ display: 'block', mt: 0.4, fontSize: '0.63rem', lineHeight: 1.3, opacity: isOn ? 0.85 : 0.35 }}>
                      {f.desc}
                    </Typography>

                    {/* Expanded config when enabled */}
                    {isOn && (
                      <Box sx={{ mt: 1 }}>
                        {/* ── Extra config per feature ── */}
                        <FeatureExtraConfig
                          featureKey={f.key}
                          config={ec}
                          onChange={(patch) => setExtraConfig(prev => ({ ...prev, [f.key]: patch }))}
                          accentColor={f.color}
                        />

                        {/* ── Zone drawing status ── */}
                        {f.needsDraw && (() => {
                          const isMultiZone = MULTI_ZONE_KEYS.has(f.key);
                          const multiZoneOn = isMultiZone && st.multiZone;
                          const extraZones  = st.extraZones || [];
                          const allZones    = isDone
                            ? [{ id: 'primary', points: st.points, configured: true, label: `${f.shape === 'line' ? 'Line' : 'Zone'} 1` }, ...extraZones.map((ez, i) => ({ ...ez, label: `${f.shape === 'line' ? 'Line' : 'Zone'} ${i + 2}` }))]
                            : extraZones.map((ez, i) => ({ ...ez, label: `${f.shape === 'line' ? 'Line' : 'Zone'} ${i + 2}` }));

                          return (
                            <Box sx={{ mt: 1 }}>
                              {/* Multi-Zone toggle row (only for supported features) */}
                              {isMultiZone && isDone && (
                                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5,
                                  bgcolor: multiZoneOn ? `${f.color}12` : 'transparent',
                                  border: multiZoneOn ? `1px solid ${f.color}33` : '1px solid transparent',
                                  borderRadius: 1, px: 0.75, py: 0.25, transition: 'all 0.2s' }}>
                                  <Typography variant="caption" sx={{ fontSize: '0.58rem', color: multiZoneOn ? f.color : 'text.disabled', fontWeight: 700, flex: 1 }}>
                                    ⬡ Multi-Zone
                                  </Typography>
                                  <Switch size="small" checked={multiZoneOn} onChange={() => toggleMultiZone(f.key)}
                                    sx={{ '& .MuiSwitch-thumb': { width: 10, height: 10, bgcolor: multiZoneOn ? f.color : (isDark ? '#555' : '#bbb') },
                                      '& .Mui-checked + .MuiSwitch-track': { bgcolor: f.color + '55' } }} />
                                </Stack>
                              )}

                              {/* Zone list when multi-zone is on */}
                              {multiZoneOn && allZones.length > 0 && (
                                <Box sx={{ mb: 0.5 }}>
                                  {allZones.map((z) => (
                                    <Stack key={z.id} direction="row" alignItems="center" spacing={0.4} sx={{ mb: 0.3,
                                      bgcolor: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
                                      borderRadius: 1, px: 0.75, py: 0.2, border: '1px solid', borderColor: 'divider' }}>
                                      <CheckCircle sx={{ fontSize: 10, color: '#69f0ae', flexShrink: 0 }} />
                                      <Typography variant="caption" sx={{ fontSize: '0.6rem', flex: 1, color: 'text.secondary' }}>{z.label}</Typography>
                                      <Button size="small" variant="text"
                                        onClick={() => z.id === 'primary' ? startDraw(f.key, false) : startDraw(f.key, true)}
                                        disabled={!!activeDrawing}
                                        sx={{ fontSize: '0.52rem', py: 0, px: 0.4, color: f.color, minWidth: 0 }}>
                                        Redraw
                                      </Button>
                                      <IconButton size="small"
                                        onClick={() => z.id === 'primary' ? clearZone(f.key) : clearExtraZone(f.key, z.id)}
                                        sx={{ color: 'error.main', opacity: 0.5, p: 0.15 }}>
                                        <HighlightOff sx={{ fontSize: 10 }} />
                                      </IconButton>
                                    </Stack>
                                  ))}
                                </Box>
                              )}

                              {/* Primary zone status (single zone mode or first zone) */}
                              {!multiZoneOn && (
                                isDone ? (
                                  <Stack direction="row" alignItems="center" spacing={0.5}>
                                    <CheckCircle sx={{ fontSize: 12, color: '#69f0ae' }} />
                                    <Typography variant="caption" sx={{ color: '#69f0ae', flex: 1, fontSize: '0.63rem' }}>
                                      {f.shape === 'line' ? 'Line' : 'Zone'} configured ✓
                                    </Typography>
                                    <Button size="small" variant="text" startIcon={<Draw sx={{ fontSize: 9 }} />}
                                      onClick={() => startDraw(f.key, false)}
                                      disabled={!!activeDrawing && !isActive}
                                      sx={{ fontSize: '0.58rem', py: 0, px: 0.5, color: f.color, minWidth: 0 }}>
                                      Redraw
                                    </Button>
                                    <IconButton size="small" onClick={() => clearZone(f.key)}
                                      sx={{ color: 'error.main', opacity: 0.5, p: 0.2 }}>
                                      <HighlightOff sx={{ fontSize: 12 }} />
                                    </IconButton>
                                  </Stack>
                                ) : isActive ? (
                                  <Stack direction="row" alignItems="center" spacing={0.5}>
                                    <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: f.color,
                                      animation: 'blink 1s infinite', '@keyframes blink': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.15 } } }} />
                                    <Typography variant="caption" sx={{ color: f.color, fontWeight: 600, fontSize: '0.63rem' }}>
                                      {f.shape === 'line' ? `Draw line (${drawPts.length}/2)` : `Drawing zone · ${drawPts.length} pts`}
                                    </Typography>
                                  </Stack>
                                ) : (
                                  <Stack direction="row" alignItems="center" spacing={0.5}>
                                    <WarningAmber sx={{ fontSize: 12, color: '#ffd600' }} />
                                    <Typography variant="caption" sx={{ color: '#ffd600', flex: 1, fontSize: '0.63rem' }}>
                                      Draw {f.shape} on camera view
                                    </Typography>
                                    <Button size="small" variant="contained"
                                      startIcon={<Draw sx={{ fontSize: 9 }} />}
                                      onClick={() => startDraw(f.key, false)}
                                      disabled={!!activeDrawing}
                                      sx={{ fontSize: '0.58rem', py: 0.15, px: 0.75, bgcolor: f.color, '&:hover': { bgcolor: f.color + 'cc' }, minWidth: 0 }}>
                                      Draw
                                    </Button>
                                  </Stack>
                                )
                              )}

                              {/* Currently drawing indicator (shown in both modes) */}
                              {isActive && multiZoneOn && (
                                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.5 }}>
                                  <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: f.color,
                                    animation: 'blink 1s infinite', '@keyframes blink': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.15 } } }} />
                                  <Typography variant="caption" sx={{ color: f.color, fontWeight: 600, fontSize: '0.63rem' }}>
                                    {f.shape === 'line' ? `Draw line (${drawPts.length}/2)` : `Drawing zone · ${drawPts.length} pts`}
                                  </Typography>
                                </Stack>
                              )}

                              {/* Add Zone button (multi-zone mode, not actively drawing) */}
                              {multiZoneOn && !isActive && (
                                <Button size="small" variant="outlined" startIcon={<Draw sx={{ fontSize: 9 }} />}
                                  onClick={() => startDraw(f.key, true)}
                                  disabled={!!activeDrawing}
                                  sx={{ mt: 0.5, width: '100%', fontSize: '0.58rem', py: 0.25,
                                    color: f.color, borderColor: f.color + '55',
                                    '&:hover': { borderColor: f.color, bgcolor: f.color + '12' } }}>
                                  + Add Zone {allZones.length + 1}
                                </Button>
                              )}
                            </Box>
                          );
                        })()}
                        {!f.needsDraw && (
                          <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.75 }}>
                            <CheckCircle sx={{ fontSize: 12, color: '#69f0ae' }} />
                            <Typography variant="caption" sx={{ color: '#69f0ae', fontSize: '0.63rem' }}>
                              Whole-frame — no zone required
                            </Typography>
                          </Stack>
                        )}
                      </Box>
                    )}
                  </Box>
                </Paper>
              );
            })}
          </Box>

          <Divider />

          {/* Footer */}
          <Box sx={{ p: 2 }}>
            {pending.length > 0 && (
              <Alert severity="warning" sx={{ mb: 1.5, py: 0, fontSize: '0.65rem' }}>
                Needs drawing: {pending.map(f => f.label).join(', ')}
              </Alert>
            )}
            {enabledCount === 0 && (
              <Typography variant="caption" color="text.disabled" display="block" textAlign="center" mb={1} sx={{ fontSize: '0.65rem' }}>
                Enable at least one analytic feature.
              </Typography>
            )}
            <Button fullWidth variant="contained" size="medium"
              startIcon={<PlayArrow />}
              onClick={handleApply}
              disabled={!readyToApply || applying}
              sx={{
                fontWeight: 700, borderRadius: 2,
                background: readyToApply ? 'linear-gradient(135deg, #00b0ff, #00e5ff)' : undefined,
                color: readyToApply ? '#000' : undefined,
                boxShadow: readyToApply ? '0 4px 20px #00b0ff44' : 'none',
              }}>
              {applying ? 'Saving…' : readyToApply ? 'Save & Apply Settings' : 'Configure Features First'}
            </Button>
            <Typography variant="caption" color="text.disabled" display="block" textAlign="center" mt={0.5} sx={{ fontSize: '0.58rem' }}>
              AI engine hot-reloads config in ~5s
            </Typography>
          </Box>
        </Box>
      )}

      {/* ── Dialogs ─────────────────────────────────────────────────────────── */}
      {/* Reset confirm */}
      <Dialog open={diagOpen} onClose={() => setDiagOpen(false)}
        PaperProps={{ sx: { border: '1px solid rgba(255,165,0,0.3)', borderRadius: 3 } }}>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Warning sx={{ color: 'warning.main' }} /> Reset Features?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            Clears all configured features and zone drawings for this camera in the editor.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDiagOpen(false)} color="inherit">Cancel</Button>
          <Button onClick={async () => {
            cancelDraw(); setFeatures(initState()); setExtraConfig(defaultFeatureConfig());
            setFullFrame(false); setDiagOpen(false);
            // Wipe zones/lines from cameras.json so they don't reappear on reload
            if (selectedCam) {
              try {
                await fetch(`${API}/api/cameras/${selectedCam.id}/zones`, { method: 'DELETE' });
                // Reload camera config so UI is in sync with cleared backend state
                await fetchCameras(selectedCam.id);
              } catch { /* best-effort */ }
            }
            toast('All features & zones cleared.', 'info');
          }} color="warning" variant="contained">Reset All</Button>
        </DialogActions>
      </Dialog>

      {/* Add camera */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)}
        PaperProps={{ sx: { border: '1px solid rgba(0,176,255,0.2)', borderRadius: 3, minWidth: 420 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Add Camera Channel</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Camera Name" fullWidth variant="outlined" size="small"
              value={newCamName} onChange={e => setNewCamName(e.target.value)}
              inputProps={{ style: { color: isDark ? '#fff' : '#000' } }}
              InputLabelProps={{ style: { color: isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.6)' } }}
              sx={{ '& .MuiOutlinedInput-root fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)' } }} />
            <TextField label="RTSP / Source URL" fullWidth variant="outlined" size="small"
              value={newCamSource} onChange={e => setNewCamSource(e.target.value)}
              inputProps={{ style: { color: isDark ? '#fff' : '#000' } }}
              InputLabelProps={{ style: { color: isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.6)' } }}
              sx={{ '& .MuiOutlinedInput-root fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)' } }} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setAddDialogOpen(false)} color="inherit">Cancel</Button>
          <Button onClick={handleAddCamera} variant="contained" color="primary">Add Channel</Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={deleteConfirmOpen} onClose={() => setDeleteConfirmOpen(false)}
        PaperProps={{ sx: { border: '1px solid rgba(255,23,68,0.3)', borderRadius: 3 } }}>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Delete sx={{ color: 'error.main' }} /> Delete Camera?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            Remove <strong style={{ color: 'inherit' }}>{camToDelete?.name}</strong>? This also removes its AI configuration.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteConfirmOpen(false)} color="inherit">Cancel</Button>
          <Button onClick={handleDeleteCamera} color="error" variant="contained">Delete</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={snack.open} autoHideDuration={3500} onClose={() => setSnack(s => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity={snack.sev} onClose={() => setSnack(s => ({ ...s, open: false }))}
          sx={{ bgcolor: snack.sev === 'success' ? '#1a3a2a' : snack.sev === 'error' ? '#3a1a1a' : '#2a2a1a' }}>
          {snack.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
