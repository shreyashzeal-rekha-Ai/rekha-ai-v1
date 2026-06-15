import React, { useState, useMemo } from 'react';
import { ThemeProvider, CssBaseline, Box, Tabs, Tab, Stack, Tooltip, IconButton } from '@mui/material';
import { Settings, Dashboard, History, LightMode, DarkMode, Videocam, Analytics } from '@mui/icons-material';
import { createAppTheme } from './theme';
import SettingsPage    from './pages/SettingsPage';
import DashboardPage   from './pages/DashboardPage';
import AlertsDashboard from './pages/AlertsDashboard';
import AnalysisPage    from './pages/AnalysisPage';

function App() {
  const [tab, setTab] = useState(0);
  const [colorMode, setColorMode] = useState('light'); // default: light mode
  const theme = useMemo(() => createAppTheme(colorMode), [colorMode]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ height: '100vh', width: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>

        {/* ── Top navigation bar ── */}
        <Box sx={{
          borderBottom: '1px solid',
          borderColor: 'divider',
          background: colorMode === 'dark'
            ? 'linear-gradient(135deg, rgba(13, 20, 30, 0.75) 0%, rgba(8, 10, 15, 0.65) 100%)'
            : 'linear-gradient(135deg, rgba(255, 255, 255, 0.8) 0%, rgba(241, 245, 249, 0.5) 100%)',
          backdropFilter: 'blur(16px)',
          boxShadow: colorMode === 'dark' ? '0 4px 20px rgba(0,0,0,0.15)' : '0 4px 20px rgba(0,0,0,0.03)',
          px: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          flexShrink: 0,
          height: 60,
          zIndex: 10,
        }}>
          {/* Brand — Rekha-Ai */}
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ pr: 2, borderRight: '1px solid', borderColor: 'divider', height: '100%' }}>
            <Box
              component="img"
              src="/rekha_ai_logo.jpeg"
              alt="Rekha-Ai"
              sx={{ width: 40, height: 40, objectFit: 'contain', borderRadius: '8px', filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.25))' }}
            />
            <Box>
              <Box component="span" sx={{ fontWeight: 800, fontSize: '1.05rem', color: 'text.primary', letterSpacing: 1.2 }}>
                Rekha-Ai
              </Box>
              <Box component="span" sx={{ fontSize: '0.7rem', color: 'text.secondary', ml: 1, fontWeight: 500 }}>
                AI Surveillance Intelligence
              </Box>
            </Box>
          </Stack>
 
          {/* Tabs */}
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{
              minHeight: 60, height: 60,
              '& .MuiTab-root': {
                minHeight: 60, height: 60, py: 0, px: 2,
                fontSize: '0.85rem', fontWeight: 600,
                color: 'text.secondary',
                textTransform: 'none',
                transition: 'all 0.2s',
                '&:hover': { color: '#00b0ff' },
                '&.Mui-selected': { color: '#00b0ff', fontWeight: 700 },
              },
              '& .MuiTabs-indicator': { bgcolor: '#00b0ff', height: 3, borderRadius: '3px 3px 0 0' },
            }}
          >
            {/* Tab 0 — Analytics Dashboard (first page on load) */}
            <Tab icon={<Dashboard fontSize="small" />}  iconPosition="start" label="Dashboard"       />
            {/* Tab 1 — Live AI camera feed + real-time alerts */}
            <Tab icon={<Videocam  fontSize="small" />}  iconPosition="start" label="Live AI Cam"     />
            {/* Tab 2 — Alert history / clips */}
            <Tab icon={<History   fontSize="small" />}  iconPosition="start" label="Alert History"   />
            {/* Tab 3 — Feature configuration */}
            <Tab icon={<Settings  fontSize="small" />}  iconPosition="start" label="Settings"        />
          </Tabs>

          {/* ── Dark / Light mode toggle (right side of navbar) ── */}
          <Box sx={{ ml: 'auto', pr: 1 }}>
            <Tooltip title={colorMode === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
              <IconButton
                id="color-mode-toggle"
                size="small"
                onClick={() => setColorMode(m => m === 'dark' ? 'light' : 'dark')}
                sx={{
                  color: 'text.secondary',
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1.5,
                  p: 0.75,
                  '&:hover': { color: 'primary.main', borderColor: 'primary.main', bgcolor: colorMode === 'dark' ? 'rgba(0,176,255,0.1)' : 'rgba(0,176,255,0.05)' },
                  transition: 'all 0.2s',
                }}
              >
                {colorMode === 'dark'
                  ? <LightMode fontSize="small" />
                  : <DarkMode  fontSize="small" />
                }
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {/* ── Page content — fills all remaining height ── */}
        <Box sx={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
          {tab === 0 && <AnalysisPage    />}
          {tab === 1 && <DashboardPage   />}
          {tab === 2 && <AlertsDashboard />}
          {tab === 3 && <SettingsPage    />}
        </Box>

      </Box>
    </ThemeProvider>
  );
}

export default App;
