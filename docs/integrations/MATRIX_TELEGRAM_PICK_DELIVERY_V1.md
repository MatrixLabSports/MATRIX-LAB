# MATRIX-LAB-SPORTS — Telegram Pick Delivery Architecture V1

Effective date: 2026-09-28
Status: PREPARED / USER TELEGRAM SETUP PENDING
REAL_MONEY: BLOCKED
AUTOMATIC_WAGERING: FALSE

## Purpose

Deliver governed MATRIX picks to Telegram without creating a parallel decision system.

Telegram is a notification surface only. It may not create, alter, promote or
reinterpret a pick.

## Required upstream order

P_MATRIX
→ exact market identity
→ valid execution-book price
→ positive expected value
→ calibration/risk gate
→ prematch price freeze
→ Telegram pick card
→ Telegram send
→ append-only dispatch ledger

## Modes

### SHADOW

Allowed while REAL_MONEY is BLOCKED.

Mandatory properties:
- message header says MATRIX SHADOW — NO APOSTAR;
- stake is exactly zero;
- real_money_gate_open is false;
- automatic_wagering is false.

### CONTROLLED_LIVE

Allowed only after separate MATRIX governance explicitly opens real money.

Mandatory properties:
- calibration_gate_pass is true;
- real_money_gate_open is true;
- positive governed stake exists;
- automatic_wagering remains false;
- source price freeze is prematch and hash-addressed.

## Hard gates

- football and tennis only;
- execution bookmaker must be in the governed Colombia execution portfolio;
- Pinnacle/reference-only books cannot be emitted as execution destinations;
- decimal odds must be strictly > 1.50;
- P_MATRIX must be between 0 and 1;
- implied probability must equal 1 / decimal odds;
- expected value must equal P_MATRIX * decimal odds - 1;
- expected value must be positive;
- odds may not be used as model input;
- freeze must be strictly before event start;
- duplicate pick IDs cannot be dispatched twice;
- bot token is never stored in repository files or logs;
- Telegram cannot open REAL_MONEY.

## Secret names

- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Both must be stored as GitHub Actions secrets. The bot token must never be pasted
into a MATRIX artifact or committed to the repository.

## User setup

1. Create a Telegram bot with @BotFather using /newbot.
2. Store the generated token as GitHub Actions secret TELEGRAM_BOT_TOKEN.
3. Start a direct chat with the bot or add the bot to the desired private group/channel.
4. Use the MATRIX Telegram activation workflow in discover mode to identify the chat.
5. Store the selected chat id as GitHub Actions secret TELEGRAM_CHAT_ID.
6. Run send_test. The test message must say PRUEBA / NO APOSTAR and REAL_MONEY: BLOCKED.

## Physical components

- app/notifications/telegram_pick_notifier.py
  Pure validation, rendering and append-only dispatch-ledger logic. No network.

- tools/telegram_pick_transport.py
  Telegram sendMessage network transport.

- tools/telegram_bot_probe.py
  getMe, getUpdates chat discovery and governed connection test.

- .github/workflows/matrix-telegram-bot-activation.yml
  Secure activation workflow. Push runs tests only. Manual execution is required
  for probe, discover or send_test.

## Current activation state

Architecture is prepared, but Telegram is not active until both secrets are
physically configured and a successful connection test is persisted/verified.

No current football or tennis output may be represented as a real-money pick
while REAL_MONEY remains BLOCKED.
