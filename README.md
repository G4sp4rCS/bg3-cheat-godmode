# BG3 Party God Mode + Insta-Kill

Make your Baldur's Gate 3 party invincible and able to one-shot enemies. Multiple tools and approaches are included.

## Overview

This repo provides four independent tools for BG3:

| Script                | File                                         | Requires CE? | Features                                   |
|-----------------------|----------------------------------------------|:------------:|--------------------------------------------|
| Overlord Mode         | `scripts/bg3_godmode_instakill.lua`          | Yes          | God Mode, Insta-Kill, Unlimited Resources  |
| Python Overlord       | `python/bg3_overlord.py`                     | Optional     | AOB patch, CE pipe, script generator       |
| God Mode Only         | `scripts/bg3_godmode_party.lua`              | Yes          | Invulnerability only                       |
| Python God Mode       | `python/bg3_godmode.py`                      | No           | Damage patch via pymem                     |

---

## Overlord Mode

God Mode, Insta-Kill, and Unlimited Resources in one script.

**Quick Start:**
1. Open Cheat Engine and attach to bg3_dx11.exe
2. Load cheat table and activate "Register Commands"
3. Open Lua Engine, load `bg3_godmode_instakill.lua`, and execute

**Commands:**
```lua
Overlord:Enable()
Overlord:Disable()
Overlord:GodMode()
Overlord:InstaKill()
Overlord:Unlimited()
Overlord:Status()
```

---

## God Mode Only Script

Invincibility without damage boosts.

**Quick Start:**
1. Open Cheat Engine and attach to bg3_dx11.exe
2. Load cheat table and activate "Register Commands"
3. Open Lua Engine, load `bg3_godmode_party.lua`, and execute

**Commands:**
```lua
GodModeParty:Enable()
GodModeParty:Disable()
GodModeParty:Toggle()
GodModeParty:Status()
GodModeParty:Refresh()
```

---

## Python Overlord

Python implementation with three layers:

| Layer         | Description                                 | Requires CE? |
|---------------|---------------------------------------------|:------------:|
| AOB Patch     | pymem damage function NOP                   | No           |
| CE Lua Pipe   | Sends commands through CE's named pipe      | Yes          |
| Script Gen    | Generates `.lua` files offline              | No           |

**Install:**
```bash
pip install -r requirements.txt
```

**Usage:**
```bash
python python/bg3_overlord.py --godmode -k
python python/bg3_overlord.py --overlord
python python/bg3_overlord.py --generate
python python/bg3_overlord.py --disable
```

---

## Python God Mode

Simpler script using pymem to patch the damage function.

```bash
python python/bg3_godmode.py --all --keep-alive
python python/bg3_godmode.py --interactive
python python/bg3_godmode.py --disable
```

---

## Supported Companions

Lua scripts auto-detect all active party members.

| Companion    | UUID                                    |
|--------------|-----------------------------------------|
| Astarion     | c7c13742-bacd-460a-8f65-f864fe41f255    |
| Gale         | ad9af97d-75da-406a-ae13-7071c563f604    |
| Karlach      | 2c76687d-93a2-477b-8b18-8a14b549304c    |
| Lae'zel      | 58a69333-40bf-8571-d77a-93e42c29260e    |
| Wyll         | c774d764-4a17-48dc-b470-32ace9ce447d    |
| Shadowheart  | 3ed74f06-3c60-42dc-83f6-f034cb47c679    |
| Minsc        | 0de603c5-42e2-4811-9210-f178b28716a8    |
| Jaheira      | 91b6b200-7d00-4d62-8dc9-99e8339dfa1a    |
| Minthara     | 25721313-0c15-4571-acc5-b83e5e09b30c    |
| Halsin       | 7628bc0e-52b8-42a7-856a-13a6fd413323    |
| Dark Urge    | 3130cff0-5765-4b71-b857-a2b00228087b    |
| Custom Tav   | Auto-detected                           |

---

## Multiplayer

| Scenario         | Works? | Notes                                 |
|------------------|:------:|---------------------------------------|
| Host             | Yes    | All party members protected           |
| Client           | No     | Game logic runs on host machine       |

BG3 has no anti-cheat. No risk of bans.

---

## Technical Details

Lua scripts use BG3's Osiris command system via Cheat Engine's "Register Commands". Python scripts patch memory directly or communicate with CE.

---

## Project Structure

```
bg3-party-godmode/
├── scripts/
│   ├── bg3_godmode_instakill.lua
│   └── bg3_godmode_party.lua
├── python/
│   ├── bg3_overlord.py
│   └── bg3_godmode.py
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

---

## License

MIT
