/* 데이터를 바꾸면 V 값을 올리세요. 안 그러면 옛 캐시가 남습니다. */
const V = 'hist-v1';
const SHELL = ['./','index.html','manifest.webmanifest','icon.svg','data/index.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

/* HTML·JSON은 stale-while-revalidate: 캐시를 바로 주고 뒤에서 갱신한다. */
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  if (new URL(req.url).origin !== location.origin) return;
  e.respondWith(caches.open(V).then(c =>
    c.match(req).then(hit => {
      const net = fetch(req).then(res => {
        if (res && res.status === 200) c.put(req, res.clone());
        return res;
      }).catch(() => hit);
      return hit || net;
    })));
});
