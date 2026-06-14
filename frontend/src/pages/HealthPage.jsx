import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Grid, Paper, Stack, Chip,
  CircularProgress, Alert, LinearProgress
} from '@mui/material';
import { Videocam, Memory, Storage, CheckCircle, Error, Warning } from '@mui/icons-material';

const API = 'http://localhost:5050';

function HealthCard({ title, icon, children, status = 'ok' }) {
  const borderColor = status === 'ok' ? '#4caf50' : status === 'warn' ? '#ffd600' : '#f44336';
  return (
    <Paper sx={{
      p: 2.5,
      bgcolor: 'background.paper',
      border: `1px solid rgba(255,255,255,0.06)`,
      borderLeft: `3px solid ${borderColor}`,
      borderRadius: 2,
    }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={2}>
        <Box sx={{ color: borderColor }}>{icon}</Box>
        <Typography variant="subtitle2" fontWeight={700}>{title}</Typography>
        <Chip
          label={status.toUpperCase()}
          size="small"
          sx={{ ml: 'auto', color: borderColor, bgcolor: `${borderColor}15`, border: `1px solid ${borderColor}30`, fontWeight: 700, fontSize: '0.65rem', height: 20 }}
        />
      </Stack>
      {children}
    </Paper>
  );
}

function StatRow({ label, value, unit = '', warn = false }) {
  return (
    <Stack direction="row" justifyContent="space-between" mb={0.5}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" fontWeight={600} color={warn ? '#ffd600' : 'text.primary'}>
        {value}{unit}
      </Typography>
    </Stack>
  );
}

export default function HealthPage() {
  const [health,  setHealth]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const fetchHealth = () => {
    fetch(`${API}/health`)
      .then(r => r.json())
      .then(data => { setHealth(data); setLoading(false); setError(null); })
      .catch(err  => { setError(err.message); setLoading(false); });
  };

  useEffect(() => {
    fetchHealth();
    const iv = setInterval(fetchHealth, 5000);
    return () => clearInterval(iv);
  }, []);

  if (loading) return <Box p={4} textAlign="center"><CircularProgress /></Box>;

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} mb={3}>System Health</Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Backend is offline or not reachable at {API}. Start the Flask backend: <code>cd backend && python app.py</code>
        </Alert>
      )}

      {health && (
        <>
          {/* Overall status */}
          <Paper sx={{ p: 2.5, mb: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2 }}>
            <Stack direction="row" alignItems="center" spacing={2}>
              {health.mongodb === 'connected'
                ? <CheckCircle sx={{ color: '#4caf50', fontSize: 32 }} />
                : <Warning sx={{ color: '#ffd600', fontSize: 32 }} />
              }
              <Box>
                <Typography variant="h6" fontWeight={700}>
                  Backend: {health.status?.toUpperCase()}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {new Date(health.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false })}
                </Typography>
              </Box>
            </Stack>
          </Paper>

          <Grid container spacing={3}>
            {/* MongoDB */}
            <Grid item xs={12} sm={6} md={4}>
              <HealthCard
                title="Database (MongoDB)"
                icon={<Storage />}
                status={health.mongodb === 'connected' ? 'ok' : 'error'}
              >
                <StatRow label="Status"  value={health.mongodb} />
                <StatRow label="URI"     value="localhost:27017" />
                <StatRow label="DB"      value="expert_cctv" />
              </HealthCard>
            </Grid>

            {/* Camera status */}
            {health.cameras && Object.entries(health.cameras).map(([cam_id, cam]) => (
              <Grid item xs={12} sm={6} md={4} key={cam_id}>
                <HealthCard
                  title={cam_id}
                  icon={<Videocam />}
                  status={cam.online ? 'ok' : 'error'}
                >
                  <StatRow label="Online"     value={cam.online ? 'Yes' : 'No'} warn={!cam.online} />
                  <StatRow label="FPS"        value={cam.fps || '—'} />
                  <StatRow label="Last frame" value={cam.last_frame !== undefined ? `${cam.last_frame}s ago` : '—'} warn={(cam.last_frame || 0) > 5} />
                </HealthCard>
              </Grid>
            ))}

            {/* GPU / System — shown if available */}
            {health.gpu && (
              <Grid item xs={12} sm={6} md={4}>
                <HealthCard
                  title="GPU"
                  icon={<Memory />}
                  status={health.gpu.temperature > 80 ? 'warn' : 'ok'}
                >
                  <StatRow label="Temperature" value={health.gpu.temperature}  unit="°C" warn={health.gpu.temperature > 75} />
                  <StatRow label="Load"        value={health.gpu.load_percent} unit="%" />
                  <StatRow label="VRAM Used"   value={health.gpu.memory_used}  unit=" GB" />
                </HealthCard>
              </Grid>
            )}
          </Grid>

          <Box mt={3}>
            <Typography variant="caption" color="text.disabled">
              Auto-refreshes every 5 seconds. If camera data is missing, the AI engine is not connected to the backend yet.
            </Typography>
          </Box>
        </>
      )}

      {!health && !error && (
        <Alert severity="info">Waiting for backend response...</Alert>
      )}
    </Box>
  );
}
