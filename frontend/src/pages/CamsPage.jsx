import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Grid, Card, CardContent, CardActions,
  Button, Chip, Stack, Paper, CircularProgress, Alert
} from '@mui/material';
import { Videocam, Settings, CheckCircle, Error } from '@mui/icons-material';
import { Link } from 'react-router-dom';

const API = 'http://localhost:5050';

const FEATURE_COLORS = {
  fire_smoke: '#ff1744', intrusion: '#ff6d00', loitering: '#ffd600',
  no_go_zone: '#ff1744', crowd: '#76ff03', footfall: '#00b0ff',
  perimeter: '#ff4081', missing_person: '#e040fb',
  personal_monitoring: '#00e5ff', tampering: '#aa00ff',
};

export default function CamsPage() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    fetch(`${API}/api/cameras`)
      .then(r => r.json())
      .then(data => { setCameras(data); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, []);

  if (loading) return <Box p={4} textAlign="center"><CircularProgress /></Box>;
  if (error)   return <Box p={4}><Alert severity="warning">Backend unavailable: {error}</Alert></Box>;

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} mb={3}>Camera Management</Typography>

      <Grid container spacing={3}>
        {cameras.map(cam => (
          <Grid item xs={12} sm={6} md={4} key={cam.id}>
            <Card sx={{
              bgcolor: 'background.paper',
              border: '1px solid rgba(255,255,255,0.06)',
              height: '100%',
              display: 'flex', flexDirection: 'column',
              transition: 'transform 0.2s, box-shadow 0.2s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: '0 12px 40px rgba(0,229,255,0.1)' },
            }}>
              <CardContent sx={{ flexGrow: 1 }}>
                {/* Header */}
                <Stack direction="row" alignItems="center" spacing={1.5} mb={2}>
                  <Box sx={{ bgcolor: 'rgba(0,229,255,0.1)', borderRadius: 1.5, p: 1, display: 'flex' }}>
                    <Videocam sx={{ color: 'primary.main' }} />
                  </Box>
                  <Box>
                    <Typography variant="subtitle1" fontWeight={700}>{cam.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Source: {typeof cam.source === 'number' ? `Webcam ${cam.source}` : cam.source}
                    </Typography>
                  </Box>
                  <Chip
                    icon={<CheckCircle sx={{ fontSize: '14px !important' }} />}
                    label="Active"
                    size="small"
                    sx={{ ml: 'auto', bgcolor: 'rgba(76,175,80,0.15)', color: '#4caf50', border: '1px solid #4caf5040' }}
                  />
                </Stack>

                {/* Stats */}
                <Stack direction="row" spacing={2} mb={2}>
                  <Paper sx={{ flex: 1, p: 1.5, textAlign: 'center', bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1.5 }}>
                    <Typography variant="h6" fontWeight={700} color="primary.main">
                      {cam.fps_limit || 10}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">FPS Limit</Typography>
                  </Paper>
                  <Paper sx={{ flex: 1, p: 1.5, textAlign: 'center', bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1.5 }}>
                    <Typography variant="h6" fontWeight={700} color="primary.main">
                      {(cam.zones || []).length}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">Zones</Typography>
                  </Paper>
                  <Paper sx={{ flex: 1, p: 1.5, textAlign: 'center', bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1.5 }}>
                    <Typography variant="h6" fontWeight={700} color="primary.main">
                      {(cam.features || []).length}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">Features</Typography>
                  </Paper>
                </Stack>

                {/* Feature chips */}
                <Stack direction="row" flexWrap="wrap" gap={0.5}>
                  {(cam.features || []).map(f => (
                    <Chip
                      key={f}
                      label={f.replace('_', ' ')}
                      size="small"
                      sx={{
                        fontSize: '0.65rem',
                        height: 20,
                        bgcolor: `${FEATURE_COLORS[f] || '#78909c'}15`,
                        color: FEATURE_COLORS[f] || '#78909c',
                        border: `1px solid ${FEATURE_COLORS[f] || '#78909c'}30`,
                      }}
                    />
                  ))}
                </Stack>
              </CardContent>

              <CardActions sx={{ p: 2, pt: 0 }}>
                <Button
                  component={Link}
                  to={`/zone-editor/${cam.id}`}
                  variant="outlined"
                  size="small"
                  startIcon={<Settings />}
                  fullWidth
                  sx={{ borderColor: 'primary.main', color: 'primary.main' }}
                >
                  Configure Zones
                </Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
