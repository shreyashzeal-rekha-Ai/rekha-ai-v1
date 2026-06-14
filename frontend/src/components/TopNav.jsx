import React, { useState, useEffect } from 'react';
import { AppBar, Toolbar, Typography, Button, Box, IconButton, Badge, Avatar, Chip } from '@mui/material';
import {
  Notifications as NotificationsIcon,
  Videocam as VideocamIcon,
  Dashboard as DashboardIcon,
  Timeline as TimelineIcon,
  HealthAndSafety as HealthIcon,
  AccountCircle,
  GridView,
  FiberManualRecord,
} from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';

const API = 'http://localhost:5050';

const TopNav = () => {
  const location = useLocation();
  const [criticalCount, setCriticalCount] = useState(0);

  // Poll for critical-severity alerts to update the badge
  useEffect(() => {
    const check = async () => {
      try {
        const res  = await fetch(`${API}/api/alerts?limit=50`);
        const data = await res.json();
        const recent = data.filter(a => {
          const age = (Date.now() - new Date(a.timestamp)) / 1000;
          return age < 60 && ['CRITICAL', 'HIGH'].includes(a.severity);
        });
        setCriticalCount(recent.length);
      } catch {/* backend offline — ignore */}
    };
    check();
    const iv = setInterval(check, 5000);
    return () => clearInterval(iv);
  }, []);

  const navItems = [
    { label: 'Alerts',    path: '/alerts',    icon: <NotificationsIcon sx={{ mr: 0.8, fontSize: 18 }} /> },
    { label: 'Cams',      path: '/cams',       icon: <VideocamIcon       sx={{ mr: 0.8, fontSize: 18 }} /> },
    { label: 'Cam Group', path: '/cam-group',  icon: <GridView           sx={{ mr: 0.8, fontSize: 18 }} /> },
    { label: 'Analysis',  path: '/analysis',   icon: <TimelineIcon       sx={{ mr: 0.8, fontSize: 18 }} /> },
    { label: 'Health',    path: '/health',     icon: <HealthIcon         sx={{ mr: 0.8, fontSize: 18 }} /> },
  ];

  return (
    <AppBar position="fixed" color="default">
      <Toolbar sx={{ justifyContent: 'space-between', minHeight: '60px !important' }}>

        {/* ── Logo ─────────────────────────────────────────────── */}
        <Box
          component={Link}
          to="/"
          sx={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit', mr: 4 }}
        >
          {/* Rekha-Ai logo from public folder */}
          <Box
            component="img"
            src="/rekha_ai_logo.jpeg"
            alt="Rekha-Ai Logo"
            sx={{
              width: 44,
              height: 44,
              mr: 1.2,
              objectFit: 'contain',
              filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.35))',
            }}
          />
          <Box>
            <Typography
              variant="subtitle1"
              sx={{ fontWeight: 900, color: 'primary.main', lineHeight: 1, letterSpacing: 2, fontSize: '1.05rem' }}
            >
              Rekha-Ai
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.disabled', lineHeight: 1, fontWeight: 400, letterSpacing: 0.5 }}>
              AI Surveillance Platform
            </Typography>
          </Box>
        </Box>

        {/* ── Nav Links ─────────────────────────────────────────── */}
        <Box sx={{ display: 'flex', gap: 0.5, flex: 1 }}>
          {navItems.map((item) => {
            const isActive = location.pathname.startsWith(item.path);
            return (
              <Button
                key={item.label}
                component={Link}
                to={item.path}
                size="small"
                sx={{
                  color: isActive ? 'primary.main' : 'text.secondary',
                  backgroundColor: isActive ? 'rgba(0, 229, 255, 0.1)' : 'transparent',
                  borderBottom: isActive ? '2px solid #00e5ff' : '2px solid transparent',
                  borderRadius: 0,
                  px: 1.5,
                  py: 1.5,
                  fontSize: '0.8rem',
                  fontWeight: isActive ? 700 : 400,
                  '&:hover': {
                    color: 'primary.main',
                    backgroundColor: 'rgba(0, 229, 255, 0.05)',
                  },
                  transition: 'all 0.15s',
                }}
              >
                {item.icon}
                {item.label}
              </Button>
            );
          })}
        </Box>

        {/* ── Right Side ────────────────────────────────────────── */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>

          {/* Live indicator */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <FiberManualRecord sx={{
              fontSize: 10, color: '#4caf50',
              animation: 'pulse 2s ease-in-out infinite',
            }} />
            <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.7rem' }}>LIVE</Typography>
          </Box>

          {/* Alert bell with badge */}
          <IconButton
            component={Link}
            to="/alerts"
            size="small"
            sx={{ color: criticalCount > 0 ? 'error.main' : 'text.secondary' }}
          >
            <Badge badgeContent={criticalCount || null} color="error" max={9}>
              <NotificationsIcon fontSize="small" />
            </Badge>
          </IconButton>

          {/* Avatar */}
          <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main', cursor: 'pointer' }}>
            <AccountCircle sx={{ color: 'background.default', fontSize: 22 }} />
          </Avatar>
        </Box>
      </Toolbar>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </AppBar>
  );
};

export default TopNav;
