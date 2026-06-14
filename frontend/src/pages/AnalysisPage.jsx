import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Grid, Paper, Stack, CircularProgress, Alert, Divider
} from '@mui/material';
import {
  ArrowDownward, ArrowUpward, People, Analytics
} from '@mui/icons-material';

const API = 'http://localhost:5050';

function MetricCard({ label, value, icon, color = '#00e5ff', subtitle }) {
  return (
    <Paper sx={{
      p: 3, textAlign: 'center',
      bgcolor: 'background.paper',
      border: `1px solid ${color}20`,
      borderTop: `3px solid ${color}`,
      borderRadius: 2,
      transition: 'transform 0.2s',
      '&:hover': { transform: 'translateY(-2px)' }
    }}>
      <Box sx={{ color: color, mb: 1 }}>{icon}</Box>
      <Typography variant="h3" fontWeight={800} sx={{ color, lineHeight: 1 }}>
        {value ?? '—'}
      </Typography>
      <Typography variant="subtitle2" fontWeight={600} mt={0.5}>{label}</Typography>
      {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
    </Paper>
  );
}

function FeatureBar({ label, count, total, color }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <Box mb={1.5}>
      <Stack direction="row" justifyContent="space-between" mb={0.5}>
        <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
          {label.replace(/_/g, ' ')}
        </Typography>
        <Typography variant="body2" fontWeight={700} color={color || 'text.primary'}>
          {count}
        </Typography>
      </Stack>
      <Box sx={{ height: 6, bgcolor: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: color || '#00e5ff', borderRadius: 3, transition: 'width 0.5s' }} />
      </Box>
    </Box>
  );
}

const FEATURE_COLORS = {
  fire_smoke: '#ff1744', intrusion: '#ff6d00', loitering: '#ffd600',
  no_go_zone: '#ff1744', crowd: '#76ff03', footfall: '#00b0ff',
  perimeter: '#ff4081', missing_person: '#e040fb',
  personal_monitoring: '#00e5ff', tampering: '#aa00ff',
};

export default function AnalysisPage() {
  const [stats,   setStats]   = useState(null);
  const [alerts,  setAlerts]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/alerts/stats`).then(r => r.json()),
      fetch(`${API}/api/alerts?limit=200`).then(r => r.json()),
    ])
      .then(([statsData, alertsData]) => {
        setStats(statsData);
        setAlerts(alertsData);
        setLoading(false);
      })
      .catch(err => { setError(err.message); setLoading(false); });
  }, []);

  if (loading) return <Box p={4} textAlign="center"><CircularProgress /></Box>;
  if (error)   return <Box p={4}><Alert severity="warning">Backend unavailable: {error}</Alert></Box>;

  const featureCounts = stats?.last_24h || {};
  const totalAlerts   = Object.values(featureCounts).reduce((s, v) => s + v, 0);

  const footfallAlerts = alerts.filter(a => a.feature === 'footfall');
  const footfallIn  = footfallAlerts.filter(a => a.detections?.[0]?.direction === 'in').length;
  const footfallOut = footfallAlerts.filter(a => a.detections?.[0]?.direction === 'out').length;

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} mb={3}>
        <Analytics sx={{ mr: 1, verticalAlign: 'middle' }} />
        Analysis
      </Typography>

      {/* Footfall cards */}
      <Typography variant="subtitle1" fontWeight={700} mb={2} color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.75rem' }}>
        Footfall (This Session)
      </Typography>
      <Grid container spacing={2} mb={4}>
        <Grid item xs={12} sm={4}>
          <MetricCard label="Total Count"   value={footfallIn + footfallOut} icon={<People sx={{ fontSize: 32 }} />} color="#00e5ff" subtitle="All crossings" />
        </Grid>
        <Grid item xs={12} sm={4}>
          <MetricCard label="Entries (IN)"  value={footfallIn}  icon={<ArrowDownward sx={{ fontSize: 32 }} />} color="#00e676" subtitle="Entered zone" />
        </Grid>
        <Grid item xs={12} sm={4}>
          <MetricCard label="Exits (OUT)"   value={footfallOut} icon={<ArrowUpward sx={{ fontSize: 32 }} />}   color="#ff6d00" subtitle="Left zone" />
        </Grid>
      </Grid>

      <Divider sx={{ mb: 3, borderColor: 'rgba(255,255,255,0.06)' }} />

      {/* Alerts by feature (last 24h) */}
      <Typography variant="subtitle1" fontWeight={700} mb={2} color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.75rem' }}>
        Alerts by Feature (Last 24 Hours)
      </Typography>

      {totalAlerts === 0
        ? <Typography color="text.secondary" variant="body2">No alerts in past 24 hours.</Typography>
        : (
          <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 2 }}>
            <Stack direction="row" justifyContent="space-between" mb={2}>
              <Typography variant="body2" color="text.secondary">Feature</Typography>
              <Typography variant="body2" color="text.secondary">Count / {totalAlerts} total</Typography>
            </Stack>
            {Object.entries(featureCounts)
              .sort(([,a],[,b]) => b - a)
              .map(([feature, count]) => (
                <FeatureBar
                  key={feature}
                  label={feature}
                  count={count}
                  total={totalAlerts}
                  color={FEATURE_COLORS[feature]}
                />
              ))
            }
          </Paper>
        )
      }
    </Box>
  );
}
