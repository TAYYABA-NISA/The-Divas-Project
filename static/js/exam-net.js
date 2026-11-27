/*
 * Network-aware answer saving for the examination workspace.
 *
 * - Answers are queued in localStorage and sent in order with a per-attempt sequence number.
 *   The server ignores stale or duplicate sequence numbers, so replays are safe.
 * - The server decides the deadline from its own clock. Time spent offline never extends it:
 *   once the server answers 403, the queue is discarded.
 * - A heartbeat reports connection quality and resynchronises the countdown with the server.
 */
(function () {
  'use strict';

  function ExamNet(config) {
    const storageKey = 'exam-queue-' + config.attemptId;
    const state = { online: navigator.onLine, failures: 0, slow: false, flushing: false, retryDelay: 2000, retryTimer: null };

    function load() {
      try {
        const data = JSON.parse(localStorage.getItem(storageKey) || '{}');
        return { seq: data.seq || 0, items: Array.isArray(data.items) ? data.items : [] };
      } catch (e) { return { seq: 0, items: [] }; }
    }
    function store(data) {
      try { localStorage.setItem(storageKey, JSON.stringify(data)); } catch (e) { /* storage full or blocked */ }
    }

    function nextSeq() {
      const data = load();
      data.seq += 1;
      store(data);
      return data.seq;
    }

    // One queued item per question: the newest state of that question wins.
    function enqueue(position, fields) {
      const data = load();
      data.seq += 1;
      data.items = data.items.filter(function (item) { return item.position !== position; });
      data.items.push({ seq: data.seq, position: position, fields: fields });
      data.items.sort(function (a, b) { return a.seq - b.seq; });
      store(data);
      render();
      return data.seq;
    }

    function pending() { return load().items.length; }
    function queuedFor(position) {
      return load().items.filter(function (item) { return item.position === position; })[0] || null;
    }

    function quality() {
      if (!state.online || state.failures >= 2) return 'offline';
      if (state.failures === 1 || state.slow) return 'unstable';
      return 'online';
    }

    function render() {
      const q = quality();
      const count = pending();
      if (config.netEl) {
        config.netEl.className = 'net-status net-' + q;
        config.netEl.textContent = q === 'offline' ? 'Offline: answers are kept on this device and will retry'
          : q === 'unstable' ? 'Unstable connection: retrying' : 'Online';
      }
      if (config.onStatus) config.onStatus(q, count, state.flushing);
    }

    function buildBody(item) {
      const body = new FormData();
      (item.fields.choice || []).forEach(function (id) { body.append('choice', id); });
      body.append('written_response', item.fields.written_response || '');
      if (item.fields.marked_for_review) body.append('marked_for_review', 'on');
      body.append('client_seq', String(item.seq));
      return body;
    }

    function removeItem(seq) {
      const data = load();
      data.items = data.items.filter(function (item) { return item.seq !== seq; });
      store(data);
    }

    function scheduleRetry() {
      clearTimeout(state.retryTimer);
      state.retryTimer = setTimeout(flush, state.retryDelay);
      state.retryDelay = Math.min(state.retryDelay * 2, 30000);
    }

    // Send queued answers oldest first. Resolves true when the queue is empty.
    function flush() {
      if (state.flushing) return Promise.resolve(false);
      const items = load().items;
      if (!items.length) { render(); return Promise.resolve(true); }
      state.flushing = true;
      render();

      function sendNext(index) {
        if (index >= items.length) return Promise.resolve(true);
        const item = items[index];
        const url = config.saveUrl.replace('/question/0/', '/question/' + item.position + '/');
        return fetch(url, {
          method: 'POST', body: buildBody(item), credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': config.csrf },
        }).then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (body) {
            if (response.ok && body.ok) {
              removeItem(item.seq);
              state.failures = 0;
              if (config.onSaved) config.onSaved(item, body);
              return sendNext(index + 1);
            }
            if (response.status === 403 || body.expired) {
              store({ seq: load().seq, items: [] });
              if (config.onDeadlinePassed) config.onDeadlinePassed(body.error);
              return false;
            }
            if (response.status === 400) {
              removeItem(item.seq); // invalid data will never succeed; do not block later answers
              if (config.onRejected) config.onRejected(item, body.error);
              return sendNext(index + 1);
            }
            throw new Error('server ' + response.status);
          });
        });
      }

      return sendNext(0).then(function (done) {
        state.flushing = false;
        if (done) state.retryDelay = 2000;
        render();
        return done;
      }).catch(function () {
        state.flushing = false;
        state.failures += 1;
        render();
        scheduleRetry();
        return false;
      });
    }

    function heartbeat() {
      const started = Date.now();
      return fetch(config.pollUrl + '?after=' + (config.lastAnnouncement ? config.lastAnnouncement() : 0), {
        credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' }, cache: 'no-store',
      }).then(function (response) {
        if (!response.ok) throw new Error('poll ' + response.status);
        return response.json();
      }).then(function (body) {
        state.online = true;
        state.failures = 0;
        state.slow = Date.now() - started > 3000;
        render();
        if (config.onHeartbeat) config.onHeartbeat(body);
        if (pending()) flush();
      }).catch(function () {
        state.failures += 1;
        render();
        if (pending()) scheduleRetry();
      });
    }

    window.addEventListener('online', function () { state.online = true; state.failures = 0; state.retryDelay = 2000; render(); heartbeat(); flush(); });
    window.addEventListener('offline', function () { state.online = false; render(); });

    function start() {
      render();
      heartbeat();
      flush();
      setInterval(heartbeat, config.interval || 15000);
    }

    return {
      start: start, enqueue: enqueue, flush: flush, pending: pending, nextSeq: nextSeq,
      queuedFor: queuedFor, quality: quality, isOnline: function () { return quality() !== 'offline'; },
    };
  }

  window.ExamNet = ExamNet;
})();
