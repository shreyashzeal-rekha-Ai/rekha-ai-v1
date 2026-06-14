import { createTheme } from '@mui/material/styles';

export function createAppTheme(mode = 'dark') {
  const isDark = mode === 'dark';

  return createTheme({
    palette: {
      mode, // ← tells MUI which mode, controls default text/bg

      primary:   { main: '#00b0ff', contrastText: '#000000' },
      secondary: { main: '#ff1744', contrastText: '#ffffff' },
      error:     { main: '#f44336' },
      warning:   { main: '#ff9800' },
      success:   { main: '#69f0ae' },

      background: {
        // Dark mode: near-black shells  |  Light mode: clean white/gray
        default: isDark ? '#0a0c10' : '#f0f2f5',
        paper:   isDark ? '#0d1117' : '#ffffff',
      },

      text: {
        // MUI auto-applies these for Typography when mode is set,
        // but we define explicitly for predictability:
        primary:   isDark ? 'rgba(255,255,255,0.92)' : 'rgba(0,0,0,0.87)',
        secondary: isDark ? 'rgba(255,255,255,0.55)' : 'rgba(0,0,0,0.55)',
        disabled:  isDark ? 'rgba(255,255,255,0.30)' : 'rgba(0,0,0,0.35)',
      },

      divider: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.10)',

      // Custom tokens accessible via theme.palette.custom.*
      custom: {
        navBg:        isDark ? '#0d1117'              : '#ffffff',
        navBorder:    isDark ? 'rgba(255,255,255,0.07)': 'rgba(0,0,0,0.08)',
        panelBg:      isDark ? '#0d1117'              : '#f8f9fb',
        feedBg:       isDark ? '#000000'              : '#1a1a1a', // camera feed always dark
        feedBorder:   isDark ? 'rgba(255,255,255,0.07)': 'rgba(0,0,0,0.15)',
        scrollbar:    isDark ? 'rgba(255,255,255,0.12)': 'rgba(0,0,0,0.18)',
      },
    },

    typography: {
      fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
      h6:    { fontWeight: 600, letterSpacing: '0.5px' },
      button: { textTransform: 'none', fontWeight: 500 },
    },

    components: {
      // ── Remove dead MuiAppBar override (app uses <Box>, not <AppBar>) ──

      MuiButton: {
        styleOverrides: { root: { borderRadius: 8 } },
      },

      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none', // prevent MUI dark-mode elevation overlay
          },
        },
      },

      MuiDivider: {
        styleOverrides: {
          root: {
            borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.10)',
          },
        },
      },

      MuiChip: {
        styleOverrides: {
          root: {
            // chips with outlined variant get correct border in both modes
            '&.MuiChip-outlined': {
              borderColor: isDark ? 'rgba(255,255,255,0.20)' : 'rgba(0,0,0,0.20)',
            },
          },
        },
      },
    },
  });
}

// Default export still works for any legacy import
export default createAppTheme('dark');
