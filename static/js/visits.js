(() => {
  'use strict';
  let sent = false;
  function record() {
    if (sent || document.visibilityState !== 'visible' || document.prerendering) return;
    sent = true;
    try {
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      bytes[6] = (bytes[6] & 15) | 64;
      bytes[8] = (bytes[8] & 63) | 128;
      const hex = Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('');
      const id = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
      fetch('/community/api/visits/', {
        method: 'POST', mode: 'same-origin', credentials: 'omit', keepalive: true,
        headers: {'Content-Type': 'application/json', 'X-JLA-Visit': '1'},
        body: JSON.stringify({path: location.pathname, event_id: id}),
      }).catch(() => {});
    } catch (_) { /* Statistics must never interrupt reading or playback. */ }
  }
  record();
  document.addEventListener('visibilitychange', record);
  document.addEventListener('prerenderingchange', record);
})();
