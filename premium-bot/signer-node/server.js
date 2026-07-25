import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  Address,
  Cell,
  SendMode,
  beginCell,
  external,
  internal,
  storeMessage,
} from '@ton/core';
import { mnemonicToPrivateKey } from '@ton/crypto';
import { WalletContractV4 } from '@ton/ton';

const env = process.env;
const PORT = Number(env.TON_SIGNER_PORT || 9000);
const SHARED_SECRET = env.TON_SIGNER_SHARED_SECRET || '';
const BACKEND = (env.TON_SIGNER_BACKEND || 'mock').toLowerCase();
const KEY_DIR = env.TON_SIGNER_KEY_DIR || '/run/secrets/ton-wallets';
const STATE_DIR = env.TON_SIGNER_STATE_DIR || '/var/lib/ton-signer';
const MAX_CLOCK_SKEW = Number(env.TON_SIGNER_MAX_CLOCK_SKEW_SECONDS || 60);
const MIN_TTL = Number(env.FRAGMENT_CAPTURE_MIN_TTL_SECONDS || 10);
const MAX_TTL = Number(env.FRAGMENT_CAPTURE_MAX_TTL_SECONDS || 300);
const MAX_DEVIATION_BPS = Number(env.TON_AMOUNT_DEVIATION_BPS || 100);
const ALLOW_INSECURE_KEYS = String(env.TON_SIGNER_ALLOW_INSECURE_KEY_PERMISSIONS || 'false').toLowerCase() === 'true';
const TONCENTER_V2_URL = (env.TONCENTER_V2_URL || 'https://toncenter.com/api/v2').replace(/\/$/, '');
const TONCENTER_API_KEY = env.TONCENTER_API_KEY || '';
const SINGLE_LIMIT = tonToNano(env.TON_SINGLE_LIMIT || '50');
const GLOBAL_DAILY_LIMIT = tonToNano(env.TON_GLOBAL_DAILY_LIMIT || '100');
const WALLET_DAILY_LIMIT = tonToNano(env.TON_WALLET_DAILY_LIMIT || '100');
const FEE_RESERVE = tonToNano(env.TON_SIGNER_FEE_RESERVE || '0.1');
const WALLET_CODES = new Set(splitCsv(env.TON_SIGNER_WALLET_CODES || 'ton-hot-1,ton-hot-2,ton-hot-3'));
const WALLET_ADDRESSES = parseWalletMap(env.TON_SIGNER_WALLET_ADDRESSES || '');
const ALLOWED_WORKCHAINS = new Set(splitCsv(env.TON_ALLOWED_DESTINATION_WORKCHAINS || '0').map(Number));
const nonceCache = new Map();
let serial = Promise.resolve();

function splitCsv(value) {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function parseWalletMap(value) {
  const map = new Map();
  for (const item of splitCsv(value)) {
    const index = item.indexOf('=');
    if (index > 0) map.set(item.slice(0, index).trim(), item.slice(index + 1).trim());
  }
  return map;
}

function tonToNano(value) {
  const text = String(value).trim();
  if (!/^\d+(?:\.\d{1,9})?$/.test(text)) throw new Error(`Invalid TON amount setting: ${text}`);
  const [whole, fraction = ''] = text.split('.');
  return BigInt(whole) * 1_000_000_000n + BigInt((fraction + '000000000').slice(0, 9));
}

function normalizeAddress(value) {
  return Address.parse(String(value)).toRawString().toLowerCase();
}

function decodeBase64(value) {
  let text = String(value).trim().replace(/-/g, '+').replace(/_/g, '/');
  while (text.length % 4) text += '=';
  return Buffer.from(text, 'base64');
}

function sha256Hex(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function safeEqualHex(expected, actual) {
  if (!/^[0-9a-f]{64}$/i.test(expected || '') || !/^[0-9a-f]{64}$/i.test(actual || '')) return false;
  return crypto.timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(actual, 'hex'));
}

function jsonResponse(res, status, value) {
  const body = Buffer.from(JSON.stringify(value));
  res.writeHead(status, {'content-type': 'application/json', 'content-length': body.length});
  res.end(body);
}

function httpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1_048_576) throw httpError(413, 'Request body too large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function verifyAuth(req, body) {
  const timestamp = req.headers['x-signer-timestamp'];
  const nonce = req.headers['x-signer-nonce'];
  const signature = req.headers['x-signer-signature'];
  if (!timestamp || !nonce || !signature) throw httpError(401, 'Missing signer authentication');
  const ts = Number(timestamp);
  if (!Number.isInteger(ts) || Math.abs(Math.floor(Date.now() / 1000) - ts) > MAX_CLOCK_SKEW) {
    throw httpError(401, 'Signer timestamp is outside allowed skew');
  }
  const message = Buffer.concat([Buffer.from(String(timestamp)), Buffer.from('\n'), Buffer.from(String(nonce)), Buffer.from('\n'), body]);
  const expected = crypto.createHmac('sha256', SHARED_SECRET).update(message).digest('hex');
  if (!safeEqualHex(expected, String(signature))) throw httpError(401, 'Invalid signer signature');
  const now = Math.floor(Date.now() / 1000);
  for (const [key, seen] of nonceCache) if (seen < now - Math.max(300, MAX_CLOCK_SKEW * 3)) nonceCache.delete(key);
  if (nonceCache.has(String(nonce))) throw httpError(409, 'Signer nonce was already used');
  nonceCache.set(String(nonce), ts);
}

function validatePayload(data) {
  const requiredStrings = ['request_id', 'order_id', 'wallet_code', 'destination', 'destination_raw', 'payload_boc', 'payload_hash', 'schema_hash', 'idempotency_key'];
  for (const key of requiredStrings) if (!data[key] || typeof data[key] !== 'string') throw httpError(422, `Missing ${key}`);
  if (String(data.network) !== '-239') throw httpError(422, 'Only TON mainnet is allowed');
  if (!WALLET_CODES.has(data.wallet_code)) throw httpError(422, 'Wallet code is not approved');
  const configuredAddress = WALLET_ADDRESSES.get(data.wallet_code);
  if (!configuredAddress) throw httpError(503, 'Signer wallet address map is incomplete');
  const source = data.source_address || data.source_address_raw;
  if (!source || normalizeAddress(source) !== normalizeAddress(configuredAddress)) throw httpError(422, 'TON Connect source does not match signer wallet');
  if (data.source_address_raw && normalizeAddress(data.source_address_raw) !== normalizeAddress(configuredAddress)) throw httpError(422, 'Normalized source mismatch');
  const destinationRaw = normalizeAddress(data.destination);
  if (destinationRaw !== String(data.destination_raw).toLowerCase()) throw httpError(422, 'Destination normalization mismatch');
  const workchain = Number(destinationRaw.split(':', 1)[0]);
  if (!ALLOWED_WORKCHAINS.has(workchain)) throw httpError(422, 'Destination workchain is not allowed');
  const amount = BigInt(data.amount_nano);
  const expected = BigInt(data.expected_amount_nano);
  if (amount <= 0n || expected <= 0n || amount > SINGLE_LIMIT) throw httpError(422, 'TON amount is outside policy');
  if (Number(data.amount_deviation_bps) > MAX_DEVIATION_BPS) throw httpError(422, 'Quote deviation exceeded');
  if (Number(data.message_count) !== 1 || data.has_state_init || data.has_extra_currency) throw httpError(422, 'Unsafe TON message structure');
  if (data.schema_approved !== true) throw httpError(422, 'TON schema is not approved');
  const now = Math.floor(Date.now() / 1000);
  const ttl = Number(data.valid_until) - now;
  if (ttl < MIN_TTL || ttl > MAX_TTL) throw httpError(422, 'TON request TTL is outside policy');
  const payloadBytes = decodeBase64(data.payload_boc);
  if (sha256Hex(payloadBytes) !== String(data.payload_hash).toLowerCase()) throw httpError(422, 'Payload hash mismatch');
  Cell.fromBoc(payloadBytes);
  return {amount, expected, configuredAddress, destinationRaw, payloadBytes};
}

async function ensureDirectories() {
  await fs.mkdir(path.join(STATE_DIR, 'requests'), {recursive: true});
  await fs.mkdir(path.join(STATE_DIR, 'locks'), {recursive: true});
  await fs.mkdir(path.join(STATE_DIR, 'ledger'), {recursive: true});
}

async function readJson(file, fallback = null) {
  try { return JSON.parse(await fs.readFile(file, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}

async function writeJsonAtomic(file, data) {
  const temp = `${file}.${process.pid}.${crypto.randomBytes(4).toString('hex')}.tmp`;
  await fs.writeFile(temp, JSON.stringify(data, null, 2), {mode: 0o600});
  await fs.rename(temp, file);
}

async function withFileLock(name, fn) {
  const lockFile = path.join(STATE_DIR, 'locks', `${name}.lock`);
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const handle = await fs.open(lockFile, 'wx', 0o600);
      try { return await fn(); }
      finally { await handle.close(); await fs.unlink(lockFile).catch(() => {}); }
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const stat = await fs.stat(lockFile).catch(() => null);
      if (stat && Date.now() - stat.mtimeMs > 300_000) await fs.unlink(lockFile).catch(() => {});
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  throw httpError(503, 'Signer wallet lock timeout');
}

function dateKey() { return new Date().toISOString().slice(0, 10); }

async function reserveDailyLimit(data, amount, requestHash) {
  const ledgerFile = path.join(STATE_DIR, 'ledger', `${dateKey()}.json`);
  const ledger = await readJson(ledgerFile, {date: dateKey(), entries: {}});
  let globalSpent = 0n;
  let walletSpent = 0n;
  for (const entry of Object.values(ledger.entries || {})) {
    if (!['pending', 'sent', 'unknown'].includes(entry.status)) continue;
    const value = BigInt(entry.amount_nano);
    globalSpent += value;
    if (entry.wallet_code === data.wallet_code) walletSpent += value;
  }
  if (!ledger.entries[requestHash]) {
    if (globalSpent + amount > GLOBAL_DAILY_LIMIT) throw httpError(422, 'Signer global daily limit exceeded');
    if (walletSpent + amount > WALLET_DAILY_LIMIT) throw httpError(422, 'Signer wallet daily limit exceeded');
    ledger.entries[requestHash] = {
      idempotency_key_hash: requestHash,
      wallet_code: data.wallet_code,
      amount_nano: amount.toString(),
      status: 'pending',
      created_at: new Date().toISOString(),
    };
    await writeJsonAtomic(ledgerFile, ledger);
  }
  return {ledgerFile, ledger};
}

async function updateLedger(ledgerFile, requestHash, status) {
  const ledger = await readJson(ledgerFile, {date: dateKey(), entries: {}});
  if (ledger.entries?.[requestHash]) {
    ledger.entries[requestHash].status = status;
    ledger.entries[requestHash].updated_at = new Date().toISOString();
    await writeJsonAtomic(ledgerFile, ledger);
  }
}

async function toncenterGet(endpoint, params) {
  const url = new URL(`${TONCENTER_V2_URL}/${endpoint}`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
  const headers = TONCENTER_API_KEY ? {'X-API-Key': TONCENTER_API_KEY} : {};
  const response = await fetch(url, {headers, signal: AbortSignal.timeout(20_000)});
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`TON Center invalid response: HTTP ${response.status}`); }
  if (!response.ok || data.ok === false) throw new Error(`TON Center ${endpoint} failed: ${data.error || response.status}`);
  return data.result ?? data;
}

async function getWalletState(address) {
  try {
    const result = await toncenterGet('getWalletInformation', {address});
    return {seqno: Number(result.seqno || 0), balance: BigInt(result.balance || 0), deployed: Boolean(result.wallet)};
  } catch (error) {
    const balance = BigInt(await toncenterGet('getAddressBalance', {address}));
    return {seqno: 0, balance, deployed: false};
  }
}

async function broadcastBoc(boc) {
  const headers = {'content-type': 'application/json'};
  if (TONCENTER_API_KEY) headers['X-API-Key'] = TONCENTER_API_KEY;
  const response = await fetch(`${TONCENTER_V2_URL}/sendBocReturnHash`, {
    method: 'POST', headers, body: JSON.stringify({boc}), signal: AbortSignal.timeout(20_000),
  });
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`TON Center invalid broadcast response: HTTP ${response.status}`); }
  if (!response.ok || data.ok === false) throw new Error(`TON broadcast failed: ${data.error || response.status}`);
  return data.result || data;
}

async function loadWalletKey(walletCode, configuredAddress) {
  const file = path.join(KEY_DIR, `${walletCode}.mnemonic`);
  const stat = await fs.stat(file);
  if (!ALLOW_INSECURE_KEYS && (stat.mode & 0o077) !== 0) throw new Error(`Unsafe permissions on ${walletCode} mnemonic file; require 0400 or 0600`);
  const words = (await fs.readFile(file, 'utf8')).trim().split(/\s+/);
  if (words.length !== 24) throw new Error(`${walletCode} mnemonic must contain exactly 24 words`);
  const keyPair = await mnemonicToPrivateKey(words);
  const wallet = WalletContractV4.create({workchain: 0, publicKey: keyPair.publicKey});
  if (wallet.address.toRawString().toLowerCase() !== normalizeAddress(configuredAddress)) throw new Error(`Derived address does not match ${walletCode} configuration`);
  return {wallet, keyPair};
}

async function realSignAndBroadcast(data, validated) {
  const {wallet, keyPair} = await loadWalletKey(data.wallet_code, validated.configuredAddress);
  const state = await getWalletState(wallet.address.toString());
  if (state.balance < validated.amount + FEE_RESERVE) throw new Error('Hot wallet balance is insufficient including fee reserve');
  const payloadCell = Cell.fromBoc(validated.payloadBytes)[0];
  let bounce = true;
  try { bounce = Address.parseFriendly(data.destination).isBounceable; } catch {}
  const timeout = Math.min(Number(data.valid_until), Math.floor(Date.now() / 1000) + 60);
  const transfer = wallet.createTransfer({
    seqno: state.seqno,
    secretKey: keyPair.secretKey,
    sendMode: SendMode.PAY_GAS_SEPARATELY | SendMode.IGNORE_ERRORS,
    timeout,
    messages: [internal({to: Address.parse(data.destination), value: validated.amount, bounce, body: payloadCell})],
  });
  const ext = external({to: wallet.address, init: state.deployed ? undefined : wallet.init, body: transfer});
  const message = beginCell().store(storeMessage(ext)).endCell();
  const boc = message.toBoc().toString('base64');
  const localHash = message.hash().toString('base64');
  const remote = await broadcastBoc(boc);
  return {
    external_message_hash: remote.hash_norm || remote.hash || localHash,
    seqno: state.seqno,
    broadcasted: true,
    signer_mode: 'toncenter_v4r2',
    raw_result: {mode: 'toncenter_v4r2', local_hash: localHash, remote_hash: remote.hash || null, remote_hash_norm: remote.hash_norm || null},
  };
}

async function processSignRequest(data) {
  const validated = validatePayload(data);
  const requestHash = sha256Hex(data.idempotency_key);
  const requestFile = path.join(STATE_DIR, 'requests', `${requestHash}.json`);
  const existing = await readJson(requestFile);
  if (existing?.result) return existing.result;
  if (existing?.status === 'pending' || existing?.status === 'unknown') throw httpError(409, 'Existing signer request is pending reconciliation; refusing duplicate broadcast');

  return withFileLock(`wallet-${data.wallet_code}`, async () => {
    const recheck = await readJson(requestFile);
    if (recheck?.result) return recheck.result;
    if (recheck?.status === 'pending' || recheck?.status === 'unknown') throw httpError(409, 'Existing signer request is pending reconciliation');
    const {ledgerFile} = await reserveDailyLimit(data, validated.amount, requestHash);
    await writeJsonAtomic(requestFile, {
      status: 'pending', request_id: data.request_id, order_id: data.order_id,
      wallet_code: data.wallet_code, amount_nano: data.amount_nano,
      payload_hash: data.payload_hash, schema_hash: data.schema_hash,
      created_at: new Date().toISOString(),
    });
    let broadcastStarted = false;
    try {
      let result;
      if (BACKEND === 'mock') {
        const digest = sha256Hex(`${data.idempotency_key}:${data.wallet_code}:${data.payload_hash}`);
        result = {
          external_message_hash: `remote_mock_${digest}`, seqno: null, broadcasted: false,
          signer_mode: 'remote_mock', raw_result: {mode: 'remote_mock', broadcast: false, request_id: data.request_id},
        };
        await updateLedger(ledgerFile, requestHash, 'simulated');
      } else if (BACKEND === 'toncenter_v4r2') {
        broadcastStarted = true;
        result = await realSignAndBroadcast(data, validated);
        await updateLedger(ledgerFile, requestHash, 'sent');
      } else {
        throw new Error(`Unsupported signer backend: ${BACKEND}`);
      }
      await writeJsonAtomic(requestFile, {status: 'completed', result, completed_at: new Date().toISOString()});
      return result;
    } catch (error) {
      if (broadcastStarted) {
        await updateLedger(ledgerFile, requestHash, 'unknown');
        await writeJsonAtomic(requestFile, {status: 'unknown', error: String(error.message || error), updated_at: new Date().toISOString()});
      } else {
        await updateLedger(ledgerFile, requestHash, 'failed');
        await writeJsonAtomic(requestFile, {status: 'failed', error: String(error.message || error), updated_at: new Date().toISOString()});
      }
      throw error;
    }
  });
}

async function handle(req, res) {
  try {
    if (req.method === 'GET' && req.url === '/health/live') {
      return jsonResponse(res, 200, {status: 'ok', backend: BACKEND});
    }
    if (req.method !== 'POST' || req.url !== '/internal/v1/sign-and-broadcast') throw httpError(404, 'Not found');
    const body = await readBody(req);
    verifyAuth(req, body);
    let data;
    try { data = JSON.parse(body.toString('utf8')); } catch { throw httpError(422, 'Invalid JSON'); }
    const result = await (serial = serial.then(() => processSignRequest(data), () => processSignRequest(data)));
    return jsonResponse(res, 200, result);
  } catch (error) {
    const status = Number(error.status || (String(error.message || '').includes('policy') ? 422 : 503));
    return jsonResponse(res, status, {detail: String(error.message || error)});
  }
}

await ensureDirectories();
if (!SHARED_SECRET || SHARED_SECRET.length < 32) throw new Error('TON_SIGNER_SHARED_SECRET must contain at least 32 characters');
http.createServer(handle).listen(PORT, '0.0.0.0', () => {
  console.log(`TON signer listening on ${PORT}; backend=${BACKEND}`);
});
