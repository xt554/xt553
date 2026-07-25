(() => {
  const CAPTURE_KEY = "__fragmentTonCaptureV2";
  const LEGACY_KEY = "__fragmentTonCaptureV1";
  const rows = window[CAPTURE_KEY] || [];
  const seen = new Set(rows.map((row) => row.fingerprint).filter(Boolean));
  window[CAPTURE_KEY] = rows;
  window[LEGACY_KEY] = rows;

  const parseJson = (value) => {
    if (typeof value !== "string") return value;
    try { return JSON.parse(value); } catch (_) { return null; }
  };

  const normalize = (value) => {
    let candidate = parseJson(value) || value;
    if (!candidate || typeof candidate !== "object") return null;

    if (candidate.method === "sendTransaction" && Array.isArray(candidate.params)) {
      candidate = parseJson(candidate.params[0]) || candidate.params[0];
    }
    if (candidate.request && typeof candidate.request === "object") {
      candidate = candidate.request;
    }
    const params = candidate.params && typeof candidate.params === "object"
      ? candidate.params
      : candidate;
    if (!params || !Array.isArray(params.messages) || params.messages.length === 0) return null;
    return {
      params: {
        ...params,
        valid_until: params.valid_until ?? params.validUntil,
      },
    };
  };

  const fingerprint = (request) => {
    try {
      const p = request.params;
      return JSON.stringify([
        p.network || "-239",
        p.from || "",
        p.valid_until || 0,
        p.messages,
      ]);
    } catch (_) {
      return String(Date.now());
    }
  };

  const capture = (value, source) => {
    try {
      const request = normalize(value);
      if (!request) return;
      const key = fingerprint(request);
      if (seen.has(key)) return;
      seen.add(key);
      const row = { source, capturedAt: Date.now(), fingerprint: key, request };
      rows.push(row);
      window.dispatchEvent(new CustomEvent("fragment-ton-captured", { detail: row }));
      console.info("[fragment-hook-v2] captured TON transaction", row);
    } catch (error) {
      console.warn("[fragment-hook-v2] capture failed", error);
    }
  };

  window.__drainFragmentTonCaptures = () => rows.splice(0, rows.length);

  const patchObject = (object, label) => {
    if (!object || (typeof object !== "object" && typeof object !== "function")) return false;
    const targets = [object];
    if (object.prototype) targets.push(object.prototype);
    let patched = false;
    for (const target of targets) {
      for (const name of ["sendTransaction", "send_transaction"]) {
        let original;
        try { original = target[name]; } catch (_) { continue; }
        if (typeof original !== "function" || original.__fragmentPatchedV2) continue;
        const wrapped = async function (...args) {
          capture(args[0], `${label}.${name}`);
          return original.apply(this, args);
        };
        Object.defineProperty(wrapped, "__fragmentPatchedV2", { value: true });
        try {
          target[name] = wrapped;
          patched = true;
        } catch (_) {}
      }
    }
    return patched;
  };

  const watchGlobal = (name) => {
    let current;
    try { current = window[name]; } catch (_) { return; }
    if (current) patchObject(current, `window.${name}`);
    const descriptor = Object.getOwnPropertyDescriptor(window, name);
    if (descriptor && !descriptor.configurable) return;
    try {
      Object.defineProperty(window, name, {
        configurable: true,
        enumerable: descriptor?.enumerable ?? true,
        get: () => current,
        set: (value) => {
          current = value;
          patchObject(value, `window.${name}`);
        },
      });
    } catch (_) {}
  };

  const originalStringify = JSON.stringify;
  JSON.stringify = function (value, ...rest) {
    capture(value, "JSON.stringify");
    return originalStringify.call(this, value, ...rest);
  };

  if (window.TextEncoder?.prototype?.encode) {
    const originalEncode = window.TextEncoder.prototype.encode;
    window.TextEncoder.prototype.encode = function (input) {
      if (typeof input === "string" && input.includes("sendTransaction")) {
        capture(input, "TextEncoder.encode");
      }
      return originalEncode.call(this, input);
    };
  }

  const knownNames = ["tonConnectUI", "tonConnect", "TonConnectUI", "TonConnect"];
  knownNames.forEach(watchGlobal);

  const scan = () => {
    for (const name of knownNames) {
      try { patchObject(window[name], `window.${name}`); } catch (_) {}
    }
    for (const key of Object.keys(window)) {
      if (!/ton|wallet|connect/i.test(key)) continue;
      try { patchObject(window[key], `window.${key}`); } catch (_) {}
    }
  };
  scan();
  setInterval(scan, 500);
})();
