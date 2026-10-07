const CACHE='gods-eye-viajes-v2';
const CORE=['./','./index.html','./manifest.json','./icon.svg','./icon-192.png','./icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  // Tiles y CDN: red primero, sin cache obligatorio (network passthrough)
  if(u.hostname.includes('tile')||u.hostname.includes('unpkg')||u.hostname.includes('jsdelivr')){ return; }
  if(e.request.method!=='GET') return;
  e.respondWith(
    caches.match(e.request).then(hit=>hit||fetch(e.request).then(res=>{
      const copy=res.clone();
      if(u.origin===location.origin){ caches.open(CACHE).then(c=>c.put(e.request,copy)); }
      return res;
    }).catch(()=>caches.match('./index.html')))
  );
});
