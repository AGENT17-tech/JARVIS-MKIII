/**
 * JARVIS-MKIII — WhatsApp Bridge (Baileys)
 * Uses WhatsApp WebSocket API directly — no Puppeteer/Chrome required.
 *
 * Outbound: POST http://localhost:8000/whatsapp/incoming  (message received)
 *           POST http://localhost:8000/whatsapp/status    (connected/disconnected)
 * Inbound:  POST /send    { chat_id, message }
 *           GET  /status
 *           GET  /messages
 */

'use strict';

const { default: makeWASocket, useMultiFileAuthState,
        DisconnectReason } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const qrcode  = require('qrcode-terminal');
const express = require('express');
const axios   = require('axios');
const fs      = require('fs');

// ── Config ────────────────────────────────────────────────────────────────────
const BRIDGE_PORT      = 3001;
const BACKEND_URL      = 'http://localhost:8000';
const MAX_RECONNECTS   = 3;
const RATE_LIMIT_FILE  = './rate_limited.json';

// ── State ─────────────────────────────────────────────────────────────────────
let sock              = null;
let status            = 'disconnected';
let phone             = null;
let reconnectAttempts = 0;
const messageQueue    = [];

// ── Rate-limit persistence ────────────────────────────────────────────────────
function isRateLimited() {
    try {
        const { timestamp } = JSON.parse(fs.readFileSync(RATE_LIMIT_FILE, 'utf8'));
        return (Date.now() - timestamp) < 10 * 60 * 1000;
    } catch { return false; }
}

function setRateLimited() {
    fs.writeFileSync(RATE_LIMIT_FILE, JSON.stringify({ timestamp: Date.now() }));
}

function clearRateLimited() {
    try { fs.unlinkSync(RATE_LIMIT_FILE); } catch {}
}

// ── Helper: POST to backend with retry ───────────────────────────────────────
async function postToBackend(path, data, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            await axios.post(`${BACKEND_URL}${path}`, data, { timeout: 5000 });
            return;
        } catch (err) {
            console.warn(`[Bridge] POST ${path} failed (attempt ${i + 1}): ${err.message}`);
            if (i < retries - 1) await new Promise(r => setTimeout(r, 3000));
        }
    }
}

// ── WhatsApp connection ───────────────────────────────────────────────────────
async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('./baileys_auth');

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: require('pino')({ level: 'silent' })
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('[WA] Scan this QR code:');
            qrcode.generate(qr, { small: true });
            status = 'waiting_qr';
            reconnectAttempts = 0;
            clearRateLimited();
        }

        if (connection === 'close') {
            const shouldReconnect =
                (lastDisconnect?.error instanceof Boom)
                    ? lastDisconnect.error.output.statusCode !== DisconnectReason.loggedOut
                    : true;
            status = 'disconnected';
            phone  = null;
            await postToBackend('/whatsapp/status', { status: 'disconnected', phone: null });

            if (shouldReconnect) {
                reconnectAttempts++;
                if (reconnectAttempts >= MAX_RECONNECTS) {
                    console.log('[WA] Max reconnects reached. Waiting 10 min before retry.');
                    status = 'rate_limited';
                    setRateLimited();
                    setTimeout(() => {
                        clearRateLimited();
                        reconnectAttempts = 0;
                        connectToWhatsApp();
                    }, 10 * 60 * 1000);
                    return;
                }
                const delay = Math.min(reconnectAttempts * 5000, 30000);
                console.log(`[WA] Reconnecting in ${delay / 1000}s (attempt ${reconnectAttempts})`);
                setTimeout(connectToWhatsApp, delay);
            } else {
                console.log('[WA] Logged out — not reconnecting.');
            }
        } else if (connection === 'open') {
            console.log('[WA] Client is ready! Connected as', sock.user?.id);
            reconnectAttempts = 0;
            clearRateLimited();
            status = 'connected';
            phone  = sock.user?.id;
            await postToBackend('/whatsapp/status', { status: 'connected', phone });
        }
    });

    sock.ev.on('messages.upsert', async ({ messages }) => {
        for (const msg of messages) {
            if (!msg.message || msg.key.fromMe) continue;
            const body =
                msg.message?.conversation ||
                msg.message?.extendedTextMessage?.text || '';
            if (!body) continue;
            const from     = msg.key.remoteJid;
            const fromName = msg.pushName || from;
            const payload  = {
                from,
                from_name:  fromName,
                body,
                timestamp:  msg.messageTimestamp,
                is_group:   from.endsWith('@g.us'),
                chat_id:    from,
            };
            console.log(`[Bridge] ← ${fromName}: ${body.slice(0, 80)}`);
            messageQueue.push(payload);
            if (messageQueue.length > 50) messageQueue.shift();
            await postToBackend('/whatsapp/incoming', payload);
        }
    });
}

// ── Express API server ────────────────────────────────────────────────────────
const app = express();
app.use(express.json());

// GET /status
app.get('/status', (req, res) => {
    res.json({ status, phone });
});

// POST /send — send a WhatsApp message
app.post('/send', async (req, res) => {
    const { chat_id, message } = req.body;
    if (!chat_id || !message) {
        return res.status(400).json({ error: 'chat_id and message are required' });
    }
    if (!sock || status !== 'connected') {
        return res.status(503).json({ error: `WhatsApp not connected (status: ${status})` });
    }
    try {
        await sock.sendMessage(chat_id, { text: message });
        console.log(`[Bridge] → ${chat_id}: ${message.slice(0, 80)}`);
        res.json({ ok: true });
    } catch (err) {
        console.error('[Bridge] Send failed:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// GET /messages — recent received messages
app.get('/messages', (req, res) => {
    res.json(messageQueue);
});

app.listen(BRIDGE_PORT, () => {
    console.log(`[Bridge] Express listening on :${BRIDGE_PORT}`);
});

// ── Start ─────────────────────────────────────────────────────────────────────
// Do not auto-connect on boot if a rate-limit cooldown is still active.
// Wait for it to expire, then connect automatically; or restart manually
// with `node whatsapp_bridge.js` after the 10-minute window passes.
if (isRateLimited()) {
    const { timestamp } = JSON.parse(fs.readFileSync(RATE_LIMIT_FILE, 'utf8'));
    const remaining = 10 * 60 * 1000 - (Date.now() - timestamp);
    console.log(`[WA] Rate-limited from previous session. Resuming in ${Math.ceil(remaining / 1000)}s.`);
    status = 'rate_limited';
    setTimeout(() => {
        clearRateLimited();
        reconnectAttempts = 0;
        connectToWhatsApp();
    }, remaining);
} else {
    connectToWhatsApp();
}
