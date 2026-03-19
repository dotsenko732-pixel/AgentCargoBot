# AgentCargoBot

AI-powered freight marketplace Telegram bot for CIS countries.

## Architecture

```
AgentCargoBot/
├── main.py                    # Entry point
├── config.py                  # Settings (from .env)
├── agents/
│   ├── base.py                # Base Claude API agent
│   ├── matcher.py             # Agent-Matcher: cargo ↔ carrier matching
│   ├── pricer.py              # Agent-Pricer: fair market price estimation
│   ├── risk.py                # Agent-Risk: carrier reliability scoring
│   └── orchestrator.py        # Multi-agent coordination
├── bot/
│   ├── handlers/
│   │   ├── start.py           # /start, registration, role selection
│   │   ├── cargo.py           # Cargo posting & management
│   │   ├── carrier.py         # Vehicle management, cargo search
│   │   └── profile.py         # Profile & help
│   └── keyboards/
│       └── main.py            # All keyboard layouts
├── models/
│   ├── database.py            # SQLAlchemy async engine
│   └── entities.py            # User, Vehicle, Cargo, Deal, Review
└── services/
    └── cargo_service.py       # Database operations
```

## AI Agents

| Agent | Purpose |
|-------|---------|
| **Agent-Matcher** | Matches cargo requests with available carriers by route, vehicle type, capacity, and rating |
| **Agent-Pricer** | Estimates fair market price based on distance, weight, vehicle type, and regional rates |
| **Agent-Risk** | Assesses carrier reliability: rating, deal history, verification status |
| **Orchestrator** | Runs all three agents in parallel when a new cargo is posted |

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Get an [Anthropic API key](https://console.anthropic.com/)
3. Configure:

```bash
cp .env.example .env
# Edit .env with your tokens
```

4. Install and run:

```bash
pip install -r requirements.txt
python main.py
```

## Docker

```bash
docker build -t agentcargobot .
docker run --env-file .env agentcargobot
```

## User Flow

1. User sends `/start` → selects role (shipper/carrier) → shares phone
2. **Shipper**: posts cargo → AI estimates price + finds matching carriers + assesses risk
3. **Carrier**: adds vehicle → AI proactively suggests matching cargos
