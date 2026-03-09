--[[
================================================================================
  BG3 PARTY GOD MODE SCRIPT — DarkForge-X
  
  Target:     Baldur's Gate 3 (bg3_dx11.exe / bg3.exe)
  Table:      Requires "Register Commands" (entry [103]) to be ACTIVE
  
  Features:
    - Auto-detects ALL active party members (up to 10 companions)
    - Applies INVULNERABLE status (permanent, -1 duration)
    - Applies DamageReduction(All, Flat, 100) boost
    - Full heal via RestoreParty
    - Toggle ON/OFF 
    - Safe cleanup on disable
    
  Usage:
    1. Load your save in BG3
    2. Activate "Register Commands" in cheat table
    3. Execute this script in CE Lua Engine (Ctrl+Alt+L)
    4. Call GodModeParty:Enable() to activate
    5. Call GodModeParty:Disable() to deactivate
    6. Call GodModeParty:Status() to check current state
    
  Or just run the script — it auto-enables on execution.
================================================================================
--]]

-- ============================================================================
-- KNOWN BG3 COMPANION UUID DATABASE
-- ============================================================================
local COMPANION_DB = {
  {name = "Astarion",     uuid = "c7c13742-bacd-460a-8f65-f864fe41f255"},
  {name = "Gale",         uuid = "ad9af97d-75da-406a-ae13-7071c563f604"},
  {name = "Karlach",      uuid = "2c76687d-93a2-477b-8b18-8a14b549304c"},
  {name = "Laezel",       uuid = "58a69333-40bf-8571-d77a-93e42c29260e"},
  {name = "Wyll",         uuid = "c774d764-4a17-48dc-b470-32ace9ce447d"},
  {name = "ShadowHeart",  uuid = "3ed74f06-3c60-42dc-83f6-f034cb47c679"},
  {name = "Minsc",        uuid = "0de603c5-42e2-4811-9210-f178b28716a8"},
  {name = "Jaheira",      uuid = "91b6b200-7d00-4d62-8dc9-99e8339dfa1a"},
  {name = "Minthara",     uuid = "25721313-0c15-4571-acc5-b83e5e09b30c"},
  {name = "Halsin",       uuid = "7628bc0e-52b8-42a7-856a-13a6fd413323"},
  {name = "DarkUrge",     uuid = "3130cff0-5765-4b71-b857-a2b00228087b"},
}

-- ============================================================================
-- PROTECTION LAYERS CONFIGURATION
-- ============================================================================
local PROTECTIONS = {
  -- Layer 1: Invulnerable status effect (blocks all damage, visible icon)
  {type = "status", id = "INVULNERABLE", duration = -1},
  -- Layer 2: Flat damage reduction of 100 for all types
  {type = "boost",  id = "DamageReduction(All, Flat, 100)"},
  -- Layer 3: Additional resistance boost (optional, uncomment to add)
  -- {type = "boost",  id = "Resistance(Slashing, Immune)"},
  -- {type = "boost",  id = "Resistance(Piercing, Immune)"},
  -- {type = "boost",  id = "Resistance(Bludgeoning, Immune)"},
  -- {type = "boost",  id = "Resistance(Fire, Immune)"},
  -- {type = "boost",  id = "Resistance(Cold, Immune)"},
  -- {type = "boost",  id = "Resistance(Lightning, Immune)"},
  -- {type = "boost",  id = "Resistance(Thunder, Immune)"},
  -- {type = "boost",  id = "Resistance(Acid, Immune)"},
  -- {type = "boost",  id = "Resistance(Poison, Immune)"},
  -- {type = "boost",  id = "Resistance(Necrotic, Immune)"},
  -- {type = "boost",  id = "Resistance(Radiant, Immune)"},
  -- {type = "boost",  id = "Resistance(Psychic, Immune)"},
  -- {type = "boost",  id = "Resistance(Force, Immune)"},
}

-- ============================================================================
-- GOD MODE PARTY CONTROLLER
-- ============================================================================
GodModeParty = GodModeParty or {}
GodModeParty.active = false
GodModeParty.partyMembers = {}
GodModeParty.timerID = nil

-- ============================================================================
-- UTILITY: Check if Register Commands infrastructure is available
-- ============================================================================
function GodModeParty:CheckPrerequisites()
  local cmdCall = getAddress("cmdCall")
  if not cmdCall or cmdCall == 0 then
    print("[GOD MODE] ERROR: 'Register Commands' is not active!")
    print("[GOD MODE] Please activate entry [103] in the cheat table first.")
    return false
  end
  
  if type(GetHostCharacter) ~= "function" then
    print("[GOD MODE] ERROR: Command functions not loaded!")
    print("[GOD MODE] Please activate 'Register Commands' first.")
    return false
  end
  
  local host = GetHostCharacter()
  if not host or host == "" then
    print("[GOD MODE] ERROR: No host character found!")
    print("[GOD MODE] Please load a saved game first.")
    return false
  end
  
  return true
end

-- ============================================================================
-- DETECT: Scan for all active party members
-- ============================================================================
function GodModeParty:DetectPartyMembers()
  self.partyMembers = {}
  
  local host = GetHostCharacter()
  print(string.format("[GOD MODE] Host character: %s", host))
  
  -- Check each known companion
  for _, comp in ipairs(COMPANION_DB) do
    SetArgToString(0, comp.uuid)
    ClearArg(1)
    local result = ExecuteCall("GetHitpoints")
    local hp = GetArgAsInteger(1)
    
    if result == 1 and hp and hp > 0 and hp < 10000 then
      SetArgToString(0, comp.uuid)
      ClearArg(1)
      ExecuteCall("GetMaxHitpoints")
      local maxhp = GetArgAsInteger(1)
      
      table.insert(self.partyMembers, {
        name = comp.name,
        uuid = comp.uuid,
        hp = hp,
        maxhp = maxhp or hp,
        isHost = (comp.uuid == host)
      })
      
      print(string.format("[GOD MODE]   Found: %s (HP: %d/%d)%s", 
        comp.name, hp, maxhp or hp, 
        comp.uuid == host and " [HOST]" or ""))
    end
  end
  
  -- Also check if host UUID doesn't match any known companion (custom Tav)
  local hostFound = false
  for _, m in ipairs(self.partyMembers) do
    if m.isHost then hostFound = true; break end
  end
  
  if not hostFound and host and host ~= "" then
    SetArgToString(0, host)
    ClearArg(1)
    ExecuteCall("GetHitpoints")
    local hp = GetArgAsInteger(1)
    
    SetArgToString(0, host)
    ClearArg(1)
    ExecuteCall("GetMaxHitpoints")
    local maxhp = GetArgAsInteger(1)
    
    if hp and hp > 0 then
      table.insert(self.partyMembers, 1, {
        name = "Custom Tav",
        uuid = host,
        hp = hp,
        maxhp = maxhp or hp,
        isHost = true
      })
      print(string.format("[GOD MODE]   Found: Custom Tav (HP: %d/%d) [HOST]", hp, maxhp or hp))
    end
  end
  
  print(string.format("[GOD MODE] Total party members detected: %d", #self.partyMembers))
  return #self.partyMembers
end

-- ============================================================================
-- HEAL: Restore entire party to full HP
-- ============================================================================
function GodModeParty:HealParty()
  local host = GetHostCharacter()
  SetArgToString(0, host)
  local result = ExecuteCall("RestoreParty")
  if result == 1 then
    print("[GOD MODE] Party fully restored!")
  else
    print("[GOD MODE] RestoreParty command failed, healing individually...")
    -- Fallback: heal each member via status
    for _, member in ipairs(self.partyMembers) do
      ApplyStatus(member.uuid, "YOURHEALED", 1, 1, 0)
    end
  end
end

-- ============================================================================
-- APPLY: Apply all protection layers to a single character
-- ============================================================================
function GodModeParty:ApplyProtection(uuid, name)
  local success = true
  for _, prot in ipairs(PROTECTIONS) do
    local result
    if prot.type == "status" then
      result = ApplyStatus(uuid, prot.id, prot.duration, 1, 0)
    elseif prot.type == "boost" then
      result = AddBoosts(uuid, prot.id, 0, 0)
    end
    
    if result ~= 1 then
      print(string.format("[GOD MODE]   WARNING: Failed to apply %s to %s", prot.id, name))
      success = false
    end
  end
  return success
end

-- ============================================================================
-- REMOVE: Remove all protection layers from a single character
-- ============================================================================
function GodModeParty:RemoveProtection(uuid, name)
  for _, prot in ipairs(PROTECTIONS) do
    if prot.type == "status" then
      RemoveStatus(uuid, prot.id, 0)
    elseif prot.type == "boost" then
      RemoveBoosts(uuid, prot.id, 0, 0, 0)
    end
  end
end

-- ============================================================================
-- ENABLE: Main activation function
-- ============================================================================
function GodModeParty:Enable()
  print("")
  print("========================================")
  print("  BG3 PARTY GOD MODE — ACTIVATING")
  print("========================================")
  
  -- Check prerequisites
  if not self:CheckPrerequisites() then return false end
  
  -- Detect party members
  local count = self:DetectPartyMembers()
  if count == 0 then
    print("[GOD MODE] ERROR: No party members found!")
    return false
  end
  
  -- Heal everyone first
  print("")
  print("[GOD MODE] Phase 1: Healing party...")
  self:HealParty()
  
  -- Apply protections
  print("[GOD MODE] Phase 2: Applying invincibility...")
  local allOk = true
  for _, member in ipairs(self.partyMembers) do
    local ok = self:ApplyProtection(member.uuid, member.name)
    if ok then
      print(string.format("[GOD MODE]   %s: PROTECTED", member.name))
    else
      allOk = false
    end
  end
  
  -- Start auto-refresh timer (re-applies every 30 seconds in case status expires)
  self:StartAutoRefresh()
  
  self.active = true
  print("")
  print("========================================")
  print("  GOD MODE ACTIVE — PARTY IS INVINCIBLE")
  print("========================================")
  print("")
  
  return true
end

-- ============================================================================
-- DISABLE: Clean deactivation
-- ============================================================================
function GodModeParty:Disable()
  print("")
  print("========================================")
  print("  BG3 PARTY GOD MODE — DEACTIVATING")
  print("========================================")
  
  -- Stop auto-refresh
  self:StopAutoRefresh()
  
  -- Remove protections from all known party members
  for _, member in ipairs(self.partyMembers) do
    self:RemoveProtection(member.uuid, member.name)
    print(string.format("[GOD MODE]   %s: Protection removed", member.name))
  end
  
  -- Also try to remove from all known companions (in case party changed)
  for _, comp in ipairs(COMPANION_DB) do
    local found = false
    for _, m in ipairs(self.partyMembers) do
      if m.uuid == comp.uuid then found = true; break end
    end
    if not found then
      self:RemoveProtection(comp.uuid, comp.name)
    end
  end
  
  self.active = false
  self.partyMembers = {}
  
  print("")
  print("========================================")
  print("  GOD MODE DISABLED")
  print("========================================")
  print("")
end

-- ============================================================================
-- TOGGLE: Quick toggle
-- ============================================================================
function GodModeParty:Toggle()
  if self.active then
    self:Disable()
  else
    self:Enable()
  end
end

-- ============================================================================
-- STATUS: Print current state
-- ============================================================================
function GodModeParty:Status()
  print("")
  print("=== GOD MODE STATUS ===")
  print(string.format("Active: %s", self.active and "YES" or "NO"))
  print(string.format("Auto-refresh: %s", self.timerID and "RUNNING" or "STOPPED"))
  
  if #self.partyMembers > 0 then
    print(string.format("Party members: %d", #self.partyMembers))
    for _, member in ipairs(self.partyMembers) do
      -- Re-check current HP
      SetArgToString(0, member.uuid)
      ClearArg(1)
      ExecuteCall("GetHitpoints")
      local hp = GetArgAsInteger(1)
      
      SetArgToString(0, member.uuid)
      ClearArg(1)
      ExecuteCall("GetMaxHitpoints")
      local maxhp = GetArgAsInteger(1)
      
      print(string.format("  %s: HP=%d/%d %s%s", 
        member.name, 
        hp or 0, 
        maxhp or 0,
        (hp == maxhp) and "[FULL]" or "[DMG]",
        member.isHost and " [HOST]" or ""))
    end
  else
    print("Party members: (not scanned)")
  end
  print("")
end

-- ============================================================================
-- REFRESH: Re-apply protections (called by timer or manually)
-- ============================================================================
function GodModeParty:Refresh()
  if not self.active then return end
  
  for _, member in ipairs(self.partyMembers) do
    self:ApplyProtection(member.uuid, member.name)
  end
end

-- ============================================================================
-- AUTO-REFRESH TIMER: Re-applies every 30 seconds
-- ============================================================================
function GodModeParty:StartAutoRefresh()
  self:StopAutoRefresh()
  
  local timer = createTimer(getMainForm())
  timer.Interval = 30000  -- 30 seconds
  timer.OnTimer = function(t)
    if self.active then
      self:Refresh()
    else
      self:StopAutoRefresh()
    end
  end
  timer.Enabled = true
  self.timerID = timer
  print("[GOD MODE] Auto-refresh timer started (30s interval)")
end

function GodModeParty:StopAutoRefresh()
  if self.timerID then
    self.timerID.Enabled = false
    self.timerID.Destroy()
    self.timerID = nil
    print("[GOD MODE] Auto-refresh timer stopped")
  end
end

-- ============================================================================
-- HOTKEY: Register Ctrl+G as toggle (optional)
-- ============================================================================
function GodModeParty:RegisterHotkey()
  local hk = createHotkey(function()
    GodModeParty:Toggle()
  end, VK_G, {ssCtrl})
  print("[GOD MODE] Hotkey registered: Ctrl+G to toggle")
end

-- ============================================================================
-- AUTO-EXECUTE: Enable on script load
-- ============================================================================
print("")
print("  ____  ____  _____   ____  ___  ____   __  __  ___  ____  _____")
print(" | __ )/ ___|___ /  / ___|/ _ \\|  _ \\ |  \\/  |/ _ \\|  _ \\| ____|")
print(" |  _ \\\\___ \\ |_ \\ | |  _| | | | | | || |\\/| | | | | | | |  _|")
print(" | |_) |___) |__) || |_| | |_| | |_| || |  | | |_| | |_| | |___")
print(" |____/|____/____/  \\____|\\___/|____/ |_|  |_|\\___/|____/|_____|")
print("")
print("  Commands:")
print("    GodModeParty:Enable()   — Activate invincibility")
print("    GodModeParty:Disable()  — Remove invincibility")
print("    GodModeParty:Toggle()   — Toggle on/off")
print("    GodModeParty:Status()   — Check current state")
print("    GodModeParty:Refresh()  — Re-apply protections")
print("")

-- Auto-enable
GodModeParty:Enable()
