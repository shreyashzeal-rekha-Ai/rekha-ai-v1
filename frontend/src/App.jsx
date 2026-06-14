import React, { useState, useMemo } from 'react';
import { ThemeProvider, CssBaseline, Box, Tabs, Tab, Stack, Tooltip, IconButton } from '@mui/material';
import { Settings, Dashboard, History, LightMode, DarkMode } from '@mui/icons-material';
import { createAppTheme } from './theme';
import SettingsPage      from './pages/SettingsPage';
import DashboardPage     from './pages/DashboardPage';
import AlertsDashboard   from './pages/AlertsDashboard';

function App() {
  const [tab, setTab] = useState(0);
  const [colorMode, setColorMode] = useState('dark'); // default: dark mode
  const theme = useMemo(() => createAppTheme(colorMode), [colorMode]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ height: '100vh', width: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>

        {/* ── Top navigation bar ── */}
        <Box sx={{
          borderBottom: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          px: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          flexShrink: 0,
        }}>
          {/* Brand — Rekha-Ai */}
          <Stack direction="row" alignItems="center" spacing={1} sx={{ pr: 2, borderRight: '1px solid', borderColor: 'divider' }}>
            <Box
              component="img"
              src="/rekha_ai_logo.jpeg"
              alt="Rekha-Ai"
              sx={{ width: 36, height: 36, objectFit: 'contain', filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.4))' }}
            />
            <Box>
              <Box component="span" sx={{ fontWeight: 800, fontSize: '0.95rem', color: 'text.primary', letterSpacing: 1 }}>
                Rekha-Ai
              </Box>
              <Box component="span" sx={{ fontSize: '0.65rem', color: 'text.secondary', ml: 1 }}>
                AI Surveillance Intelligence
              </Box>
            </Box>
          </Stack>

          {/* Tabs */}
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{
              minHeight: 48,
              '& .MuiTab-root': {
                minHeight: 48, py: 0, px: 2,
                fontSize: '0.8rem', fontWeight: 600,
                color: 'text.secondary',
                textTransform: 'none',
                '&.Mui-selected': { color: '#00b0ff' },
              },
              '& .MuiTabs-indicator': { bgcolor: '#00b0ff', height: 2 },
            }}
          >
            <Tab icon={<Dashboard fontSize="small" />} iconPosition="start" label="Live Dashboard" />
            <Tab icon={<History   fontSize="small" />} iconPosition="start" label="Alert History"  />
            <Tab icon={<Settings  fontSize="small" />} iconPosition="start" label="Feature Settings" />
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
                  '&:hover': { color: 'primary.main', borderColor: 'primary.main' },
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

        {/* ── Page content ── */}
        <Box sx={{ flex: 1, overflow: 'hidden' }}>
          {tab === 0 && <DashboardPage   />}
          {tab === 1 && <AlertsDashboard />}
          {tab === 2 && <SettingsPage    />}
        </Box>

      </Box>
    </ThemeProvider>
  );
}

export default App;
