import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Stack, Chip, Paper, IconButton, Tooltip,
  CircularProgress, Divider, Select, MenuItem, FormControl,
  InputLabel, Badge, Fade, Dialog, DialogContent, Button
} from '@mui/material';
import {
  LocalFireDepartment, PersonOff, DirectionsWalk, NoPhotography,
  Groups, Login, SentimentVeryDissatisfied, Videocam, Refresh,
  Delete, PlayCircle, Image, Warning, Shield, GpsFixed,
  Person, FilterList, ZoomIn, Close, DeleteSweep, FiberManualRecord,
  Pets, DirectionsCar
} from '@mui/icons-material';
import { useTheme } from '@mui/material/styles';

const API = 'http://localhost:5050';

const FEATURE_META = {
  fire_smoke:          { label: 'Fire & Smoke',       icon: <LocalFireDepartment />, color: '#ff3d00', sev: 'CRITICAL' },
  no_go_zone:          { label: 'No-Go Zone',          icon: <NoPhotography />,       color: '#ff1744', sev: 'CRITICAL' },
  weapon_detection:    { label: 'Weapon Detected',     icon: <Warning />,             color: '#ff1744', sev: 'CRITICAL' },
  criminal_face:       { label: 'Criminal Face ID',    icon: <Person />,              color: '#ff6d00', sev: 'CRITICAL' },
  intrusion:           { label: 'Intrusion',           icon: <PersonOff />,           color: '#ff6d00', sev: 'HIGH'     },
  perimeter:           { label: 'Perimeter Breach',    icon: <Login />,               color: '#ff4081', sev: 'HIGH'     },
  missing_person:      { label: 'Person Missing',      icon: <SentimentVeryDissatisfied />, color: '#e040fb', sev: 'HIGH' },
  tampering:           { label: 'Tampering',           icon: <Videocam />,            color: '#aa00ff', sev: 'HIGH'     },
  loitering:           { label: 'Loitering',           icon: <DirectionsWalk />,      color: '#ffd600', sev: 'MEDIUM'   },
  crowd:               { label: 'Crowd Alert',         icon: <Groups />,              color: '#76ff03', sev: 'MEDIUM'   },
  personal_monitoring: { label: 'Personal Monitor',    icon: <GpsFixed />,            color: '#00e5ff', sev: 'MEDIUM'   },
  footfall:            { label: 'Footfall',            icon: <DirectionsWalk />,      color: '#00b0ff', sev: 'LOW'      },
  animal_detection:    { label: 'Animal Alert',        icon: <Pets />,                color: '#22c822', sev: 'HIGH'     },
  vehicle_detection:   { label: 'Vehicle Alert',       icon: <DirectionsCar />,       color: '#00ffff', sev: 'MEDIUM'   },
};

const SEV_COLOR = { CRITICAL: '#ff1744', HIGH: '#ff6d00', MEDIUM: '#ffd600', LOW: '#00b0ff' };

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60)   return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function fmtSize(kb) {
  if (kb > 1024) return `${(kb / 1024).toFixed(1)} MB`;
  return `${kb} KB`;
}

// ─── Alert row in the list ─────────────────────────────────────────────────
function AlertRow({ clip, selected, onClick }) {
  const meta = FEATURE_META[clip.feature] || { label: clip.feature, icon: <Shield />, color: '#78909c', sev: 'MEDIUM' };
  const isSelected = selected?.filename === clip.filename;
  const clipSev = clip.severity || meta.sev || 'MEDIUM';

  return (
    <Paper
      onClick={onClick}
      sx={{
        p: 1.25, cursor: 'pointer', borderRadius: 1.5,
        border: isSelected ? `1px solid ${meta.color}88` : '1px solid rgba(255,255,255,0.05)',
        bgcolor: isSelected ? `${meta.color}14` : 'background.paper',
        borderLeft: `3px solid ${meta.color}`,
        transition: 'all 0.15s',
        '&:hover': { bgcolor: `${meta.color}10`, borderColor: `${meta.color}55` },
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1.25}>
        {/* Feature icon */}
        <Box sx={{ color: meta.color, display: 'flex', flexShrink: 0, fontSize: 18 }}>
          {meta.icon}
        </Box>

        {/* Info */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <Typography variant="body2" fontWeight={700} sx={{ color: meta.color, fontSize: '0.78rem' }}>
              {meta.label}
            </Typography>
            <Chip
              label={clipSev}
              size="small"
              sx={{
                height: 15, fontSize: '0.52rem', fontWeight: 700,
                bgcolor: SEV_COLOR[clipSev] + '22', color: SEV_COLOR[clipSev],
                border: `1px solid ${SEV_COLOR[clipSev]}44`,
              }}
            />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.68rem' }}>
            {clip.cam_id} · {clip.date_label} {clip.time_label}
          </Typography>
        </Box>

        {/* Media type badges + size */}
        <Stack alignItems="flex-end" spacing={0.25} sx={{ flexShrink: 0 }}>
          <Stack direction="row" spacing={0.5}>
            {clip.has_image && <Image sx={{ fontSize: 13, color: '#00e5ff' }} />}
            {clip.has_video && <PlayCircle sx={{ fontSize: 13, color: '#69f0ae' }} />}
          </Stack>
          <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.6rem' }}>
            {fmtSize(clip.size_kb)}
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}

// ─── Main component ────────────────────────────────────────────────────────
export default function AlertsDashboard() {
  const [clips,     setClips]     = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const [selected,  setSelected]  = useState(null);
  const [featFilter, setFeatFilter] = useState('all');
  const [camFilter,  setCamFilter]  = useState('all');
  const [lightbox,  setLightbox]  = useState(false);
  const videoRef = useRef(null);
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const [cameras, setCameras] = useState([]);

  const fetchCameras = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/cameras`);
      if (res.ok) setCameras(await res.json());
    } catch (e) { console.error("Failed to fetch cameras", e); }
  }, []);

  const fetchClips = useCallback(async () => {
    try {
      const res  = await fetch(`${API}/api/clips?limit=200`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setClips(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCameras(); fetchClips(); }, [fetchCameras, fetchClips]);

  // Auto-select first clip
  useEffect(() => {
    if (clips.length > 0 && !selected) setSelected(clips[0]);
  }, [clips]);

  const handleDelete = async (clip) => {
    const fn = clip.filename || clip.image_url?.split('/').pop() || clip.video_url?.split('/').pop();
    if (!fn) return;
    await fetch(`${API}/api/clips/${fn}`, { method: 'DELETE' });
    setClips(prev => prev.filter(c => c.filename !== clip.filename));
    if (selected?.filename === clip.filename) setSelected(null);
  };

  const handleDeleteAll = useCallback(async () => {
    try {
      await fetch(`${API}/api/alerts`, { method: 'DELETE' });
    } catch { /* ignore network errors */ }
    setClips([]);
    if (selected) setSelected(null);
  }, [selected]);

  const handleDeleteByFeature = useCallback(async (feature) => {
    try {
      await fetch(`${API}/api/alerts?feature=${feature}`, { method: 'DELETE' });
    } catch { /* ignore */ }
    setClips(prev => prev.filter(a => a.feature !== feature));
    if (selected?.feature === feature) setSelected(null);
  }, [selected]);

  // Derived lists
  const allFeatures = [...new Set(clips.map(c => c.feature))].sort();

  const visible = clips.filter(c =>
    (featFilter === 'all' || c.feature === featFilter) &&
    (camFilter  === 'all' || c.cam_id  === camFilter)
  );

  // Stats
  const stats = {
    CRITICAL: visible.filter(c => c.severity === 'CRITICAL').length,
    HIGH:     visible.filter(c => c.severity === 'HIGH').length,
    MEDIUM:   visible.filter(c => c.severity === 'MEDIUM').length,
    LOW:      visible.filter(c => c.severity === 'LOW').length,
    total:    visible.length,
  };

  const selMeta = selected ? (FEATURE_META[selected.feature] || { label: selected.feature, color: '#78909c' }) : null;
  const selSev = selected?.severity || selMeta?.sev || 'MEDIUM';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 48px)', bgcolor: 'background.default', overflow: 'hidden' }}>

      {/* ── TOP BAR ── */}
      <Box sx={{ px: 2.5, py: 1.25, borderBottom: '1px solid', borderColor: 'divider', flexShrink: 0 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1} mb={allFeatures.length > 0 ? 1 : 0}>

          {/* Title + stats */}
          <Stack direction="row" alignItems="center" spacing={2}>
            <Typography variant="h6" fontWeight={800} sx={{ fontSize: '1rem', display: 'flex', alignItems: 'center' }}>
              <FiberManualRecord sx={{ color: '#f44336', fontSize: 14, mr: 1, animation: 'pulse 1s infinite' }} />
              Alert History
            </Typography>
            <Stack direction="row" spacing={1}>
              {Object.entries({ CRITICAL: '#ff1744', HIGH: '#ff6d00', MEDIUM: '#ffd600', LOW: '#00b0ff' }).map(([k, c]) => (
                <Chip key={k} label={`${k} ${stats[k]}`} size="small" sx={{
                  height: 20, fontSize: '0.6rem', fontWeight: 700,
                  bgcolor: c + '18', color: c, border: `1px solid ${c}44`,
                }} />
              ))}
            </Stack>
          </Stack>

          {/* Filters + refresh */}
          <Stack direction="row" spacing={1} alignItems="center">
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <Select value={camFilter} onChange={e => setCamFilter(e.target.value)}
                sx={{ fontSize: '0.72rem', height: 30 }}>
                <MenuItem value="all">All Cams</MenuItem>
                {cameras.map(c => <MenuItem key={c.id} value={c.id}>{c.name || c.id}</MenuItem>)}
              </Select>
            </FormControl>
            <Tooltip title="Refresh now">
              <IconButton size="small" onClick={fetchClips} sx={{ color: 'primary.main' }}>
                <Refresh fontSize="small" />
              </IconButton>
            </Tooltip>
            {clips.length > 0 && (
              <Tooltip title="Delete all alerts permanently">
                <Button
                  id="delete-all-alerts-btn"
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteSweep fontSize="small" />}
                  onClick={handleDeleteAll}
                  sx={{ fontWeight: 600, fontSize: '0.75rem' }}
                >
                  Delete All
                </Button>
              </Tooltip>
            )}
          </Stack>
        </Stack>
        
        {/* Feature Filters row (replaces the Select for features) */}
        {allFeatures.length > 0 && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            <Chip
              label={`All (${clips.length})`}
              onClick={() => setFeatFilter('all')}
              variant={featFilter === 'all' ? 'filled' : 'outlined'}
              sx={{
                borderColor: 'primary.main',
                color: featFilter === 'all' ? 'primary.contrastText' : 'primary.main',
                bgcolor: featFilter === 'all' ? 'primary.main' : 'transparent',
                fontWeight: 600,
              }}
            />
            {allFeatures.map(f => {
              const cfg = FEATURE_META[f] || { label: f, color: '#78909c' };
              const count = clips.filter(c => c.feature === f).length;
              return (
                <Box key={f} sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                  <Chip
                    label={`${cfg.label} (${count})`}
                    onClick={() => setFeatFilter(f)}
                    variant={featFilter === f ? 'filled' : 'outlined'}
                    sx={{
                      borderColor: cfg.color,
                      color: featFilter === f ? (isDark ? '#000' : '#fff') : cfg.color,
                      bgcolor: featFilter === f ? cfg.color : 'transparent',
                      fontWeight: 600,
                    }}
                  />
                  <Tooltip title={`Delete all ${cfg.label} alerts`}>
                    <IconButton
                      id={`delete-type-${f}-btn`}
                      size="small"
                      onClick={() => handleDeleteByFeature(f)}
                      sx={{
                        color: 'error.main',
                        opacity: 0.6,
                        p: 0.25,
                        '&:hover': { opacity: 1, bgcolor: 'error.main', color: '#fff' },
                        transition: 'all 0.15s',
                      }}
                    >
                      <Delete sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Tooltip>
                </Box>
              );
            })}
          </Stack>
        )}
      </Box>

      {/* ── BODY: list + viewer ── */}
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* LEFT: scrollable alert list */}
        <Box sx={{
          width: 320, flexShrink: 0,
          borderRight: '1px solid', borderColor: 'divider',
          overflowY: 'auto', p: 1,
          '&::-webkit-scrollbar': { width: 4 },
          '&::-webkit-scrollbar-thumb': { bgcolor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.18)', borderRadius: 4 },
        }}>
          {loading && (
            <Box textAlign="center" pt={4}><CircularProgress size={28} /></Box>
          )}
          {error && (
            <Typography color="error" variant="caption" sx={{ p: 1, display: 'block' }}>
              {error}
            </Typography>
          )}
          {!loading && !error && visible.length === 0 && (
            <Box textAlign="center" pt={6}>
              <Typography sx={{ fontSize: '2rem', opacity: 0.2 }}>📭</Typography>
              <Typography variant="caption" color="text.disabled">No clips yet</Typography>
            </Box>
          )}
          <Stack spacing={0.6}>
            {visible.map((clip, idx) => (
              <AlertRow
                key={clip.filename || idx}
                clip={clip}
                selected={selected}
                onClick={() => setSelected(clip)}
              />
            ))}
          </Stack>
        </Box>

        {/* RIGHT: media viewer */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', p: 2 }}>
          {!selected ? (
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', opacity: 0.3 }}>
              <Typography sx={{ fontSize: '3rem' }}>🎬</Typography>
              <Typography variant="body2" color="text.secondary">Select an alert to view</Typography>
            </Box>
          ) : (
            <Fade in key={selected.filename}>
              <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>

                {/* Media area */}
                <Box sx={{
                  flex: 1, minHeight: 0, position: 'relative',
                  bgcolor: '#000', borderRadius: 2, overflow: 'hidden',
                  border: `1px solid ${selMeta?.color}33`,
                }}>
                  {/* Prefer video if available, else show image */}
                  {selected.has_video && selected.video_url ? (
                    <Box sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
                      <video
                        ref={videoRef}
                        key={selected.video_url}
                        controls
                        style={{ width: '100%', flex: 1, objectFit: 'contain', minHeight: 0, background: '#000' }}
                      >
                        <source
                          src={`${API}/api/clips/video/${selected.video_url.split('/').pop()}`}
                          type="video/mp4"
                        />
                      </video>
                      {/* Download fallback */}
                      <Box sx={{ py: 0.5, px: 1.5, bgcolor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.62rem' }}>
                          Black screen? Old clip format (mp4v).
                        </Typography>
                        <a
                          href={`${API}/api/clips/video/${selected.video_url.split('/').pop()}`}
                          download
                          style={{ color: '#00b0ff', fontSize: '0.62rem', textDecoration: 'underline' }}
                        >
                          ⬇ Download & open in VLC
                        </a>
                      </Box>
                    </Box>

                  ) : selected.has_image && selected.image_url ? (
                    <img
                      src={`${API}${selected.image_url}`}
                      alt="Alert snapshot"
                      style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                    />
                  ) : (
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                      <Typography color="text.disabled">No media available</Typography>
                    </Box>
                  )}

                  {/* Zoom button for images */}
                  {selected.has_image && selected.image_url && !selected.has_video && (
                    <IconButton
                      size="small"
                      onClick={() => setLightbox(true)}
                      sx={{ position: 'absolute', top: 8, right: 8, bgcolor: 'rgba(0,0,0,0.6)', color: '#fff' }}
                    >
                      <ZoomIn fontSize="small" />
                    </IconButton>
                  )}

                  {/* Feature badge overlay */}
                  <Box sx={{
                    position: 'absolute', top: 10, left: 10,
                    bgcolor: selMeta?.color + 'dd', px: 1, py: 0.25,
                    borderRadius: 1, display: 'flex', alignItems: 'center', gap: 0.5,
                  }}>
                    <Box sx={{ color: '#000', display: 'flex', fontSize: 14 }}>{selMeta?.icon}</Box>
                    <Typography variant="caption" fontWeight={800} sx={{ color: '#000', fontSize: '0.7rem' }}>
                      {selMeta?.label?.toUpperCase()}
                    </Typography>
                  </Box>

                  {/* Toggle: if both video+image exist, show toggle buttons */}
                  {selected.has_video && selected.has_image && (
                    <Stack direction="row" spacing={0.5} sx={{ position: 'absolute', bottom: 10, right: 10 }}>
                      <Chip
                        icon={<PlayCircle sx={{ fontSize: 12 }} />}
                        label="Video"
                        size="small"
                        onClick={() => setSelected({ ...selected, _view: 'video' })}
                        sx={{ bgcolor: 'rgba(0,0,0,0.7)', color: '#69f0ae', fontSize: '0.62rem', height: 22 }}
                      />
                      <Chip
                        icon={<Image sx={{ fontSize: 12 }} />}
                        label="Snapshot"
                        size="small"
                        onClick={() => setSelected({ ...selected, _view: 'image' })}
                        sx={{ bgcolor: 'rgba(0,0,0,0.7)', color: '#00e5ff', fontSize: '0.62rem', height: 22 }}
                      />
                    </Stack>
                  )}
                </Box>

                {/* Alert metadata card */}
                <Paper sx={{
                  p: 1.75, borderRadius: 2, flexShrink: 0,
                  bgcolor: 'background.paper',
                  border: `1px solid ${selMeta?.color}22`,
                }}>
                  <Stack direction="row" alignItems="flex-start" justifyContent="space-between">
                    <Box>
                      <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
                        <Typography variant="subtitle1" fontWeight={800} sx={{ color: selMeta?.color, fontSize: '0.9rem' }}>
                          {selMeta?.label}
                        </Typography>
                        <Chip label={selSev} size="small" sx={{
                          height: 18, fontSize: '0.6rem', fontWeight: 800,
                          bgcolor: SEV_COLOR[selSev] + '22', color: SEV_COLOR[selSev],
                          border: `1px solid ${SEV_COLOR[selSev]}44`,
                        }} />
                        {selected.has_video && <Chip icon={<PlayCircle sx={{ fontSize: 11 }} />} label="Clip" size="small" sx={{ height: 18, fontSize: '0.6rem', color: '#69f0ae', bgcolor: '#69f0ae18', border: '1px solid #69f0ae33' }} />}
                        {selected.has_image && <Chip icon={<Image sx={{ fontSize: 11 }} />} label="Snapshot" size="small" sx={{ height: 18, fontSize: '0.6rem', color: '#00e5ff', bgcolor: '#00e5ff18', border: '1px solid #00e5ff33' }} />}
                      </Stack>
                      <Stack direction="row" spacing={2.5} flexWrap="wrap">
                        <Box>
                          <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>Camera</Typography>
                          <Typography variant="body2" fontWeight={700} sx={{ fontSize: '0.8rem' }}>{selected.cam_id}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>Date</Typography>
                          <Typography variant="body2" fontWeight={700} sx={{ fontSize: '0.8rem' }}>{selected.date_label}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>Time</Typography>
                          <Typography variant="body2" fontWeight={700} sx={{ fontSize: '0.8rem' }}>{selected.time_label}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>Size</Typography>
                          <Typography variant="body2" fontWeight={700} sx={{ fontSize: '0.8rem' }}>{fmtSize(selected.size_kb)}</Typography>
                        </Box>
                      </Stack>
                      
                      {/* Dynamic Message */}
                      {selected.message && (
                        <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 1, fontSize: '0.75rem', fontWeight: 500 }}>
                          {selected.message}
                        </Typography>
                      )}
                    </Box>

                    {/* Delete */}
                    <Tooltip title="Delete this clip">
                      <IconButton size="small" onClick={() => handleDelete(selected)}
                        sx={{ color: '#f44336', opacity: 0.6, '&:hover': { opacity: 1 } }}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Paper>

              </Box>
            </Fade>
          )}
        </Box>
      </Box>

      {/* Lightbox for full-res image */}
      <Dialog open={lightbox} onClose={() => setLightbox(false)} maxWidth="xl"
        PaperProps={{ sx: { bgcolor: '#000', boxShadow: 'none' } }}>
        <IconButton onClick={() => setLightbox(false)}
          sx={{ position: 'absolute', top: 8, right: 8, color: '#fff', zIndex: 1 }}>
          <Close />
        </IconButton>
        <DialogContent sx={{ p: 0 }}>
          {selected?.image_url && (
            <img src={`${API}${selected.image_url}`} alt="Alert snapshot"
              style={{ maxWidth: '90vw', maxHeight: '90vh', display: 'block' }} />
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
