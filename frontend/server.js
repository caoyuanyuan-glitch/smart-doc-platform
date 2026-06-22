const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = 5174;
const BACKEND_URL = 'http://localhost:8000';
const DIST_DIR = path.join(__dirname, 'dist');

// Simple static file server
function serveStatic(req, res, filePath) {
  const fullPath = path.join(DIST_DIR, filePath);
  
  // Handle index.html for SPA routing
  const indexPath = path.join(DIST_DIR, 'index.html');
  
  fs.readFile(indexPath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(data);
  });
}

// Proxy API requests to backend
function proxyRequest(req, res) {
  const url = BACKEND_URL + req.url;
  const protocol = url.startsWith('https') ? https : http;
  
  const options = {
    hostname: new URL(url).hostname,
    port: new URL(url).port || (url.startsWith('https') ? 443 : 80),
    path: new URL(url).pathname + new URL(url).search,
    method: req.method,
    headers: { ...req.headers, host: new URL(url).hostname }
  };
  
  const proxyReq = protocol.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });
  
  req.pipe(proxyReq);
  proxyReq.on('error', (err) => {
    console.error('Proxy error:', err);
    res.writeHead(502);
    res.end('Bad Gateway');
  });
}

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  
  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }
  
  // API proxy
  if (req.url.startsWith('/api')) {
    proxyRequest(req, res);
    return;
  }
  
  // Static files
  let filePath = req.url === '/' ? '/index.html' : req.url;
  
  // Remove query string
  filePath = filePath.split('?')[0];
  
  const fullPath = path.join(DIST_DIR, filePath);
  
  fs.readFile(fullPath, (err, data) => {
    if (err) {
      // Serve index.html for SPA routing
      fs.readFile(path.join(DIST_DIR, 'index.html'), (err2, indexData) => {
        if (err2) {
          res.writeHead(404);
          res.end('Not Found');
          return;
        }
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(indexData);
      });
      return;
    }
    
    // Determine content type
    const ext = path.extname(fullPath);
    const contentTypes = {
      '.html': 'text/html',
      '.js': 'application/javascript',
      '.css': 'text/css',
      '.json': 'application/json',
      '.png': 'image/png',
      '.jpg': 'image/jpeg',
      '.svg': 'image/svg+xml',
      '.ico': 'image/x-icon'
    };
    
    res.writeHead(200, { 'Content-Type': contentTypes[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running at http://localhost:${PORT}`);
  console.log(`API proxy to ${BACKEND_URL}`);
});
