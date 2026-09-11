// Test server: only the selected static demo directory is exposed, on loopback.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { site } from './site.mjs';

const types = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css',
  '.json':'application/json', '.py':'text/plain', '.ttf':'font/ttf', '.whl':'application/zip'};
createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (pathname === '/favicon.ico') { response.writeHead(204); response.end(); return; }
    const path = resolve(site, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!path.startsWith(site + sep)) { response.writeHead(403); response.end(); return; }
    const bytes = await readFile(path);
    response.writeHead(200, {'Content-Type': types[extname(path)] || 'application/octet-stream', 'Cache-Control':'no-store'});
    response.end(bytes);
  } catch {
    response.writeHead(404); response.end('Not found');
  }
}).listen(8766, '127.0.0.1');
