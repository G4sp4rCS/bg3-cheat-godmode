"""
================================================================================
  BG3 OVERLORD MODE — Python Standalone
  
  Full god mode + insta-kill + unlimited resources for all party members.
  
  Architecture:
    Layer 1: pymem AOB patch — Standalone damage nullification (no CE needed)
    Layer 2: CE Lua bridge   — Osiris boost injection via CE named pipe
    Layer 3: Script generator — Creates ready-to-execute .lua file for CE
  
  Modes:
    --godmode         AOB-based god mode only (pymem, no CE required)
    --overlord        Full Overlord: god mode + instakill + unlimited (needs CE)
    --generate        Generate .lua script file (no live CE connection needed)
    --interactive     Interactive CLI with all options
    --disable         Remove AOB patches and restore original code
    
  Requirements:
    pip install pymem pywin32
    Run as Administrator (required for process memory access)
    
  For --overlord mode:
    1. CE must be running with bg3 cheat table loaded
    2. "Register Commands" (entry [103]) must be ACTIVE
    3. CE Lua Pipe Server must be enabled (CE Settings > Extra > Lua pipe)
       OR use --generate to create a .lua file and paste it manually
    
  Author: DarkForge-X
  Target: Baldur's Gate 3 v4.1.1+ (bg3_dx11.exe / bg3.exe)
================================================================================
"""

import sys
import os
import time
import struct
import argparse
import logging
import json
import ctypes
import ctypes.wintypes
from typing import Optional, List, Dict, Tuple
from pathlib import Path

try:
    import pymem
    import pymem.process
except ImportError:
    print("[!] pymem not installed. Run: pip install pymem")
    sys.exit(1)

# Try to import win32 pipe support (optional, for CE connection)
HAS_WIN32 = False
try:
    import win32file
    import win32pipe
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    pass

# Fallback: use ctypes for named pipe access if pywin32 not available
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
PIPE_READMODE_MESSAGE = 0x00000002
INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1).value

kernel32 = ctypes.windll.kernel32


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("BG3Overlord")


# ============================================================================
# CONFIGURATION
# ============================================================================

PROCESS_NAMES = ["bg3_dx11.exe", "bg3.exe"]

# AOB pattern: cmp byte ptr [rcx+1C8], 00 | jne <skip_damage>
DAMAGE_FUNC_AOB = b"\x80\xB9\xC8\x01\x00\x00\x00\x0F\x85"
JNE_OFFSET = 7
ORIGINAL_BYTES = bytes([0x0F, 0x85])
PATCHED_BYTES_ALL = bytes([0x90, 0xE9])  # NOP + JMP (unconditional)

# CE Named Pipe for Lua execution
CE_PIPE_NAMES = [
    r"\\.\pipe\celuapipe",
    r"\\.\pipe\celuapipe_server",
]

# Stagger delay between characters (seconds)
STAGGER_DELAY = 2.0

# ============================================================================
# COMPANION DATABASE
# ============================================================================

COMPANION_DB = {
    "Astarion":     "c7c13742-bacd-460a-8f65-f864fe41f255",
    "Gale":         "ad9af97d-75da-406a-ae13-7071c563f604",
    "Karlach":      "2c76687d-93a2-477b-8b18-8a14b549304c",
    "Laezel":       "58a69333-40bf-8571-d77a-93e42c29260e",
    "Wyll":         "c774d764-4a17-48dc-b470-32ace9ce447d",
    "ShadowHeart":  "3ed74f06-3c60-42dc-83f6-f034cb47c679",
    "Minsc":        "0de603c5-42e2-4811-9210-f178b28716a8",
    "Jaheira":      "91b6b200-7d00-4d62-8dc9-99e8339dfa1a",
    "Minthara":     "25721313-0c15-4571-acc5-b83e5e09b30c",
    "Halsin":       "7628bc0e-52b8-42a7-856a-13a6fd413323",
    "DarkUrge":     "3130cff0-5765-4b71-b857-a2b00228087b",
}

# ============================================================================
# BOOST DEFINITIONS (ALL LIVE-TESTED AND CONFIRMED WORKING)
# ============================================================================

GOD_MODE_STATUS = "INVULNERABLE"

GOD_MODE_BOOSTS = [
    "DamageReduction(All, Flat, 100)",
]

INSTAKILL_BOOSTS = [
    "DamageBonus(20d12+50)",
    "WeaponEnchantment(10)",
    "Ability(Strength, 30)",
    "Ability(Dexterity, 30)",
    "Ability(Constitution, 30)",
    "Ability(Intelligence, 30)",
    "Ability(Wisdom, 30)",
    "Ability(Charisma, 30)",
    "RollBonus(Attack, 30)",
    "SpellSaveDC(30)",
    "CriticalHit(AttackTarget, Success, Always)",
    "IF(SpellAttack()):DamageBonus(10d10+30)",
]

INSTAKILL_PASSIVES = [
    "ImprovedCritical",
    "SavageAttacker",
    "BrutalCritical",
    "GreatWeaponMaster_BonusAttack",
]

UNLIMITED_BOOSTS = [
    "ActionResource(ActionPoint, 10, 0)",
    "ActionResource(BonusActionPoint, 10, 0)",
    "ActionResource(Movement, 100, 0)",
    "ActionResource(SpellSlot, 99, 1)",
    "ActionResource(SpellSlot, 99, 2)",
    "ActionResource(SpellSlot, 99, 3)",
    "ActionResource(SpellSlot, 99, 4)",
    "ActionResource(SpellSlot, 99, 5)",
    "ActionResource(SpellSlot, 99, 6)",
    "ActionResource(ChannelDivinity, 99, 0)",
    "ActionResource(KiPoint, 99, 0)",
    "ActionResource(BardicInspiration, 99, 0)",
    "ActionResource(RageCharge, 99, 0)",
    "ActionResource(SorceryPoint, 99, 0)",
    "ActionResource(SuperiorityDie, 99, 0)",
    "ActionResource(WarlockSpellSlot, 99, 0)",
    "ActionResource(LayOnHandsCharge, 99, 0)",
]


# ============================================================================
# CE LUA PIPE CLIENT
# ============================================================================

class CELuaPipe:
    """
    Connect to Cheat Engine's Lua Pipe Server for remote Lua execution.
    
    CE exposes a named pipe when you enable:
      Settings > Extra > Enable Lua Pipe Server
    
    Protocol: Send Lua code as UTF-8 bytes, receive result.
    """
    
    def __init__(self):
        self.pipe_handle = None
        self.connected = False
        self.pipe_name = ""
    
    def connect(self) -> bool:
        """Try to connect to CE's Lua pipe."""
        # Method 1: pywin32
        if HAS_WIN32:
            return self._connect_win32()
        # Method 2: ctypes fallback
        return self._connect_ctypes()
    
    def _connect_win32(self) -> bool:
        """Connect using pywin32."""
        for pipe_name in CE_PIPE_NAMES:
            try:
                self.pipe_handle = win32file.CreateFile(
                    pipe_name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None,
                    win32file.OPEN_EXISTING,
                    0, None
                )
                win32pipe.SetNamedPipeHandleState(
                    self.pipe_handle,
                    win32pipe.PIPE_READMODE_MESSAGE,
                    None, None
                )
                self.connected = True
                self.pipe_name = pipe_name
                log.info(f"Connected to CE Lua pipe: {pipe_name}")
                return True
            except pywintypes.error:
                continue
        
        # Try PID-specific pipes
        return self._try_pid_pipes_win32()
    
    def _try_pid_pipes_win32(self) -> bool:
        """Try CE pipes with specific PIDs."""
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq cheatengine*.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split("\n"):
                if "cheatengine" in line.lower():
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid = parts[1].strip('"')
                        pipe_name = f"\\\\.\\pipe\\celuapipe_{pid}"
                        try:
                            self.pipe_handle = win32file.CreateFile(
                                pipe_name,
                                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                0, None,
                                win32file.OPEN_EXISTING,
                                0, None
                            )
                            self.connected = True
                            self.pipe_name = pipe_name
                            log.info(f"Connected to CE Lua pipe: {pipe_name}")
                            return True
                        except pywintypes.error:
                            continue
        except Exception:
            pass
        return False
    
    def _connect_ctypes(self) -> bool:
        """Connect using ctypes (no pywin32 dependency)."""
        for pipe_name in CE_PIPE_NAMES:
            handle = kernel32.CreateFileW(
                pipe_name,
                GENERIC_READ | GENERIC_WRITE,
                0, None,
                OPEN_EXISTING,
                0, None
            )
            if handle != INVALID_HANDLE_VALUE:
                mode = ctypes.wintypes.DWORD(PIPE_READMODE_MESSAGE)
                kernel32.SetNamedPipeHandleState(
                    handle, ctypes.byref(mode), None, None
                )
                self.pipe_handle = handle
                self.connected = True
                self.pipe_name = pipe_name
                log.info(f"Connected to CE Lua pipe: {pipe_name}")
                return True
        return False
    
    def execute(self, lua_code: str, timeout: float = 10.0) -> Optional[str]:
        """Execute Lua code in CE and return the result."""
        if not self.connected:
            log.error("Not connected to CE pipe")
            return None
        
        data = lua_code.encode("utf-8")
        
        if HAS_WIN32:
            return self._execute_win32(data, timeout)
        return self._execute_ctypes(data, timeout)
    
    def _execute_win32(self, data: bytes, timeout: float) -> Optional[str]:
        """Execute via pywin32."""
        try:
            win32file.WriteFile(self.pipe_handle, data)
            _, result = win32file.ReadFile(self.pipe_handle, 65536)
            return result.decode("utf-8", errors="replace")
        except pywintypes.error as e:
            log.error(f"CE pipe error: {e}")
            return None
    
    def _execute_ctypes(self, data: bytes, timeout: float) -> Optional[str]:
        """Execute via ctypes."""
        try:
            written = ctypes.wintypes.DWORD()
            kernel32.WriteFile(
                self.pipe_handle, data, len(data),
                ctypes.byref(written), None
            )
            
            buf = ctypes.create_string_buffer(65536)
            read = ctypes.wintypes.DWORD()
            kernel32.ReadFile(
                self.pipe_handle, buf, 65536,
                ctypes.byref(read), None
            )
            return buf.raw[:read.value].decode("utf-8", errors="replace")
        except Exception as e:
            log.error(f"CE pipe error: {e}")
            return None
    
    def close(self):
        """Close the pipe connection."""
        if self.pipe_handle:
            if HAS_WIN32:
                try:
                    win32file.CloseHandle(self.pipe_handle)
                except Exception:
                    pass
            else:
                kernel32.CloseHandle(self.pipe_handle)
            self.pipe_handle = None
            self.connected = False


# ============================================================================
# PYMEM AOB ENGINE (Layer 1 — Standalone God Mode)
# ============================================================================

class AOBGodMode:
    """AOB-based damage nullification using pymem. No CE required."""
    
    def __init__(self):
        self.pm: Optional[pymem.Pymem] = None
        self.process_name = ""
        self.module_base = 0
        self.module_size = 0
        self.damage_func_addr = 0
        self.jne_addr = 0
        self.original_backup = b""
        self.patched = False
    
    def attach(self) -> bool:
        """Attach to BG3 process."""
        for name in PROCESS_NAMES:
            try:
                self.pm = pymem.Pymem(name)
                self.process_name = name
                log.info(f"Attached to {name} (PID: {self.pm.process_id})")
                
                module = pymem.process.module_from_name(
                    self.pm.process_handle, name
                )
                if module:
                    self.module_base = module.lpBaseOfDll
                    self.module_size = module.SizeOfImage
                    log.info(f"Module: 0x{self.module_base:X} ({self.module_size // (1024*1024)} MB)")
                return True
            except pymem.exception.ProcessNotFound:
                continue
            except pymem.exception.CouldNotOpenProcess:
                log.error(f"Found {name} but can't open. Run as Administrator!")
                return False
        
        log.error("BG3 not found. Make sure the game is running.")
        return False
    
    def scan(self) -> bool:
        """Find the damage function via AOB scan."""
        log.info("Scanning for damage function AOB...")
        
        try:
            module_bytes = self.pm.read_bytes(self.module_base, self.module_size)
        except Exception as e:
            log.error(f"Failed to read module: {e}")
            return False
        
        idx = module_bytes.find(DAMAGE_FUNC_AOB)
        if idx == -1:
            log.error("AOB pattern not found! Game version may be incompatible.")
            return False
        
        self.damage_func_addr = self.module_base + idx
        self.jne_addr = self.damage_func_addr + JNE_OFFSET
        
        log.info(f"Damage function: 0x{self.damage_func_addr:X}")
        log.info(f"JNE instruction: 0x{self.jne_addr:X}")
        
        current = self.pm.read_bytes(self.jne_addr, 2)
        if current == ORIGINAL_BYTES:
            log.info("Bytes verified: 0F 85 (unpatched)")
        elif current == PATCHED_BYTES_ALL:
            log.warning("Already patched (90 E9)")
            self.patched = True
        else:
            log.warning(f"Unexpected bytes: {current.hex()}")
        
        return True
    
    def enable(self) -> bool:
        """Patch JNE → NOP+JMP to skip all damage."""
        if self.patched:
            log.info("Already patched")
            return True
        
        self.original_backup = self.pm.read_bytes(self.jne_addr, 2)
        self.pm.write_bytes(self.jne_addr, PATCHED_BYTES_ALL, 2)
        
        verify = self.pm.read_bytes(self.jne_addr, 2)
        if verify == PATCHED_BYTES_ALL:
            self.patched = True
            log.info("AOB GOD MODE: ACTIVE (all entities invincible)")
            return True
        
        log.error("Patch verification failed")
        return False
    
    def disable(self) -> bool:
        """Restore original bytes."""
        if not self.patched or not self.original_backup:
            return True
        
        self.pm.write_bytes(self.jne_addr, self.original_backup, 2)
        self.patched = False
        log.info("AOB GOD MODE: DISABLED (original bytes restored)")
        return True
    
    def cleanup(self):
        """Close process handle."""
        if self.pm:
            try:
                self.pm.close_process()
            except Exception:
                pass


# ============================================================================
# OSIRIS BOOST ENGINE (Layer 2 — CE Lua Pipe)
# ============================================================================

class OsirisBoostEngine:
    """
    Sends Osiris boost commands to BG3 via CE's Lua execution pipe.
    Requires CE running with "Register Commands" active.
    """
    
    def __init__(self, pipe: CELuaPipe):
        self.pipe = pipe
        self.party: List[Dict] = []
    
    def check_prereqs(self) -> bool:
        """Verify CE has the required functions loaded."""
        result = self.pipe.execute(
            'return type(AddBoosts) == "function" and type(GetHostCharacter) == "function"'
        )
        if result and "true" in result.lower():
            log.info("CE command functions verified")
            return True
        log.error("CE command functions not available. Activate 'Register Commands' in cheat table.")
        return False
    
    def detect_party(self) -> List[Dict]:
        """Detect active party members via HP probe."""
        lua_code = """
local party = {}
local host = GetHostCharacter()

-- Probe known companions
local db = {
""" + "\n".join(
    f'  {{name="{name}", uuid="{uuid}"}},'
    for name, uuid in COMPANION_DB.items()
) + """
}

for _, c in ipairs(db) do
  local ok, _ = pcall(function()
    SetArgToString(0, c.uuid)
    ClearArg(1)
    ExecuteCall("GetHitpoints")
  end)
  if ok then
    local hp = GetArgAsInteger(1) or 0
    if hp > 0 and hp < 50000 then
      table.insert(party, c.name .. "|" .. c.uuid .. "|" .. tostring(hp))
    end
  end
end

-- Check for custom Tav (host not in companion DB)
local hostFound = false
for _, p in ipairs(party) do
  if p:find(host) then hostFound = true; break end
end
if not hostFound and host and host ~= "" then
  local ok, _ = pcall(function()
    SetArgToString(0, host)
    ClearArg(1)
    ExecuteCall("GetHitpoints")
  end)
  if ok then
    local hp = GetArgAsInteger(1) or 0
    if hp > 0 then
      table.insert(party, 1, "CustomTav|" .. host .. "|" .. tostring(hp))
    end
  end
end

return table.concat(party, ";")
"""
        result = self.pipe.execute(lua_code)
        self.party = []
        
        if result:
            for entry in result.strip().split(";"):
                parts = entry.split("|")
                if len(parts) == 3:
                    self.party.append({
                        "name": parts[0],
                        "uuid": parts[1],
                        "hp": int(parts[2]) if parts[2].isdigit() else 0
                    })
        
        log.info(f"Detected {len(self.party)} party members:")
        for m in self.party:
            log.info(f"  {m['name']}: {m['hp']} HP ({m['uuid'][:12]}...)")
        
        return self.party
    
    def apply_boosts_to_character(self, uuid: str, name: str,
                                   god: bool = True, instakill: bool = True,
                                   unlimited: bool = True) -> bool:
        """Apply all enabled boost categories to a single character."""
        commands = []
        
        if god:
            commands.append(f'ApplyStatus("{uuid}", "INVULNERABLE", -1, 1, 0)')
            for b in GOD_MODE_BOOSTS:
                commands.append(f'AddBoosts("{uuid}", "{b}", "", "")')
        
        if instakill:
            for b in INSTAKILL_BOOSTS:
                commands.append(f'AddBoosts("{uuid}", "{b}", "", "")')
            for p in INSTAKILL_PASSIVES:
                commands.append(f'AddPassive("{uuid}", "{p}")')
        
        if unlimited:
            for b in UNLIMITED_BOOSTS:
                commands.append(f'AddBoosts("{uuid}", "{b}", "", "")')
        
        # Wrap all commands in pcall for safety
        lua_code = f'local ok, fail = 0, 0\n'
        for cmd in commands:
            lua_code += f'if pcall(function() {cmd} end) then ok=ok+1 else fail=fail+1 end\n'
        lua_code += f'return string.format("{name}: %d OK, %d FAIL", ok, fail)\n'
        
        result = self.pipe.execute(lua_code)
        if result:
            log.info(f"  {result.strip()}")
            return True
        
        log.error(f"  {name}: No response from CE")
        return False
    
    def apply_all_staggered(self, god: bool = True, instakill: bool = True,
                             unlimited: bool = True) -> bool:
        """Apply boosts to all party members with stagger delays."""
        if not self.party:
            self.detect_party()
        
        if not self.party:
            log.error("No party members detected!")
            return False
        
        # Heal party first
        self.pipe.execute("""
pcall(function()
  SetArgToString(0, GetHostCharacter())
  ExecuteCall("RestoreParty")
end)
return "healed"
""")
        log.info("Party healed")
        
        total = len(self.party)
        for i, member in enumerate(self.party):
            log.info(f"[{i+1}/{total}] Applying to {member['name']}...")
            self.apply_boosts_to_character(
                member["uuid"], member["name"],
                god=god, instakill=instakill, unlimited=unlimited
            )
            
            if i < total - 1:
                log.info(f"  Waiting {STAGGER_DELAY}s before next character...")
                time.sleep(STAGGER_DELAY)
        
        log.info("All boosts applied!")
        return True
    
    def remove_all(self) -> bool:
        """Remove all boosts from all party members."""
        lua_code = """
local COMPANION_DB = {
""" + "\n".join(
    f'  "{uuid}",'
    for uuid in COMPANION_DB.values()
) + """
}

-- Also get host
local host = GetHostCharacter()
if host and host ~= "" then table.insert(COMPANION_DB, host) end

local removed = 0
for _, uuid in ipairs(COMPANION_DB) do
  pcall(function() RemoveStatus(uuid, "INVULNERABLE", 0) end)
"""
        for b in GOD_MODE_BOOSTS + INSTAKILL_BOOSTS + UNLIMITED_BOOSTS:
            lua_code += f'  pcall(function() RemoveBoosts(uuid, "{b}", 0, 0, 0) end)\n'
        for p in INSTAKILL_PASSIVES:
            lua_code += f'  pcall(function() RemovePassive(uuid, "{p}") end)\n'
        
        lua_code += """
  removed = removed + 1
end
return string.format("Cleaned %d characters", removed)
"""
        result = self.pipe.execute(lua_code)
        if result:
            log.info(result.strip())
        return True


# ============================================================================
# SCRIPT GENERATOR (Layer 3 — Offline .lua generation)
# ============================================================================

class ScriptGenerator:
    """
    Generate standalone .lua files that can be pasted into CE's Lua Engine.
    No live connection to CE required.
    """
    
    @staticmethod
    def generate_overlord_script(
        output_path: str = "bg3_overlord_generated.lua",
        god: bool = True,
        instakill: bool = True,
        unlimited: bool = True,
        custom_uuids: Optional[List[str]] = None
    ) -> str:
        """Generate a complete Overlord .lua script."""
        
        lines = []
        lines.append('-- ============================================')
        lines.append('-- BG3 OVERLORD — Auto-Generated Lua Script')
        lines.append(f'-- Generated: {time.strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append('-- ')
        lines.append('-- Prerequisites:')
        lines.append('--   1. Load your save in BG3')
        lines.append('--   2. Activate "Register Commands" in cheat table')
        lines.append('--   3. Paste this into CE Lua Engine (Ctrl+Alt+L)')
        lines.append('-- ============================================')
        lines.append('')
        
        # Companion database
        lines.append('local COMPANIONS = {')
        for name, uuid in COMPANION_DB.items():
            lines.append(f'  {{name="{name}", uuid="{uuid}"}},')
        lines.append('}')
        lines.append('')
        
        # Party detection
        lines.append('-- Detect active party members')
        lines.append('local party = {}')
        lines.append('local host = GetHostCharacter()')
        lines.append('')
        lines.append('for _, c in ipairs(COMPANIONS) do')
        lines.append('  local ok = pcall(function()')
        lines.append('    SetArgToString(0, c.uuid); ClearArg(1)')
        lines.append('    ExecuteCall("GetHitpoints")')
        lines.append('  end)')
        lines.append('  if ok then')
        lines.append('    local hp = GetArgAsInteger(1) or 0')
        lines.append('    if hp > 0 and hp < 50000 then')
        lines.append('      table.insert(party, {name=c.name, uuid=c.uuid, hp=hp})')
        lines.append('    end')
        lines.append('  end')
        lines.append('end')
        lines.append('')
        lines.append('-- Check custom Tav')
        lines.append('local hostFound = false')
        lines.append('for _, m in ipairs(party) do')
        lines.append('  if m.uuid == host then hostFound = true; break end')
        lines.append('end')
        lines.append('if not hostFound and host ~= "" then')
        lines.append('  local ok = pcall(function()')
        lines.append('    SetArgToString(0, host); ClearArg(1)')
        lines.append('    ExecuteCall("GetHitpoints")')
        lines.append('  end)')
        lines.append('  if ok then')
        lines.append('    local hp = GetArgAsInteger(1) or 0')
        lines.append('    if hp > 0 then')
        lines.append('      table.insert(party, 1, {name="Custom Tav", uuid=host, hp=hp})')
        lines.append('    end')
        lines.append('  end')
        lines.append('end')
        lines.append('')
        
        # Custom UUIDs
        if custom_uuids:
            lines.append('-- Custom UUIDs added by user')
            for uuid in custom_uuids:
                lines.append(f'table.insert(party, {{name="Custom", uuid="{uuid}", hp=1}})')
            lines.append('')
        
        lines.append('print(string.format("[OVERLORD] Detected %d party members", #party))')
        lines.append('for _, m in ipairs(party) do')
        lines.append('  print(string.format("  - %s (HP: %d)", m.name, m.hp))')
        lines.append('end')
        lines.append('')
        
        # Heal party
        lines.append('-- Heal party')
        lines.append('pcall(function()')
        lines.append('  SetArgToString(0, GetHostCharacter())')
        lines.append('  ExecuteCall("RestoreParty")')
        lines.append('end)')
        lines.append('print("[OVERLORD] Party healed")')
        lines.append('')
        
        # Staggered apply with timer
        lines.append('-- Staggered apply (2s delay between characters)')
        lines.append('local charIdx = 1')
        lines.append('')
        lines.append('local function applyToChar(m)')
        lines.append('  print(string.format("[OVERLORD] Applying to %s...", m.name))')
        
        if god:
            lines.append('  -- God Mode')
            lines.append(f'  pcall(function() ApplyStatus(m.uuid, "{GOD_MODE_STATUS}", -1, 1, 0) end)')
            for b in GOD_MODE_BOOSTS:
                lines.append(f'  pcall(function() AddBoosts(m.uuid, "{b}", "", "") end)')
        
        if instakill:
            lines.append('  -- Insta-Kill')
            for b in INSTAKILL_BOOSTS:
                lines.append(f'  pcall(function() AddBoosts(m.uuid, "{b}", "", "") end)')
            lines.append('  -- Passives')
            for p in INSTAKILL_PASSIVES:
                lines.append(f'  pcall(function() AddPassive(m.uuid, "{p}") end)')
        
        if unlimited:
            lines.append('  -- Unlimited Resources')
            for b in UNLIMITED_BOOSTS:
                lines.append(f'  pcall(function() AddBoosts(m.uuid, "{b}", "", "") end)')
        
        lines.append('  print(string.format("  %s: DONE", m.name))')
        lines.append('end')
        lines.append('')
        
        # Timer-based staggered execution
        lines.append('-- Apply first character immediately')
        lines.append('if #party > 0 then')
        lines.append('  applyToChar(party[1])')
        lines.append('  charIdx = 2')
        lines.append('end')
        lines.append('')
        lines.append('-- Schedule remaining with 2-second intervals')
        lines.append('if charIdx <= #party then')
        lines.append('  local timer = createTimer(getMainForm())')
        lines.append('  timer.Interval = 2000')
        lines.append('  timer.OnTimer = function()')
        lines.append('    pcall(function()')
        lines.append('      if charIdx <= #party then')
        lines.append('        applyToChar(party[charIdx])')
        lines.append('        charIdx = charIdx + 1')
        lines.append('      end')
        lines.append('      if charIdx > #party then')
        lines.append('        timer.Enabled = false')
        lines.append('        timer:Destroy()')
        lines.append('        print("")')
        lines.append('        print("================================================================")')
        lines.append('        print("  OVERLORD MODE FULLY ACTIVE")')
        
        active = []
        if god: active.append("INVINCIBLE")
        if instakill: active.append("ONE-SHOT EVERYTHING")
        if unlimited: active.append("UNLIMITED RESOURCES")
        
        for a in active:
            lines.append(f'        print("  - {a}")')
        
        lines.append('        print("================================================================")')
        lines.append('      end')
        lines.append('    end)')
        lines.append('  end')
        lines.append('  timer.Enabled = true')
        lines.append('end')
        lines.append('')
        
        # Refresh timer for INVULNERABLE status
        if god:
            lines.append('-- Refresh INVULNERABLE every 30s')
            lines.append('local refreshTimer = createTimer(getMainForm())')
            lines.append('refreshTimer.Interval = 30000')
            lines.append('refreshTimer.OnTimer = function()')
            lines.append('  pcall(function()')
            lines.append('    for _, m in ipairs(party) do')
            lines.append(f'      pcall(function() ApplyStatus(m.uuid, "{GOD_MODE_STATUS}", -1, 1, 0) end)')
            lines.append('    end')
            lines.append('  end)')
            lines.append('end')
            lines.append('refreshTimer.Enabled = true')
        
        script = "\n".join(lines)
        
        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)
        
        log.info(f"Generated script: {output_path} ({len(lines)} lines)")
        return output_path
    
    @staticmethod
    def generate_disable_script(output_path: str = "bg3_overlord_disable.lua") -> str:
        """Generate a script to remove all Overlord boosts."""
        lines = []
        lines.append('-- BG3 OVERLORD DISABLE — Remove all boosts')
        lines.append(f'-- Generated: {time.strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append('')
        lines.append('local ALL_UUIDS = {')
        for name, uuid in COMPANION_DB.items():
            lines.append(f'  "{uuid}", -- {name}')
        lines.append('}')
        lines.append('local host = GetHostCharacter()')
        lines.append('if host and host ~= "" then table.insert(ALL_UUIDS, host) end')
        lines.append('')
        lines.append('for _, uuid in ipairs(ALL_UUIDS) do')
        lines.append(f'  pcall(function() RemoveStatus(uuid, "{GOD_MODE_STATUS}", 0) end)')
        
        for b in GOD_MODE_BOOSTS + INSTAKILL_BOOSTS + UNLIMITED_BOOSTS:
            lines.append(f'  pcall(function() RemoveBoosts(uuid, "{b}", 0, 0, 0) end)')
        for p in INSTAKILL_PASSIVES:
            lines.append(f'  pcall(function() RemovePassive(uuid, "{p}") end)')
        
        lines.append('end')
        lines.append('print("[OVERLORD] All boosts removed!")')
        
        script = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)
        
        log.info(f"Generated disable script: {output_path}")
        return output_path


# ============================================================================
# MAIN OVERLORD CONTROLLER
# ============================================================================

class BG3Overlord:
    """Master controller combining all three layers."""
    
    def __init__(self):
        self.aob = AOBGodMode()
        self.ce_pipe = CELuaPipe()
        self.osiris: Optional[OsirisBoostEngine] = None
        self.generator = ScriptGenerator()
    
    def initialize(self, need_ce: bool = False) -> bool:
        """Initialize all available layers."""
        # Layer 1: pymem
        if not self.aob.attach():
            return False
        
        if not self.aob.scan():
            return False
        
        # Layer 2: CE pipe (optional)
        if need_ce:
            if self.ce_pipe.connect():
                self.osiris = OsirisBoostEngine(self.ce_pipe)
                if not self.osiris.check_prereqs():
                    log.warning("CE connected but Register Commands not active")
                    self.osiris = None
            else:
                log.warning("Cannot connect to CE Lua pipe")
                log.warning("Make sure CE is running and Lua Pipe Server is enabled")
                log.warning("(Settings > Extra > Enable Lua Pipe Server)")
                log.warning("")
                log.warning("Falling back to script generation mode.")
                return True  # Still usable for script generation
        
        return True
    
    def run_godmode_only(self) -> bool:
        """Layer 1 only: AOB god mode."""
        return self.aob.enable()
    
    def run_overlord(self, god=True, instakill=True, unlimited=True) -> bool:
        """
        Full Overlord mode:
          Layer 1: AOB god mode
          Layer 2: Osiris boosts via CE pipe
        """
        # AOB patch first
        if god:
            self.aob.enable()
        
        # Osiris boosts
        if self.osiris:
            self.osiris.detect_party()
            return self.osiris.apply_all_staggered(
                god=god, instakill=instakill, unlimited=unlimited
            )
        else:
            log.warning("CE not connected. Generating script instead...")
            return self.run_generate(god=god, instakill=instakill, unlimited=unlimited)
    
    def run_generate(self, god=True, instakill=True, unlimited=True,
                      output: str = "bg3_overlord_generated.lua") -> bool:
        """Generate .lua scripts for manual execution in CE."""
        self.generator.generate_overlord_script(
            output_path=output, god=god, instakill=instakill, unlimited=unlimited
        )
        self.generator.generate_disable_script(
            output_path=output.replace(".lua", "_disable.lua")
        )
        
        print(f"\n[+] Scripts generated!")
        print(f"    Enable:  {output}")
        print(f"    Disable: {output.replace('.lua', '_disable.lua')}")
        print(f"\n    To use: Open CE Lua Engine (Ctrl+Alt+L), paste the script, click Execute")
        return True
    
    def run_disable(self) -> bool:
        """Disable everything."""
        self.aob.disable()
        
        if self.osiris:
            self.osiris.remove_all()
        
        return True
    
    def cleanup(self):
        """Clean shutdown."""
        self.ce_pipe.close()
        self.aob.cleanup()


# ============================================================================
# INTERACTIVE CLI
# ============================================================================

def interactive_mode(overlord: BG3Overlord):
    """Full interactive command-line interface."""
    print("\n" + "=" * 60)
    print("  BG3 OVERLORD — INTERACTIVE MODE")
    print("=" * 60)
    print("  Commands:")
    print("    godmode         AOB god mode (pymem, standalone)")
    print("    overlord        Full Overlord (needs CE)")
    print("    god-only        Osiris god mode only")
    print("    instakill       Osiris instakill only")
    print("    unlimited       Osiris unlimited only")
    print("    generate [file] Generate .lua script")
    print("    detect          Detect party members")
    print("    disable         Remove all patches/boosts")
    print("    status          Show status")
    print("    quit            Exit")
    print("=" * 60)
    
    while True:
        try:
            cmd = input("\n[OVERLORD] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        
        if not cmd:
            continue
        
        parts = cmd.split()
        action = parts[0]
        
        if action in ("quit", "exit", "q"):
            break
        elif action == "godmode":
            overlord.run_godmode_only()
        elif action == "overlord":
            if not overlord.osiris:
                if overlord.ce_pipe.connect():
                    overlord.osiris = OsirisBoostEngine(overlord.ce_pipe)
                    overlord.osiris.check_prereqs()
            overlord.run_overlord()
        elif action == "god-only":
            if overlord.osiris:
                overlord.osiris.detect_party()
                overlord.osiris.apply_all_staggered(god=True, instakill=False, unlimited=False)
            else:
                print("CE not connected. Use 'godmode' for AOB-only mode.")
        elif action == "instakill":
            if overlord.osiris:
                overlord.osiris.detect_party()
                overlord.osiris.apply_all_staggered(god=False, instakill=True, unlimited=False)
            else:
                print("CE not connected.")
        elif action == "unlimited":
            if overlord.osiris:
                overlord.osiris.detect_party()
                overlord.osiris.apply_all_staggered(god=False, instakill=False, unlimited=True)
            else:
                print("CE not connected.")
        elif action == "generate":
            output = parts[1] if len(parts) > 1 else "bg3_overlord_generated.lua"
            overlord.run_generate(output=output)
        elif action == "detect":
            if overlord.osiris:
                overlord.osiris.detect_party()
            else:
                print("CE not connected. Cannot detect party without Osiris API.")
        elif action == "disable":
            overlord.run_disable()
        elif action == "status":
            print(f"\n  AOB God Mode:  {'ACTIVE' if overlord.aob.patched else 'OFF'}")
            print(f"  CE Connected:  {'YES' if overlord.ce_pipe.connected else 'NO'}")
            print(f"  Osiris Engine: {'READY' if overlord.osiris else 'N/A'}")
            if overlord.osiris and overlord.osiris.party:
                print(f"  Party Members: {len(overlord.osiris.party)}")
                for m in overlord.osiris.party:
                    print(f"    - {m['name']} ({m['uuid'][:12]}...)")
        else:
            print(f"Unknown command: {cmd}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="BG3 Overlord Mode — God Mode + Insta-Kill + Unlimited",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  --godmode         AOB god mode only (pymem, no CE needed)
  --overlord        Full Overlord: god + instakill + unlimited (needs CE)
  --generate [path] Generate .lua script for CE (no live CE needed)
  --disable         Remove AOB patches
  --interactive     Interactive CLI

Examples:
  python bg3_overlord.py --godmode              # Standalone god mode
  python bg3_overlord.py --overlord             # Full power (needs CE)
  python bg3_overlord.py --generate             # Generate script for CE
  python bg3_overlord.py --generate custom.lua  # Custom output path
  python bg3_overlord.py -i                     # Interactive mode
        """
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--godmode", action="store_true",
                       help="AOB god mode only (no CE required)")
    group.add_argument("--overlord", action="store_true",
                       help="Full Overlord mode (requires CE)")
    group.add_argument("--generate", nargs="?", const="bg3_overlord_generated.lua",
                       metavar="PATH",
                       help="Generate .lua script for CE")
    group.add_argument("--disable", action="store_true",
                       help="Remove all patches")
    group.add_argument("--interactive", "-i", action="store_true",
                       help="Interactive CLI mode")
    
    parser.add_argument("--no-god", action="store_true",
                        help="Skip god mode boosts")
    parser.add_argument("--no-instakill", action="store_true",
                        help="Skip instakill boosts")
    parser.add_argument("--no-unlimited", action="store_true",
                        help="Skip unlimited resource boosts")
    parser.add_argument("--keep-alive", "-k", action="store_true",
                        help="Keep running after applying")
    parser.add_argument("--stagger-delay", type=float, default=2.0,
                        help="Delay between characters (default: 2.0s)")
    
    args = parser.parse_args()
    
    global STAGGER_DELAY
    STAGGER_DELAY = args.stagger_delay
    
    # Banner
    print(r"""
     ___  _   _ _____ ____  _     ___  ____  ____  
    / _ \| | | | ____|  _ \| |   / _ \|  _ \|  _ \ 
   | | | | | | |  _| | |_) | |  | | | | |_) | | | |
   | |_| | |_| | |___|  _ <| |__| |_| |  _ <| |_| |
    \___/ \___/|_____|_| \_|_____\___/|_| \_\____/ 
                                                     
    BG3 Python Overlord — DarkForge-X
    Layer 1: pymem AOB (standalone)
    Layer 2: CE Lua Pipe (Osiris boosts)
    Layer 3: Script Generator (offline)
    """)
    
    god = not args.no_god
    instakill = not args.no_instakill
    unlimited = not args.no_unlimited
    
    overlord = BG3Overlord()
    
    try:
        # Script generation doesn't need process attachment
        if args.generate:
            ScriptGenerator.generate_overlord_script(
                output_path=args.generate,
                god=god, instakill=instakill, unlimited=unlimited
            )
            ScriptGenerator.generate_disable_script(
                output_path=args.generate.replace(".lua", "_disable.lua")
            )
            print(f"\n[+] Scripts generated!")
            print(f"    Enable:  {args.generate}")
            print(f"    Disable: {args.generate.replace('.lua', '_disable.lua')}")
            print(f"\n    Usage: Open CE > Ctrl+Alt+L > Paste > Execute")
            return
        
        # All other modes need process attachment
        need_ce = args.overlord or args.interactive
        if not overlord.initialize(need_ce=need_ce):
            sys.exit(1)
        
        if args.interactive:
            interactive_mode(overlord)
        elif args.disable:
            overlord.run_disable()
        elif args.overlord:
            if overlord.run_overlord(god=god, instakill=instakill, unlimited=unlimited):
                print("\n" + "=" * 60)
                print("  OVERLORD MODE FULLY ACTIVE")
                if god: print("  ✓ INVINCIBLE (0 damage taken)")
                if instakill: print("  ✓ ONE-SHOT EVERYTHING (always crit, ~200-400 dmg)")
                if unlimited: print("  ✓ UNLIMITED actions, spells, movement")
                print("=" * 60)
        elif args.godmode:
            overlord.run_godmode_only()
            print("\n[+] AOB GOD MODE ACTIVE (all entities invincible)")
        else:
            # Default: just god mode
            overlord.run_godmode_only()
            print("\n[+] AOB GOD MODE ACTIVE")
            print("[*] For full Overlord, use --overlord (requires CE)")
            print("[*] For script generation, use --generate")
        
        if args.keep_alive:
            print("\nPress Ctrl+C to disable patches and exit...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    
    except Exception as e:
        log.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        overlord.cleanup()
        print("\n[*] Overlord shut down.")


if __name__ == "__main__":
    main()
