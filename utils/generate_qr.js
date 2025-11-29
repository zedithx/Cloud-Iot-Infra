#!/usr/bin/env node
/**
 * Generate a QR code for a device ID.
 * 
 * Installation:
 *   npm install qrcode
 * 
 * Usage:
 *   node generate_qr.js [device_id]
 *   node generate_qr.js esp32s3_cam_01
 */

const fs = require('fs');
const path = require('path');

// Get device ID from command line or use default
const deviceId = process.argv[2] || 'esp32s3_cam_01';
const outputPath = path.join(__dirname, 'qr_code.png');

try {
  // Try to require qrcode
  const QRCode = require('qrcode');
  
  // Generate QR code
  QRCode.toFile(outputPath, deviceId, {
    errorCorrectionLevel: 'L',
    type: 'png',
    width: 300,
    margin: 2,
  }, (err) => {
    if (err) {
      console.error('❌ Error generating QR code:', err.message);
      process.exit(1);
    }
    console.log(`✅ QR code generated: ${outputPath}`);
    console.log(`   Device ID: ${deviceId}`);
  });
} catch (err) {
  if (err.code === 'MODULE_NOT_FOUND') {
    console.error('❌ Error: qrcode library not installed.');
    console.error('   Install it with: npm install qrcode');
    process.exit(1);
  }
  throw err;
}


