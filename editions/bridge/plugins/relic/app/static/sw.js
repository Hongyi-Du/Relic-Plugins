// The Relic App as an installed app: Edge needs a service worker to offer "Install". Everything still comes from the
// local server; nothing is cached.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => { /* the network answers every request */ });
