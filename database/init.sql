// MongoDB init script — runs on first container start
// Creates the collections and indexes for Expert CCTV

db = db.getSiblingDB('expert_cctv');

// Alerts collection
db.createCollection('alerts');
db.alerts.createIndex({ cam_id: 1, timestamp: -1 });
db.alerts.createIndex({ feature: 1 });
db.alerts.createIndex({ timestamp: -1 });

print('✅ expert_cctv database initialized.');
