import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Stack, Paper, Chip, Divider,
  Badge, IconButton, Tooltip, Alert, Button,
  Select, MenuItem, Checkbox, ListItemText, FormControl,
  Snackbar, LinearProgress
} from '@mui/material';
import {
  Notifications, Refresh, DeleteSweep, Videocam, PlayArrow, Stop,
  LocalFireDepartment, Person, Timeline, Group,
  Shield, Warning, GpsFixed, CheckCircle, Pets, DirectionsCar
} from '@mui/icons-material';
import { useTheme } from '@mui/material/styles';

const API     = 'http://localhost:5050';
const POLL_MS = 3000;

const FEATURE_META = {
  intrusion:           { label: 'Intrusion',          color: '#ff6d00', icon: <Shield fontSize="small" />,              severity: 'HIGH'     },
  no_go_zone:          { label: 'No-Go Zone',          color: '#ff1744', icon: <Warning fontSize="small" />,             severity: 'CRITICAL' },
  loitering:           { label: 'Loitering',           color: '#ffd600', icon: <Person fontSize="small" />,              severity: 'MEDIUM'   },
  crowd:               { label: 'Crowd',               color: '#76ff03', icon: <Group fontSize="small" />,               severity: 'MEDIUM'   },
  missing_person:      { label: 'Person Missing',      color: '#e040fb', icon: <Person fontSize="small" />,              severity: 'HIGH'     },
  personal_monitoring: { label: 'Personal Monitor',    color: '#00e5ff', icon: <GpsFixed fontSize="small" />,            severity: 'MEDIUM'   },
  footfall:            { label: 'Footfall Count',      color: '#00b0ff', icon: <Timeline fontSize="small" />,            severity: 'LOW'      },
  perimeter:           { label: 'Perimeter',           color: '#ff4081', icon: <Shield fontSize="small" />,              severity: 'HIGH'     },
  fire_smoke:          { label: 'Fire & Smoke',        color: '#ff3d00', icon: <LocalFireDepartment fontSize="small" />, severity: 'CRITICAL' },
  tampering:           { label: 'Tampering',           color: '#9c27b0', icon: <Warning fontSize="small" />,             severity: 'HIGH'     },
  weapon_detection:    { label: 'Weapon Detected',     color: '#ff1744', icon: <Warning fontSize="small" />,             severity: 'CRITICAL' },
  criminal_face:       { label: 'Criminal Identified', color: '#ff6d00', icon: <Person fontSize="small" />,              severity: 'CRITICAL' },
  animal_detection:    { label: 'Animal Alert',        color: '#22c822', icon: <Pets fontSize="small" />,                severity: 'HIGH'     },
  vehicle_detection:   { label: 'Vehicle Alert',       color: '#00ffff', icon: <DirectionsCar fontSize="small" />,       severity: 'MEDIUM'   },
};

const SEV_COLOR = { CRITICAL: '#ff1744', HIGH: '#ff6d00', MEDIUM: '#ffd600', LOW: '#00b0ff' };
const SEV_BG    = { CRITICAL: '#ff174222', HIGH: '#ff6d0022', MEDIUM: '#ffd60022', LOW: '#00b0ff22' };

function timeAgo(iso) {
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function parseTamperAlertNum(message) {
  if (!message) return null;
  const match = message.match(/\(Alert (\d+)\/10\)/);
  return match ? parseInt(match[1], 10) : null;
}

function isTamperResolved(alert) {
  return (
    alert.feature === 'tampering' &&
    alert.message &&
    alert.message.toLowerCase().includes('alerts stopped')
  );
}

// ── Tampering alert card ───────────────────────────────────────────────────
function TamperingAlertCard({ alert }) {
  const resolved = isTamperResolved(alert);
  const alertNum = parseTamperAlertNum(alert.message);

  // Alert 11 — green resolved card
  if (resolved) {
    return (
      <Paper sx={{
        mb: 1, p: 1.5, borderRadius: 2,
        border: '1.5px solid #00e676',
        bgcolor: '#00e67614',
        position: 'relative', overflow: 'hidden',
      }}>
        <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, bgcolor: '#00e676' }} />
        <Box sx={{ pl: 1 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
            <Stack direction="row" alignItems="center" spacing={0.75}>
              <CheckCircle sx={{ color: '#00e676', fontSize: 18 }} />
              <Typography variant="body2" fontWeight={700} sx={{ color: '#00e676' }}>
                Tampering — Baseline Updated
              </Typography>
            </Stack>
            <Typography variant="caption" color="text.disabled">
              {alert.timestamp ? timeAgo(alert.timestamp) : '—'}
            </Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Camera: <strong>{alert.cam_id}</strong>
          </Typography>
          <Typography variant="caption" display="block"
            sx={{ color: '#00e676', mt: 0.5, fontSize: '0.72rem', fontWeight: 600 }}>
            ✔ New camera angle captured. Alerts stopped.
          </Typography>
        </Box>
      </Paper>
    );
  }

  // Alerts 1–10 — orange card with progress bar
  const progress = alertNum ? (alertNum / 10) * 100 : null;
  const isCover  = alert.tamper_type === 'cover';

  return (
    <Paper sx={{
      mb: 1, p: 1.5, borderRadius: 2,
      border: '1px solid #ff6d0066',
      bgcolor: '#ff6d0015',
      position: 'relative', overflow: 'hidden',
    }}>
      <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, bgcolor: '#ff6d00' }} />
      <Box sx={{ pl: 1 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <Warning sx={{ color: '#ff6d00', fontSize: 18 }} />
            <Typography variant="body2" fontWeight={700} sx={{ color: '#ff6d00' }}>
              {isCover ? 'Camera Covered' : 'Tampering Detected'}
            </Typography>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <Chip label="HIGH" size="small" sx={{
              height: 18, fontSize: '0.58rem', fontWeight: 700,
              bgcolor: '#ff6d0022', color: '#ff6d00', border: '1px solid #ff6d0055',
            }} />
            <Typography variant="caption" color="text.disabled">
              {alert.timestamp ? timeAgo(alert.timestamp) : '—'}
            </Typography>
          </Stack>
        </Stack>

        <Typography variant="caption" color="text.secondary">
          Camera: <strong>{alert.cam_id}</strong>
        </Typography>

        {/* Cover alert — simple message, no progress bar */}
        {isCover && (
          <Typography variant="caption" display="block"
            sx={{ color: '#ffb74d', mt: 0.5, fontSize: '0.68rem' }}>
            🖐 Camera lens appears to be covered or blocked
          </Typography>
        )}

        {/* Repositioned — progress bar */}
        {!isCover && alertNum && (
          <Box sx={{ mt: 0.75 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.25}>
              <Typography variant="caption" sx={{ color: '#ff6d00', fontWeight: 600, fontSize: '0.68rem' }}>
                Camera still tampered — auto-resolves at 10
              </Typography>
              <Typography variant="caption" sx={{ color: '#ff6d00', fontWeight: 800, fontSize: '0.68rem' }}>
                {alertNum}/10
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={progress}
              sx={{
                height: 4, borderRadius: 2,
                bgcolor: '#ff6d0022',
                '& .MuiLinearProgress-bar': { bgcolor: '#ff6d00', borderRadius: 2 },
              }}
            />
          </Box>
        )}

        {/* Fallback message for unknown tamper types with no alertNum */}
        {!isCover && !alertNum && alert.message && (
          <Typography variant="caption" display="block"
            sx={{ color: '#ffb74d', mt: 0.5, fontSize: '0.68rem' }}>
            {alert.message}
          </Typography>
        )}
      </Box>
    </Paper>
  );
}

function CameraGridItem({ camId, label, streamActive, streamKey }) {
  const [localError, setLocalError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    setLocalError(false);
  }, [streamKey, camId]);

  return (
    <Box sx={{
      position: 'relative', flex: 1, height: '100%', minHeight: 0,
      bgcolor: '#000', borderRadius: 1.5, overflow: 'hidden',
      border: '1px solid rgba(255,255,255,0.08)',
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    }}>
      <Box sx={{
        position: 'absolute', top: 8, left: 8,
        bgcolor: 'rgba(0,0,0,0.65)', color: '#fff',
        px: 1, py: 0.5, borderRadius: 1,
        fontSize: '0.75rem', fontWeight: 600, zIndex: 2,
        backdropFilter: 'blur(4px)', border: '1px solid rgba(255,255,255,0.1)'
      }}>
        {label}
      </Box>

      {!streamActive ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
          <Videocam sx={{ fontSize: 36, color: 'rgba(255,255,255,0.2)' }} />
          <Typography variant="caption" color="text.disabled">Feed Paused</Typography>
        </Box>
      ) : localError ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, p: 2, textAlign: 'center' }}>
          <Warning color="error" sx={{ fontSize: 32 }} />
          <Typography variant="caption" color="error.main" fontWeight={600}>Offline</Typography>
          <Button size="small" variant="text" sx={{ color: '#00b0ff', fontSize: '0.65rem', minWidth: 0, p: 0 }}
            onClick={() => { setLocalError(false); setRetryKey(k => k + 1); }}>Retry</Button>
        </Box>
      ) : (
        <img
          key={`${camId}_${streamKey}_${retryKey}`}
          src={`${API}/api/cameras/${camId}/stream`}
          alt={label}
          onError={() => setLocalError(true)}
          onLoad={() => setLocalError(false)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      )}
    </Box>
  );
}

export default function DashboardPage() {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [camId,        setCamId]        = useState('all');
  const [camConfig,    setCamConfig]    = useState(null);
  const [alerts,       setAlerts]       = useState([]);
  const [newCount,     setNewCount]     = useState(0);
  const [backendOk,    setBackendOk]    = useState(true);
  const [streamError,  setStreamError]  = useState(false);
  const [streamActive, setStreamActive] = useState(true);
  const seenIds = useRef(new Set());
  const [streamKey, setStreamKey] = useState(0);
  const [isUpdatingFeatures, setIsUpdatingFeatures] = useState(false);
  const [popupAlert, setPopupAlert] = useState({ open: false, message: '', severity: 'info' });
  const [cameras, setCameras] = useState([]);

  const playAlarmSound = (severity) => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      if (severity === 'CRITICAL') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        gain.gain.setValueAtTime(0.08, ctx.currentTime);
        osc.start(); osc.stop(ctx.currentTime + 0.15);
        setTimeout(() => {
          const osc2 = ctx.createOscillator(); const gain2 = ctx.createGain();
          osc2.connect(gain2); gain2.connect(ctx.destination);
          osc2.type = 'sawtooth'; osc2.frequency.setValueAtTime(880, ctx.currentTime);
          gain2.gain.setValueAtTime(0.08, ctx.currentTime);
          osc2.start(); osc2.stop(ctx.currentTime + 0.15);
        }, 200);
      } else if (severity === 'HIGH') {
        osc.type = 'sine'; osc.frequency.setValueAtTime(660, ctx.currentTime);
        gain.gain.setValueAtTime(0.08, ctx.currentTime);
        osc.start(); osc.stop(ctx.currentTime + 0.25);
      } else {
        osc.type = 'sine'; osc.frequency.setValueAtTime(440, ctx.currentTime);
        gain.gain.setValueAtTime(0.05, ctx.currentTime);
        osc.start(); osc.stop(ctx.currentTime + 0.15);
      }
    } catch (e) { console.error("Audio alarm failed", e); }
  };

  const triggerNotifications = useCallback((alert) => {
    const meta = FEATURE_META[alert.feature] || { label: alert.feature, severity: 'MEDIUM' };
    const sev = alert.severity || meta.severity || 'MEDIUM';
    if (isTamperResolved(alert)) {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator(); const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = 'sine'; osc.frequency.setValueAtTime(523, ctx.currentTime);
        gain.gain.setValueAtTime(0.05, ctx.currentTime);
        osc.start(); osc.stop(ctx.currentTime + 0.4);
      } catch (e) {}
    } else {
      playAlarmSound(sev);
    }
    if (Notification.permission === 'granted') {
      new Notification(`Surveillance Alert: ${meta.label}`, {
        body: alert.message || `Camera: ${alert.cam_id} | Severity: ${sev}`,
      });
    }
    setPopupAlert({
      open: true,
      message: alert.message || `${meta.label} detected on ${alert.cam_id}!`,
      severity: isTamperResolved(alert) ? 'success' : (sev === 'CRITICAL' ? 'error' : sev === 'HIGH' ? 'warning' : 'info')
    });
  }, []);

  useEffect(() => {
    if (Notification.permission === 'default') Notification.requestPermission();
  }, []);

  const handleFeatureChange = async (event) => {
    if (camId === 'all') return;
    const { target: { value } } = event;
    const newFeatures = typeof value === 'string' ? value.split(',') : value;
    const updatedConfig = { ...camConfig, features: newFeatures };
    setCamConfig(updatedConfig);
    setIsUpdatingFeatures(true);
    try {
      await fetch(`${API}/api/cameras/${camId}/config`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedConfig)
      });
      await loadConfig();
    } catch (e) { console.error("Failed to update features", e); }
    finally { setIsUpdatingFeatures(false); }
  };

  const startStream = () => { setStreamKey(k => k + 1); setStreamActive(true); setStreamError(false); };
  const stopStream  = () => setStreamActive(false);

  const handleCamChange = (newId) => {
    setCamId(newId); setCamConfig(null); setAlerts([]);
    seenIds.current.clear(); setNewCount(0);
    setStreamError(false); setStreamKey(k => k + 1); setStreamActive(true);
  };

  const loadConfig = useCallback(async () => {
    if (camId === 'all') { setCamConfig({ name: 'All Cameras', features: [] }); return; }
    try {
      const res = await fetch(`${API}/api/cameras/${camId}`);
      if (res.ok) { setCamConfig(await res.json()); setBackendOk(true); }
    } catch { setBackendOk(false); }
  }, [camId]);

  const fetchAlerts = useCallback(async () => {
    try {
      const url = camId === 'all'
        ? `${API}/api/alerts?limit=50`
        : `${API}/api/alerts?limit=50&cam_id=${camId}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      const incoming = Array.isArray(data) ? data : [];
      const fresh = incoming.filter(a => !seenIds.current.has(a._id));
      fresh.forEach(a => seenIds.current.add(a._id));
      if (fresh.length) setNewCount(n => n + fresh.length);
      setAlerts(incoming);
      setBackendOk(true);
    } catch { setBackendOk(false); }
  }, [camId]);

  const fetchCameras = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/cameras`);
      if (res.ok) setCameras(await res.json());
    } catch (e) { console.error("Failed to fetch cameras", e); }
  }, []);

  useEffect(() => {
    fetchCameras(); loadConfig(); fetchAlerts();
    const es = new EventSource(`${API}/api/alerts/events`);
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.ping) return;
        if (camId !== 'all' && data.cam_id !== camId) return;
        setAlerts((prev) => {
          if (prev.some(a => a._id === data._id)) return prev;
          setNewCount(n => n + 1);
          return [data, ...prev];
        });
        triggerNotifications(data);
      } catch (err) { console.error("Failed to parse SSE message", err); }
    };
    es.onerror = () => console.warn("SSE connection lost. Reconnecting...");
    return () => es.close();
  }, [camId, loadConfig, fetchAlerts, triggerNotifications]);

  const handleClearAlerts = async () => {
    try { await fetch(`${API}/api/alerts`, { method: 'DELETE' }); } catch { }
    setAlerts([]); seenIds.current.clear(); setNewCount(0);
  };

  const activeFeatures = camConfig?.features || [];

  return (
    <Box sx={{ display: 'flex', width: '100%', height: 'calc(100vh - 48px)', overflow: 'hidden', bgcolor: 'background.default' }}>

      {/* ══ LEFT — Camera feed ══ */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 2, overflow: 'hidden', minWidth: 0 }}>
        <Stack direction="row" alignItems="center" spacing={1.5} mb={1.5} flexWrap="wrap">
          <Videocam fontSize="small" sx={{ color: '#00b0ff' }} />
          <select value={camId} onChange={e => handleCamChange(e.target.value)}
            style={{
              background: isDark ? 'rgba(255,255,255,0.05)' : '#ffffff', 
              color: isDark ? '#ffffff' : '#1e293b',
              border: isDark ? '1px solid rgba(255,255,255,0.2)' : '1px solid rgba(0,0,0,0.1)', 
              borderRadius: 6,
              padding: '4px 10px', fontSize: '0.85rem', cursor: 'pointer', outline: 'none',
            }}>
            <option value="all" style={{ background: isDark ? '#1e1e1e' : '#fff', color: isDark ? '#fff' : '#000' }}>All Cameras</option>
            {cameras.map(c => <option key={c.id} value={c.id} style={{ background: isDark ? '#1e1e1e' : '#fff', color: isDark ? '#fff' : '#000' }}>{c.name || c.id}</option>)}
          </select>

          {camId !== 'all' && (
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <Select multiple displayEmpty value={activeFeatures}
                onChange={handleFeatureChange} disabled={isUpdatingFeatures}
                renderValue={(selected) => selected.length === 0 ? <em>No AI Selected</em> : `${selected.length} AI Feature(s)`}
                sx={{ bgcolor: isDark ? 'rgba(255,255,255,0.05)' : '#ffffff', borderRadius: 1.5, fontSize: '0.85rem', '& .MuiOutlinedInput-notchedOutline': { borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.1)' } }}>
                {Object.keys(FEATURE_META).map((key) => (
                  <MenuItem key={key} value={key}>
                    <Checkbox checked={activeFeatures.indexOf(key) > -1} size="small" />
                    <ListItemText primary={FEATURE_META[key].label} primaryTypographyProps={{ fontSize: '0.85rem' }} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          <Typography variant="h6" fontWeight={700} noWrap>
            {camConfig?.name || camId}
          </Typography>

          <Box sx={{
            width: 8, height: 8, borderRadius: '50%',
            bgcolor: (camId !== 'all' && streamError) ? '#f44336' : '#69f0ae',
            animation: (camId !== 'all' && streamError) ? 'none' : 'blink 2s infinite',
            '@keyframes blink': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.3 } },
          }} />
          <Typography variant="caption" sx={{ color: (camId !== 'all' && streamError) ? 'error.main' : '#69f0ae' }}>
            {(camId !== 'all' && streamError) ? 'Stream offline' : 'AI Engine Live'}
          </Typography>

          {!backendOk && <Chip label="Backend offline" size="small" color="error" variant="outlined" />}
          <Box flex={1} />

          {streamActive ? (
            <Button size="small" variant="outlined" color="error"
              startIcon={<Stop fontSize="small" />} onClick={stopStream}
              sx={{ fontSize: '0.75rem' }}>Stop Feed</Button>
          ) : (
            <Button size="small" variant="outlined" color="primary"
              startIcon={<PlayArrow fontSize="small" />} onClick={startStream}
              sx={{ fontSize: '0.75rem' }}>Start Feed</Button>
          )}
        </Stack>

        <Box sx={{
          flex: 1, borderRadius: 2, overflow: 'hidden',
          border: streamActive && !streamError ? '2px solid #00b0ff' : '2px solid rgba(0,0,0,0.07)',
          bgcolor: streamActive ? '#000' : 'background.paper', position: 'relative',
          boxShadow: '0 4px 20px rgba(0,0,0,0.05)'
        }}>
          {camId !== 'all' && streamActive && !streamError && activeFeatures.length > 0 && (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{
              position: 'absolute', top: 16, left: 16, zIndex: 10,
              background: isDark ? 'rgba(0,0,0,0.7)' : 'rgba(255,255,255,0.85)', backdropFilter: 'blur(8px)',
              p: 0.75, borderRadius: 2, border: isDark ? '1px solid rgba(255,255,255,0.1)' : '1px solid rgba(0,0,0,0.1)'
            }}>
              <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ mr: 0.5, display: 'flex', alignItems: 'center' }}>
                ACTIVE AI:
              </Typography>
              {activeFeatures.map(f => {
                const m = FEATURE_META[f] || { label: f, color: '#888' };
                return (
                  <Chip key={f} size="small"
                    icon={<Box sx={{ color: m.color + ' !important', display: 'flex' }}>{m.icon}</Box>}
                    label={m.label}
                    sx={{ bgcolor: m.color + '22', color: m.color, border: `1px solid ${m.color}66`, fontWeight: 700, fontSize: '0.7rem' }}
                  />
                );
              })}
            </Stack>
          )}

          {!streamActive && (
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 2 }}>
              <Videocam sx={{ fontSize: 64, color: 'rgba(255,255,255,0.15)' }} />
              <Typography color="text.disabled" variant="body1" fontWeight={600}>Live feed paused</Typography>
              <Button variant="contained" size="large" startIcon={<PlayArrow />} onClick={startStream}
                sx={{ fontWeight: 700, borderRadius: 2, px: 4, background: 'linear-gradient(135deg,#00b0ff,#00e5ff)', color: '#000', boxShadow: '0 4px 24px #00b0ff55' }}>
                Start Live Feed
              </Button>
              <Typography variant="caption" color="text.disabled">
                AI engine must be running for annotated feed
              </Typography>
            </Box>
          )}

          {streamActive && camId === 'all' && (
            <Box sx={{
              display: 'grid',
              gridTemplateColumns: cameras.length <= 1 ? '1fr' : cameras.length <= 4 ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
              gap: 1.5, p: 1.5, width: '100%', height: '100%', overflowY: 'auto'
            }}>
              {cameras.map(c => (
                <CameraGridItem key={c.id} camId={c.id} label={c.name || c.id}
                  streamActive={streamActive} streamKey={streamKey} />
              ))}
            </Box>
          )}

          {streamActive && camId !== 'all' && (
            <>
              <img key={streamKey} src={`${API}/api/cameras/${camId}/stream`} alt="Live Camera Feed"
                onError={() => setStreamError(true)} onLoad={() => setStreamError(false)}
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
              {streamError && (
                <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center', bgcolor: 'rgba(0,0,0,0.9)' }}>
                  <Videocam sx={{ fontSize: 56, color: 'text.disabled', mb: 1 }} />
                  <Typography color="text.disabled" fontWeight={600}>Stream not available</Typography>
                  <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5 }}>
                    Start AI engine: cd ai_engine &amp;&amp; python main.py
                  </Typography>
                  <Button size="small" variant="outlined" sx={{ mt: 2 }} onClick={startStream}>Retry</Button>
                </Box>
              )}
            </>
          )}
        </Box>
      </Box>

      {/* ══ RIGHT — Alert panel ══ */}
      <Box sx={{
        width: 400, flexShrink: 0,
        borderLeft: '1px solid', borderColor: 'divider',
        display: 'flex', flexDirection: 'column',
        bgcolor: 'background.paper',
        minHeight: 0, overflow: 'hidden',
      }}>
        <Box sx={{ px: 2.5, pt: 2.5, pb: 1.5 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Stack direction="row" alignItems="center" spacing={1}>
              <Badge badgeContent={newCount} color="error"
                onClick={() => setNewCount(0)} sx={{ cursor: 'pointer' }}>
                <Notifications sx={{ color: '#00b0ff' }} />
              </Badge>
              <Typography variant="subtitle1" fontWeight={700}>Live Alerts</Typography>
            </Stack>
            <Stack direction="row" spacing={0.5}>
              <Tooltip title="Refresh">
                <IconButton size="small" onClick={fetchAlerts}>
                  <Refresh fontSize="small" sx={{ color: 'text.secondary' }} />
                </IconButton>
              </Tooltip>
              <Tooltip title="Clear all">
                <IconButton size="small" onClick={handleClearAlerts}>
                  <DeleteSweep fontSize="small" sx={{ color: 'text.secondary' }} />
                </IconButton>
              </Tooltip>
            </Stack>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Auto-refresh {POLL_MS / 1000}s · {alerts.length} total · {camId === 'all' ? 'All Cameras' : (cameras.find(c => c.id === camId)?.name || camId)}
          </Typography>
        </Box>
        <Divider />

        <Box sx={{
          flex: 1, overflowY: 'auto', px: 1.5, py: 1.5,
          '&::-webkit-scrollbar': { width: 4 },
          '&::-webkit-scrollbar-thumb': { bgcolor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.18)', borderRadius: 4 },
        }}>
          {!backendOk ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              Backend offline — start: cd backend &amp;&amp; python app.py
            </Alert>
          ) : alerts.length === 0 ? (
            <Box sx={{ textAlign: 'center', mt: 6 }}>
              <Shield sx={{ fontSize: 44, color: 'text.disabled', mb: 1, opacity: 0.3 }} />
              <Typography color="text.disabled" variant="body2">No alerts yet</Typography>
              <Typography color="text.disabled" variant="caption">
                Alerts appear here as AI engine detects events
              </Typography>
            </Box>
          ) : (
            alerts.map((alert, idx) => {
              // ── Tampering gets smart card ──────────────────────────────
              if (alert.feature === 'tampering') {
                return <TamperingAlertCard key={alert._id || idx} alert={alert} />;
              }

              // ── All other features — unchanged original rendering ───────
              const meta = FEATURE_META[alert.feature] || { label: alert.feature, color: '#888' };
              const sev  = alert.severity || meta.severity || 'MEDIUM';
              const sc   = SEV_COLOR[sev] || '#888';
              const isMissing = alert.feature === 'missing_person';

              const emptyDuration = (() => {
                if (!alert.empty_seconds) return null;
                const total = Math.round(alert.empty_seconds);
                const mins = Math.floor(total / 60);
                const secs = total % 60;
                if (mins > 0) return `${mins} min ${secs}s`;
                return `${secs}s`;
              })();

              return (
                <Paper key={alert._id || idx} sx={{
                  mb: 1, p: 1.5, borderRadius: 2,
                  border: isMissing ? `2px solid #e040fb` : `1px solid ${sc}44`,
                  bgcolor: isMissing ? '#e040fb1a' : (SEV_BG[sev] || '#88888822'),
                  position: 'relative', overflow: 'hidden',
                  animation: isMissing ? 'missingPulse 2s ease-in-out infinite' : 'none',
                  '@keyframes missingPulse': {
                    '0%, 100%': { boxShadow: '0 0 0 0 #e040fb44' },
                    '50%':      { boxShadow: '0 0 12px 4px #e040fb44' },
                  },
                }}>
                  <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: isMissing ? 4 : 3, bgcolor: isMissing ? '#e040fb' : sc }} />
                  <Box sx={{ pl: 1 }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
                      <Stack direction="row" alignItems="center" spacing={0.75}>
                        <Box sx={{ color: meta.color, display: 'flex' }}>{meta.icon}</Box>
                        <Typography variant="body2" fontWeight={700} sx={{ color: meta.color }}>
                          {isMissing ? '🔴 PERSON MISSING' : meta.label}
                        </Typography>
                      </Stack>
                      <Stack direction="row" alignItems="center" spacing={0.75}>
                        <Chip label={sev} size="small" sx={{
                          height: 18, fontSize: '0.58rem', fontWeight: 700,
                          bgcolor: sc + '22', color: sc, border: `1px solid ${sc}55`,
                        }} />
                        <Typography variant="caption" color="text.disabled">
                          {alert.timestamp ? timeAgo(alert.timestamp) : '—'}
                        </Typography>
                      </Stack>
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      Camera: <strong>{alert.cam_id}</strong>
                      {alert.detections?.length > 0 && ` · ${alert.detections.length} detection(s)`}
                    </Typography>
                    {alert.feature === 'criminal_face' && alert.class && (
                      <Typography variant="caption" display="block" sx={{ color: '#ff6d00', fontWeight: 700, mt: 0.25 }}>
                        ⚠ WATCHLIST MATCH: {alert.class}
                        {alert.confidence && ` (${(alert.confidence * 100).toFixed(0)}% match)`}
                      </Typography>
                    )}
                    {alert.feature === 'weapon_detection' && alert.class && (
                      <Typography variant="caption" display="block" sx={{ color: '#ff1744', fontWeight: 700, mt: 0.25 }}>
                        🔫 {alert.class.toUpperCase()} detected
                        {alert.confidence && ` — ${(alert.confidence * 100).toFixed(1)}% confidence`}
                      </Typography>
                    )}
                    {isMissing && (
                      <Box sx={{ mt: 0.5, p: 0.75, borderRadius: 1, bgcolor: '#e040fb15', border: '1px solid #e040fb33' }}>
                        {alert.zone_name && (
                          <Typography variant="caption" display="block" sx={{ color: '#e040fb', fontWeight: 700 }}>
                            📍 Zone: {alert.zone_name}
                          </Typography>
                        )}
                        {emptyDuration && (
                          <Typography variant="caption" display="block" sx={{ color: '#ff8a80', fontWeight: 600, mt: 0.25 }}>
                            ⏱ Empty for: {emptyDuration}
                          </Typography>
                        )}
                        {alert.message && (
                          <Typography variant="caption" display="block"
                            sx={{ color: '#e040fb', opacity: 0.85, mt: 0.5, fontSize: '0.65rem', fontStyle: 'italic' }}>
                            {alert.message}
                          </Typography>
                        )}
                      </Box>
                    )}
                    {alert.feature === 'perimeter' && (
                      <Typography variant="caption" display="block" sx={{ color: '#ff4081', fontWeight: 700, mt: 0.25 }}>
                        {alert.alert_type === 'animal' ? '🐾 Animal' : '🚨 Person'} crossed perimeter
                        {alert.class ? ` — ${alert.class.charAt(0).toUpperCase() + alert.class.slice(1)}` : ''}
                        {alert.track_id != null ? ` (track #${alert.track_id})` : ''}
                      </Typography>
                    )}
                    {alert.message && !['criminal_face','weapon_detection','missing_person','perimeter'].includes(alert.feature) && (
                      <Typography variant="caption" display="block" color="text.disabled" sx={{ mt: 0.25 }}>
                        {alert.message}
                      </Typography>
                    )}
                  </Box>
                </Paper>
              );
            })
          )}
        </Box>

        {alerts.length > 0 && (
          <>
            <Divider />
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
                Breakdown:
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={0.75} useFlexGap>
                {Object.entries(
                  alerts.reduce((acc, a) => { acc[a.feature] = (acc[a.feature] || 0) + 1; return acc; }, {})
                ).map(([feat, count]) => {
                  const m = FEATURE_META[feat] || { label: feat, color: '#888' };
                  return (
                    <Chip key={feat} size="small" label={`${m.label}: ${count}`} sx={{
                      height: 20, fontSize: '0.65rem',
                      bgcolor: m.color + '18', color: m.color, border: `1px solid ${m.color}44`,
                    }} />
                  );
                })}
              </Stack>
            </Box>
          </>
        )}
      </Box>

      {/* ── Popup snackbar ── */}
      <Snackbar
        open={popupAlert.open}
        autoHideDuration={4000}
        onClose={() => setPopupAlert(p => ({ ...p, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert severity={popupAlert.severity} onClose={() => setPopupAlert(p => ({ ...p, open: false }))}>
          {popupAlert.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}