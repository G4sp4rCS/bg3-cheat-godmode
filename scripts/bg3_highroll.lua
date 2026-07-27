--[[
================================================================================
  BG3 ALWAYS HIGH ROLL SCRIPT — DarkForge-X
  ("High rollear siempre" — cada tirada de d20 sale alta / 20 natural)

  Target:     Baldur's Gate 3 (bg3_dx11.exe / bg3.exe)
  Table:      Requires "Register Commands" (entry [103]) to be ACTIVE

  Features:
    - Auto-detects ALL active party members (up to 10 companions + custom Tav)
    - Forces every d20 roll to land high on:
        * Attack rolls        (natural 20 -> auto-hit + auto-crit)
        * Skill checks        (Persuasion, Deception, Sleight of Hand, ...)
        * Saving throws        (Dexterity, Wisdom, ... saves)
        * Raw ability checks   (Strength, Charisma, ... checks)
        * Death saving throws
    - Three selectable modes (see CONFIG below):
        * "max"  -> MinimumRollResult(): the die ALWAYS shows the target value
        * "safe" -> RollBonus() + Advantage(): huge flat bonus + advantage,
                    no crash risk (recommended if "max" ever misbehaves)
        * "both" -> apply both layers at once
    - Toggle ON/OFF, Status, Refresh, and Ctrl+H hotkey
    - Safe cleanup on disable

  Usage:
    1. Load your save in BG3
    2. Activate "Register Commands" in cheat table
    3. Execute this script in CE Lua Engine (Ctrl+Alt+L)
    4. Call HighRoll:Enable() to activate  (auto-enables on execution)
    5. Call HighRoll:Disable() to deactivate
    6. Call HighRoll:Status() to check current state

  Commands:
    HighRoll:Enable()        -- Apply high-roll boosts to the whole party
    HighRoll:Disable()       -- Remove all high-roll boosts
    HighRoll:Toggle()        -- Toggle on/off
    HighRoll:Status()        -- Check current state
    HighRoll:Refresh()       -- Re-apply boosts (cleanly, no stacking)
    HighRoll:SetMode(m, v)   -- Switch mode/value live, e.g. SetMode("safe", 30)
================================================================================
--]]

-- ============================================================================
-- CONFIG
-- ============================================================================
local CONFIG = {
  -- "max"  = MinimumRollResult(...) -> every d20 rolls at least `value`.
  --          value = 20 means an always-natural-20 (true "high roll siempre").
  --          NOTE: on some game patches MinimumRollResult can be unstable with
  --          certain tooltips/items. If you ever see crashes, switch to "safe".
  -- "safe" = RollBonus(...) + Advantage(...) -> big flat bonus + advantage.
  --          No crash risk; rolls are effectively always high (passes any DC).
  -- "both" = apply both layers together.
  mode = "max",

  -- Minimum die result forced by "max" mode, AND the flat bonus size in "safe".
  -- 20 = natural 20 (the highest single die face). Raise to 30 / 99 to steamroll
  -- even the hardest DCs when a character has negative modifiers.
  value = 20,
}

-- ============================================================================
-- KNOWN BG3 COMPANION UUID DATABASE
-- ============================================================================
local COMPANION_DB = {
  {name = "Astarion",     uuid = "c7c13742-bacd-460a-8f65-f864fe41f255"},
  {name = "Gale",         uuid = "ad9af97d-75da-406a-ae13-7071c563f604"},
  {name = "Karlach",      uuid = "2c76687d-93a2-477b-8b18-8a14b549304c"},
  {name = "Lae'zel",      uuid = "58a69333-40bf-8571-d77a-93e42c29260e"},
  {name = "Wyll",         uuid = "c774d764-4a17-48dc-b470-32ace9ce447d"},
  {name = "Shadowheart",  uuid = "3ed74f06-3c60-42dc-83f6-f034cb47c679"},
  {name = "Minsc",        uuid = "0de603c5-42e2-4811-9210-f178b28716a8"},
  {name = "Jaheira",      uuid = "91b6b200-7d00-4d62-8dc9-99e8339dfa1a"},
  {name = "Minthara",     uuid = "25721313-0c15-4571-acc5-b83e5e09b30c"},
  {name = "Halsin",       uuid = "7628bc0e-52b8-42a7-856a-13a6fd413323"},
  {name = "Dark Urge",    uuid = "3130cff0-5765-4b71-b857-a2b00228087b"},
}

-- ============================================================================
-- ROLL DEFINITIONS
--   RollType values verified against Norbyte's BG3 Script Extender source
--   (stats::RollType). AdvantageContext values likewise verified.
-- ============================================================================

-- d20 roll types affected by MinimumRollResult / RollBonus
local ROLL_TYPES = {
  "Attack",           -- attack rolls (natural 20 => auto-hit + critical hit)
  "SkillCheck",       -- skill checks (dialogue, exploration)
  "SavingThrow",      -- saving throws
  "RawAbility",       -- raw ability checks
  "DeathSavingThrow", -- death saving throws
}

-- Advantage contexts used only by "safe" / "both" modes
local ADVANTAGE_CONTEXTS = {
  "AttackRoll",
  "AllSkills",
  "AllSavingThrows",
  "AllAbilities",
  "DeathSavingThrow",
}

-- ----------------------------------------------------------------------------
-- Build the active boost list from the current CONFIG.
-- ----------------------------------------------------------------------------
local function BuildBoostList()
  local boosts = {}
  local mode = tostring(CONFIG.mode or "max"):lower()
  local value = math.floor(tonumber(CONFIG.value) or 20)
  if value < 1 then value = 20 end

  if mode == "max" or mode == "both" then
    for _, rt in ipairs(ROLL_TYPES) do
      table.insert(boosts, string.format("MinimumRollResult(%s, %d)", rt, value))
    end
  end

  if mode == "safe" or mode == "both" then
    for _, rt in ipairs(ROLL_TYPES) do
      table.insert(boosts, string.format("RollBonus(%s, %d)", rt, value))
    end
    for _, ac in ipairs(ADVANTAGE_CONTEXTS) do
      table.insert(boosts, string.format("Advantage(%s)", ac))
    end
  end

  return boosts
end

-- ============================================================================
-- SAFE WRAPPERS (pcall-guarded so one bad boost never aborts the batch)
-- ============================================================================
local function SafeAddBoost(uuid, boost)
  pcall(function() AddBoosts(uuid, boost, 0, 0) end)
end
local function SafeRemoveBoost(uuid, boost)
  pcall(function() RemoveBoosts(uuid, boost, 0, 0, 0) end)
end

-- Merge boost strings from `src` into `dst`, keeping order and skipping dupes.
local function MergeUnique(dst, src)
  local seen = {}
  for _, b in ipairs(dst) do seen[b] = true end
  for _, b in ipairs(src) do
    if not seen[b] then
      seen[b] = true
      table.insert(dst, b)
    end
  end
end

-- ============================================================================
-- HIGH ROLL CONTROLLER
-- ============================================================================
HighRoll = HighRoll or {}
HighRoll.active = false
HighRoll.partyMembers = {}
HighRoll.timerID = nil
HighRoll.boosts = BuildBoostList()
-- Every distinct boost string this session has applied, so Disable/Refresh can
-- remove EXACTLY what was added (no brute-force loop that floods the engine).
HighRoll.appliedBoosts = HighRoll.appliedBoosts or {}
MergeUnique(HighRoll.appliedBoosts, HighRoll.boosts)

-- ============================================================================
-- UTILITY: Check if Register Commands infrastructure is available
-- ============================================================================
function HighRoll:CheckPrerequisites()
  local cmdCall = getAddress("cmdCall")
  if not cmdCall or cmdCall == 0 then
    print("[HIGH ROLL] ERROR: 'Register Commands' is not active!")
    print("[HIGH ROLL] Please activate entry [103] in the cheat table first.")
    return false
  end

  if type(GetHostCharacter) ~= "function" then
    print("[HIGH ROLL] ERROR: Command functions not loaded!")
    print("[HIGH ROLL] Please activate 'Register Commands' first.")
    return false
  end

  local host = GetHostCharacter()
  if not host or host == "" then
    print("[HIGH ROLL] ERROR: No host character found!")
    print("[HIGH ROLL] Please load a saved game first.")
    return false
  end

  return true
end

-- ============================================================================
-- DETECT: Scan for all active party members
-- ============================================================================
function HighRoll:DetectPartyMembers()
  self.partyMembers = {}

  local host = GetHostCharacter()
  print(string.format("[HIGH ROLL] Host character: %s", host))

  -- Check each known companion
  for _, comp in ipairs(COMPANION_DB) do
    local ok, hp = pcall(function()
      SetArgToString(0, comp.uuid)
      ClearArg(1)
      local r = ExecuteCall("GetHitpoints")
      if r == 1 then return GetArgAsInteger(1) end
      return nil
    end)

    if ok and hp and hp > 0 and hp < 50000 then
      table.insert(self.partyMembers, {
        name = comp.name,
        uuid = comp.uuid,
        isHost = (comp.uuid == host),
      })
      print(string.format("[HIGH ROLL]   Found: %s%s",
        comp.name, comp.uuid == host and " [HOST]" or ""))
    end
  end

  -- Also check if host UUID doesn't match any known companion (custom Tav)
  local hostFound = false
  for _, m in ipairs(self.partyMembers) do
    if m.isHost then hostFound = true; break end
  end

  if not hostFound and host and host ~= "" then
    table.insert(self.partyMembers, 1, {
      name = "Custom Tav",
      uuid = host,
      isHost = true,
    })
    print("[HIGH ROLL]   Found: Custom Tav [HOST]")
  end

  print(string.format("[HIGH ROLL] Total party members detected: %d", #self.partyMembers))
  return #self.partyMembers
end

-- ============================================================================
-- APPLY / REMOVE for a single character
-- ============================================================================
function HighRoll:ApplyToCharacter(uuid)
  for _, boost in ipairs(self.boosts) do
    SafeAddBoost(uuid, boost)
  end
end

function HighRoll:RemoveListFromCharacter(uuid, list)
  for _, boost in ipairs(list) do
    SafeRemoveBoost(uuid, boost)
  end
end

-- Remove every boost this session ever applied (bounded, no engine flooding).
function HighRoll:RemoveFromCharacter(uuid)
  self:RemoveListFromCharacter(uuid, self.appliedBoosts)
end

-- Record the current boost list so we can always clean it up later.
function HighRoll:TrackApplied()
  MergeUnique(self.appliedBoosts, self.boosts)
end

-- ============================================================================
-- ENABLE: Main activation function
-- ============================================================================
function HighRoll:Enable()
  print("")
  print("========================================")
  print("  BG3 ALWAYS HIGH ROLL — ACTIVATING")
  print("========================================")

  -- Check prerequisites
  if not self:CheckPrerequisites() then return false end

  -- Rebuild boost list in case CONFIG changed since load
  self.boosts = BuildBoostList()
  if #self.boosts == 0 then
    print("[HIGH ROLL] ERROR: Unknown mode '" .. tostring(CONFIG.mode) .. "'.")
    print("[HIGH ROLL] Valid modes: \"max\", \"safe\", \"both\".")
    return false
  end
  self:TrackApplied()

  -- Detect party members
  local count = self:DetectPartyMembers()
  if count == 0 then
    print("[HIGH ROLL] ERROR: No party members found!")
    return false
  end

  -- Apply boosts
  print("")
  print(string.format("[HIGH ROLL] Mode: %s  |  Value: %d  |  Boosts per character: %d",
    tostring(CONFIG.mode), math.floor(tonumber(CONFIG.value) or 20), #self.boosts))
  for _, member in ipairs(self.partyMembers) do
    -- Clean first so a re-Enable never stacks flat RollBonus values
    self:RemoveFromCharacter(member.uuid)
    self:ApplyToCharacter(member.uuid)
    print(string.format("[HIGH ROLL]   %s: HIGH ROLLING", member.name))
  end

  -- Start auto-refresh timer (re-applies periodically in case boosts drop)
  self:StartAutoRefresh()

  self.active = true
  print("")
  print("========================================")
  print("  HIGH ROLL ACTIVE — PARTY ALWAYS ROLLS HIGH")
  print("========================================")
  print("")

  return true
end

-- ============================================================================
-- DISABLE: Clean deactivation
-- ============================================================================
function HighRoll:Disable()
  print("")
  print("========================================")
  print("  BG3 ALWAYS HIGH ROLL — DEACTIVATING")
  print("========================================")

  -- Stop auto-refresh
  self:StopAutoRefresh()

  -- Remove boosts from all known party members
  for _, member in ipairs(self.partyMembers) do
    self:RemoveFromCharacter(member.uuid)
    print(string.format("[HIGH ROLL]   %s: boosts removed", member.name))
  end

  -- Safety sweep on every known companion (in case party changed)
  for _, comp in ipairs(COMPANION_DB) do
    self:RemoveFromCharacter(comp.uuid)
  end

  self.active = false
  self.partyMembers = {}

  print("")
  print("========================================")
  print("  HIGH ROLL DISABLED")
  print("========================================")
  print("")
end

-- ============================================================================
-- TOGGLE: Quick toggle
-- ============================================================================
function HighRoll:Toggle()
  if self.active then
    self:Disable()
  else
    self:Enable()
  end
end

-- ============================================================================
-- SET MODE: Switch mode/value at runtime and re-apply
-- ============================================================================
function HighRoll:SetMode(mode, value)
  if mode then CONFIG.mode = mode end
  if value then CONFIG.value = value end
  print(string.format("[HIGH ROLL] Mode set to '%s' (value %s)",
    tostring(CONFIG.mode), tostring(CONFIG.value)))
  if self.active then
    -- Re-apply cleanly with the new settings
    self.boosts = BuildBoostList()
    self:TrackApplied()
    for _, member in ipairs(self.partyMembers) do
      self:RemoveFromCharacter(member.uuid)
      self:ApplyToCharacter(member.uuid)
    end
    print("[HIGH ROLL] Re-applied with new settings.")
  end
end

-- ============================================================================
-- STATUS: Print current state
-- ============================================================================
function HighRoll:Status()
  print("")
  print("=== HIGH ROLL STATUS ===")
  print(string.format("Active: %s", self.active and "YES" or "NO"))
  print(string.format("Mode: %s  |  Value: %d", tostring(CONFIG.mode),
    math.floor(tonumber(CONFIG.value) or 20)))
  print(string.format("Auto-refresh: %s", self.timerID and "RUNNING" or "STOPPED"))

  if #self.partyMembers > 0 then
    print(string.format("Party members: %d", #self.partyMembers))
    for _, member in ipairs(self.partyMembers) do
      print(string.format("  %s%s", member.name, member.isHost and " [HOST]" or ""))
    end
  else
    print("Party members: (not scanned)")
  end

  print("Active boosts:")
  for _, boost in ipairs(self.boosts) do
    print("  - " .. boost)
  end
  print("")
end

-- ============================================================================
-- REFRESH: Re-apply boosts cleanly (called by timer or manually)
--   Removes first, then adds, so flat RollBonus values never stack.
-- ============================================================================
function HighRoll:Refresh()
  if not self.active then return end
  for _, member in ipairs(self.partyMembers) do
    -- Remove just the current set (already applied) then re-add, so flat
    -- RollBonus values never stack up over repeated refreshes.
    self:RemoveListFromCharacter(member.uuid, self.boosts)
    self:ApplyToCharacter(member.uuid)
  end
end

-- ============================================================================
-- AUTO-REFRESH TIMER: Re-applies every 60 seconds
-- ============================================================================
function HighRoll:StartAutoRefresh()
  self:StopAutoRefresh()

  local timer = createTimer(getMainForm())
  timer.Interval = 60000  -- 60 seconds
  timer.OnTimer = function(t)
    if self.active then
      pcall(function() self:Refresh() end)
    else
      self:StopAutoRefresh()
    end
  end
  timer.Enabled = true
  self.timerID = timer
  print("[HIGH ROLL] Auto-refresh timer started (60s interval)")
end

function HighRoll:StopAutoRefresh()
  if self.timerID then
    pcall(function()
      self.timerID.Enabled = false
      self.timerID.Destroy()
    end)
    self.timerID = nil
    print("[HIGH ROLL] Auto-refresh timer stopped")
  end
end

-- ============================================================================
-- HOTKEY: Register Ctrl+H as toggle (optional)
-- ============================================================================
function HighRoll:RegisterHotkey()
  local ok = pcall(function()
    createHotkey(function() HighRoll:Toggle() end, VK_H, {ssCtrl})
  end)
  if ok then
    print("[HIGH ROLL] Hotkey registered: Ctrl+H to toggle")
  end
end

-- ============================================================================
-- AUTO-EXECUTE: Enable on script load
-- ============================================================================
print("")
print("  _  _ ___ ___ _  _   ___  ___  _    _    ")
print(" | || |_ _/ __| || | | _ \\/ _ \\| |  | |   ")
print(" | __ || | (_ | __ | |   / (_) | |__| |__ ")
print(" |_||_|___\\___|_||_| |_|_\\\\___/|____|____|")
print("")
print("  Always High Roll — every d20 lands high")
print("")
print("  Commands:")
print("    HighRoll:Enable()        -- Activate high rolls")
print("    HighRoll:Disable()       -- Remove high rolls")
print("    HighRoll:Toggle()        -- Toggle on/off")
print("    HighRoll:Status()        -- Check current state")
print("    HighRoll:Refresh()       -- Re-apply boosts")
print("    HighRoll:SetMode(m, v)   -- e.g. HighRoll:SetMode(\"safe\", 30)")
print("")

-- Auto-enable
HighRoll:Enable()
