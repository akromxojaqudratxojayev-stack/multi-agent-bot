const CACHE_NAME = 'ai-jamoa-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Online bo'lsa to'g'ridan-to'g'ri internetdan oladi
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
