import React, { useRef, useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Stack, Button, Select, MenuItem,
  FormControl, InputLabel, TextField, Paper,
  Alert, IconButton, Tooltip, List, ListItem, Divider,
  ListItemText, ListItemSecondaryAction
} from '@mui/material';
import {
  Delete, Save, Undo, Draw
} from '@mui/icons-material';

const API = 'http://localhost:5050';

const FEATURES = [
  { value: 'intrusion',           label: 'Intrusion Zone',        color: '#ff6d00', shape: 'polygon' },
  { value: 'no_go_zone',          label: 'No-Go Zone',            color: '#ff1744', shape: 'polygon' },
  { value: 'crowd',               label: 'Crowd Monitoring',      color: '#76ff03', shape: 'polygon' },
  { value: 'missing_person',      label: 'Person Missing',        color: '#e040fb', shape: 'polygon' },
  { value: 'personal_monitoring', label: 'Personal Monitoring',   color: '#00e5ff', shape: 'polygon' },
  { value: 'loitering',           label: 'Loitering',             color: '#ffd600', shape: 'polygon' },
  { value: 'perimeter',           label: 'Perimeter Intrusion',   color: '#ff4081', shape: 'line' },
  { value: 'footfall',            label: 'Footfall Count',        color: '#00b0ff', shape: 'line' },
];

const CANVAS_W = 640;
const CANVAS_H = 480;

function snapToCanvas(x, y, rect) {
  const scaleX = CANVAS_W / rect.width;
  const scaleY = CANVAS_H / rect.height;
  return [
    Math.max(0, Math.min(CANVAS_W, Math.round(x * scaleX))),
    Math.max(0, Math.min(CANVAS_H, Math.round(y * scaleY))),
  ];
}

export default function ZoneEditorPage() {
  const canvasRef = useRef(null);

  const [featureType, setFeatureType] = useState('intrusion');
  const [drawing, setDrawing] = useState(false);
  const [currentPoints, setCurrentPoints] = useState([]);
  const [saveMsg, setSaveMsg] = useState(null);

  const selectedFeature = FEATURES.find(f => f.value === featureType);

  // ── Draw overlay on canvas ───────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    // Draw current in-progress polygon/line
    if (currentPoints.length > 0) {
      const color = selectedFeature?.color || '#ffffff';
      ctx.strokeStyle = color;
      ctx.fillStyle   = `${color}33`;
      ctx.lineWidth   = 2;
      ctx.setLineDash([6, 4]);

      ctx.beginPath();
      ctx.moveTo(currentPoints[0][0], currentPoints[0][1]);
      currentPoints.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
      
      // Auto-close visually if it's a polygon and we aren't done yet, just for preview
      if (selectedFeature?.shape === 'polygon' && currentPoints.length >= 3) {
        ctx.closePath();
        ctx.fill();
      }
      ctx.stroke();

      // Draw point handles
      currentPoints.forEach(([x, y]) => {
        ctx.setLineDash([]);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, 2 * Math.PI);
        ctx.fill();
      });
    }
  }, [currentPoints, selectedFeature]);

  // Animate canvas
  useEffect(() => {
    let raf;
    const loop = () => { draw(); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [draw]);

  // ── Click to add point ───────────────────────────────────────────
  const handleCanvasClick = (e) => {
    if (!drawing) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const [x, y] = snapToCanvas(e.clientX - rect.left, e.clientY - rect.top, rect);
    
    const newPoints = [...currentPoints, [x, y]];
    setCurrentPoints(newPoints);

    // If it's a line, auto-finish after 2 points
    if (selectedFeature?.shape === 'line' && newPoints.length === 2) {
      setDrawing(false);
    }
  };

  const handleCanvasDblClick = (e) => {
    if (!drawing || currentPoints.length < 3 || selectedFeature?.shape !== 'polygon') return;
    setDrawing(false); // Stop drawing mode
  };

  // ── Save Config to AI Engine ─────────────────────────────────────
  const handleSaveConfig = async () => {
    const isLine = selectedFeature?.shape === 'line';
    if (isLine && currentPoints.length !== 2) {
      setSaveMsg({ type: 'warning', text: 'Draw exactly 2 points for a line.' });
      return;
    }
    if (!isLine && currentPoints.length < 3) {
      setSaveMsg({ type: 'warning', text: 'Draw at least 3 points for a polygon.' });
      return;
    }

    const payload = {
      feature: featureType,
      shape_type: selectedFeature?.shape,
      points: currentPoints
    };

    try {
      const res = await fetch(`${API}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error('Backend update failed');
      setSaveMsg({ type: 'success', text: `Configuration sent! AI Engine is now running ${selectedFeature.label}.` });
      setTimeout(() => setSaveMsg(null), 3000);
      setCurrentPoints([]); // Clear drawing
    } catch (err) {
      setSaveMsg({ type: 'error', text: `Failed to save: ${err.message}` });
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto', mt: 4 }}>
      <Typography variant="h4" color="primary.main" fontWeight={800} mb={1}>
        EXPERT CCTV — MVP DETECTOR
      </Typography>
      <Typography variant="body1" color="text.secondary" mb={4}>
        Basic Model Test Mode: 1 Feature, 1 Camera.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
        {/* View area */}
        <Box flex={1}>
          <Box sx={{ 
            position: 'relative', 
            borderRadius: 2, 
            overflow: 'hidden',
            width: CANVAS_W,
            height: CANVAS_H,
            border: drawing ? '2px solid #00e5ff' : '2px solid rgba(255,255,255,0.1)',
            boxShadow: drawing ? '0 0 24px rgba(0,229,255,0.2)' : 'none',
            bgcolor: '#000'
          }}>
            {/* Live MJPEG Feed from Backend replaces local webcam */}
            <img 
              src={`${API}/video_feed`} 
              alt="Live Backend Feed" 
              style={{ position: 'absolute', top: 0, left: 0, width: CANVAS_W, height: CANVAS_H, objectFit: 'fill' }}
            />
            {/* Drawing Canvas Overlays on Top */}
            <canvas
              ref={canvasRef}
              width={CANVAS_W}
              height={CANVAS_H}
              onClick={handleCanvasClick}
              onDoubleClick={handleCanvasDblClick}
              style={{
                position: 'absolute', top: 0, left: 0,
                cursor: drawing ? 'crosshair' : 'default',
              }}
            />
          </Box>
          <Typography variant="caption" color="text.disabled" mt={1} display="block" textAlign="center" width={CANVAS_W}>
            {drawing && selectedFeature?.shape === 'polygon' ? '👆 Click to add points · Double-click to finish' : ''}
            {drawing && selectedFeature?.shape === 'line' ? '👆 Click 2 points to draw a line' : ''}
          </Typography>
        </Box>

        {/* Controls panel */}
        <Box sx={{ width: { xs: '100%', md: 320 } }}>
          <Paper sx={{ p: 3, bgcolor: 'background.paper', borderRadius: 2, border: '1px solid rgba(255,255,255,0.06)' }}>
            <Typography variant="h6" fontWeight={700} mb={3}>Feature Config</Typography>

            {/* Feature Select */}
            <FormControl fullWidth size="small" sx={{ mb: 3 }}>
              <InputLabel>Select Feature</InputLabel>
              <Select value={featureType} onChange={e => { setFeatureType(e.target.value); setCurrentPoints([]); setDrawing(false); }} label="Select Feature">
                {FEATURES.map(t => (
                  <MenuItem key={t.value} value={t.value}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: t.color }} />
                      <Typography variant="body1">{t.label}</Typography>
                    </Stack>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Alert severity="info" sx={{ mb: 3 }}>
              Shape required: <strong>{selectedFeature?.shape}</strong>
            </Alert>

            {/* Action buttons */}
            <Stack spacing={2}>
              {!drawing ? (
                <Button variant="contained" color="primary" startIcon={<Draw />} onClick={() => { setDrawing(true); setCurrentPoints([]); }} fullWidth>
                  Draw New {selectedFeature?.shape}
                </Button>
              ) : (
                <>
                  <Button variant="outlined" color="warning" startIcon={<Undo />} onClick={() => setCurrentPoints(prev => prev.slice(0, -1))} fullWidth disabled={currentPoints.length === 0}>
                    Undo Last Point
                  </Button>
                  <Button variant="text" color="error" onClick={() => { setDrawing(false); setCurrentPoints([]); }} fullWidth>
                    Cancel
                  </Button>
                </>
              )}
              
              <Divider sx={{ my: 1 }} />

              <Button variant="contained" color="success" startIcon={<Save />} onClick={handleSaveConfig} fullWidth>
                Apply Details to AI Engine
              </Button>
            </Stack>

            {saveMsg && (
              <Alert severity={saveMsg.type} sx={{ mt: 2 }}>
                {saveMsg.text}
              </Alert>
            )}
          </Paper>
        </Box>
      </Stack>
    </Box>
  );
}
