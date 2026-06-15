import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';
import http from 'node:http';
import https from 'node:https';

const DEV_API_TARGET = process.env.VITE_DEV_API_TARGET ?? 'https://api.pdftoreel.com';

// Fresh connection per request (keepAlive: false). Reusing keep-alive sockets
// to a remote backend is the usual cause of intermittent dev-only 500s: the
// remote closes an idle socket, the proxy reuses the dead one, the request
// fails with ECONNRESET and http-proxy reports it to the browser as a 500 the
// backend never logs. The Flutter app hits the backend directly and so never
// sees this.
const proxyAgent = DEV_API_TARGET.startsWith('https')
  ? new https.Agent({ keepAlive: false })
  : new http.Agent({ keepAlive: false });

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Proxy /api to the backend so browser dev requests are same-origin
    // (avoids CORS). Override the target with VITE_DEV_API_TARGET for a local
    // backend. In production the app calls API_BASE_URL directly.
    proxy: {
      '/api': {
        target: DEV_API_TARGET,
        changeOrigin: true,
        secure: true,
        agent: proxyAgent,
        // Don't let an upstream socket error crash the proxy or hang the
        // request; surface it as a clean 502 with the reason instead.
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            console.warn(`[proxy] ${err.message}`);
            const sres = res as http.ServerResponse;
            if (sres && !sres.headersSent && typeof sres.writeHead === 'function') {
              sres.writeHead(502, { 'Content-Type': 'application/json' });
              sres.end(JSON.stringify({ detail: `Proxy error: ${err.message}` }));
            }
          });
        },
      },
    },
  },
});
