--[[
================================================================================
  BG3 GOD MODE + INSTA-KILL — DarkForge-X (v4 — staggered apply, no crash)
  
  Target:     Baldur's Gate 3 (bg3_dx11.exe / bg3.exe)
  Table:      Requires "Register Commands" (entry [103]) to be ACTIVE
  
  v4 FIX: Applies boosts using a TIMER with 2-second delays between
  each character to prevent overwhelming the game engine command queue.
  
  Usage:
    1. Load your save in BG3
    2. Activate "Register Commands" in cheat table
    3. Execute this script in CE Lua Engine (Ctrl+Alt+L)
    4. Wait ~15 seconds for all boosts to apply (staged per character)
    
  Commands:
    Overlord:Enable()      -- Enable everything (staged, ~15s)
    Overlord:Disable()     -- Disable everything
    Overlord:GodMode()     -- Toggle god mode only
    Overlord:InstaKill()   -- Toggle insta-kill only
    Overlord:Unlimited()   -- Toggle unlimited resources only
    Overlord:Status()      -- Check current state
================================================================================
--]]

-- ============================================================================
-- COMPANION UUID DATABASE
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
-- BOOST DEFINITIONS (ALL LIVE TESTED INDIVIDUALLY)
-- ============================================================================

local GOD_MODE_BOOSTS = {
  "DamageReduction(All, Flat, 100)",
}

local INSTAKILL_BOOSTS = {
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
}

local INSTAKILL_PASSIVES = {
  "ImprovedCritical",
  "SavageAttacker",
  "BrutalCritical",
  "GreatWeaponMaster_BonusAttack",
}

local UNLIMITED_BOOSTS = {
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
}

-- ============================================================================
-- SAFE WRAPPERS
-- ============================================================================
local function SafeAddBoost(uuid, boost)
  pcall(function() AddBoosts(uuid, boost, 0, 0) end)
end
local function SafeRemoveBoost(uuid, boost)
  pcall(function() RemoveBoosts(uuid, boost, 0, 0, 0) end)
end
local function SafeAddPassive(uuid, passive)
  pcall(function() AddPassive(uuid, passive) end)
end
local function SafeRemovePassive(uuid, passive)
  pcall(function() RemovePassive(uuid, passive) end)
end
local function SafeApplyStatus(uuid, status, duration)
  pcall(function() ApplyStatus(uuid, status, duration, 1, 0) end)
end
local function SafeRemoveStatus(uuid, status)
  pcall(function() RemoveStatus(uuid, status, 0) end)
end

-- ============================================================================
-- OVERLORD CONTROLLER
-- ============================================================================
Overlord = Overlord or {}
Overlord.partyMembers = {}
Overlord.godModeActive = false
Overlord.instaKillActive = false
Overlord.unlimitedActive = false
Overlord.refreshTimer = nil
Overlord.applyQueue = {}
Overlord.applyTimer = nil

function Overlord:CheckPrereqs()
  local cmdCall = getAddress("cmdCall")
  if not cmdCall or cmdCall == 0 then
    print("[OVERLORD] ERROR: 'Register Commands' not active!")
    return false
  end
  if type(GetHostCharacter) ~= "function" then
    print("[OVERLORD] ERROR: Command functions not loaded!")
    return false
  end
  local host = GetHostCharacter()
  if not host or host == "" then
    print("[OVERLORD] ERROR: No host character. Load a save first.")
    return false
  end
  return true
end

function Overlord:DetectParty()
  self.partyMembers = {}
  local host = GetHostCharacter()
  
  for _, comp in ipairs(COMPANION_DB) do
    local ok, hp = pcall(function()
      SetArgToString(0, comp.uuid)
      ClearArg(1)
      local r = ExecuteCall("GetHitpoints")
      if r == 1 then return GetArgAsInteger(1) end
      return nil
    end)
    if ok and hp and hp > 0 and hp < 50000 then
      local maxhp = hp
      pcall(function()
        SetArgToString(0, comp.uuid)
        ClearArg(1)
        ExecuteCall("GetMaxHitpoints")
        maxhp = GetArgAsInteger(1) or hp
      end)
      table.insert(self.partyMembers, {
        name = comp.name, uuid = comp.uuid, hp = hp, maxhp = maxhp,
        isHost = (comp.uuid == host)
      })
    end
  end
  
  -- Custom Tav
  local hostFound = false
  for _, m in ipairs(self.partyMembers) do
    if m.isHost then hostFound = true; break end
  end
  if not hostFound and host and host ~= "" then
    local ok, hp = pcall(function()
      SetArgToString(0, host); ClearArg(1)
      ExecuteCall("GetHitpoints"); return GetArgAsInteger(1)
    end)
    if ok and hp and hp > 0 then
      local maxhp = hp
      pcall(function()
        SetArgToString(0, host); ClearArg(1)
        ExecuteCall("GetMaxHitpoints"); maxhp = GetArgAsInteger(1) or hp
      end)
      table.insert(self.partyMembers, 1, {
        name = "Custom Tav", uuid = host, hp = hp, maxhp = maxhp, isHost = true
      })
    end
  end
  return #self.partyMembers
end

-- ============================================================================
-- STAGGERED APPLY: Queue boosts and apply them with delays
-- This is the key fix — instead of flooding commands, we queue them
-- and process one character every 2 seconds via a timer
-- ============================================================================
function Overlord:QueueApply(charIndex)
  if charIndex > #self.partyMembers then
    -- All done
    print("[OVERLORD] All characters boosted!")
    self:StopApplyTimer()
    return
  end
  
  local m = self.partyMembers[charIndex]
  print(string.format("[OVERLORD] Applying to %s (%d/%d)...", m.name, charIndex, #self.partyMembers))
  
  -- God mode
  if self.godModeActive then
    SafeApplyStatus(m.uuid, "INVULNERABLE", -1)
    for _, b in ipairs(GOD_MODE_BOOSTS) do SafeAddBoost(m.uuid, b) end
  end
  
  -- Insta-kill
  if self.instaKillActive then
    for _, b in ipairs(INSTAKILL_BOOSTS) do SafeAddBoost(m.uuid, b) end
    for _, p in ipairs(INSTAKILL_PASSIVES) do SafeAddPassive(m.uuid, p) end
  end
  
  -- Unlimited
  if self.unlimitedActive then
    for _, b in ipairs(UNLIMITED_BOOSTS) do SafeAddBoost(m.uuid, b) end
  end
  
  print(string.format("[OVERLORD]   %s: DONE", m.name))
end

function Overlord:StartStagedApply()
  self:StopApplyTimer()
  local charIdx = 1
  
  -- Apply first character immediately
  self:QueueApply(charIdx)
  charIdx = charIdx + 1
  
  if charIdx <= #self.partyMembers then
    -- Schedule remaining characters with 2-second intervals
    local timer = createTimer(getMainForm())
    timer.Interval = 2000  -- 2 seconds between characters
    timer.OnTimer = function()
      pcall(function()
        self:QueueApply(charIdx)
        charIdx = charIdx + 1
        if charIdx > #self.partyMembers then
          self:StopApplyTimer()
          self:StartRefreshTimer()
          print("")
          print("================================================================")
          print("  OVERLORD MODE FULLY ACTIVE")
          print("  - INVINCIBLE (0 damage taken)")
          print("  - ONE-SHOT EVERYTHING (always crit, ~200-400 dmg)")
          print("  - UNLIMITED actions, spells, movement")
          print("================================================================")
          print("")
        end
      end)
    end
    timer.Enabled = true
    self.applyTimer = timer
  else
    self:StartRefreshTimer()
  end
end

function Overlord:StopApplyTimer()
  if self.applyTimer then
    pcall(function() self.applyTimer.Enabled = false; self.applyTimer.Destroy() end)
    self.applyTimer = nil
  end
end

-- ============================================================================
-- MODULE TOGGLES (instant, no staging needed for single modules)
-- ============================================================================
function Overlord:GodMode()
  if not self:CheckPrereqs() then return end
  if #self.partyMembers == 0 then self:DetectParty() end
  
  if self.godModeActive then
    print("[OVERLORD] Disabling God Mode...")
    for _, m in ipairs(self.partyMembers) do
      SafeRemoveStatus(m.uuid, "INVULNERABLE")
      for _, b in ipairs(GOD_MODE_BOOSTS) do SafeRemoveBoost(m.uuid, b) end
    end
    self.godModeActive = false
    print("[OVERLORD] God Mode OFF")
  else
    pcall(function()
      SetArgToString(0, GetHostCharacter())
      ExecuteCall("RestoreParty")
    end)
    print("[OVERLORD] Enabling God Mode...")
    for _, m in ipairs(self.partyMembers) do
      SafeApplyStatus(m.uuid, "INVULNERABLE", -1)
      for _, b in ipairs(GOD_MODE_BOOSTS) do SafeAddBoost(m.uuid, b) end
      print(string.format("  %s: INVULNERABLE", m.name))
    end
    self.godModeActive = true
    print("[OVERLORD] God Mode ON")
  end
end

function Overlord:InstaKill()
  if not self:CheckPrereqs() then return end
  if #self.partyMembers == 0 then self:DetectParty() end
  
  if self.instaKillActive then
    print("[OVERLORD] Disabling Insta-Kill...")
    for _, m in ipairs(self.partyMembers) do
      for _, b in ipairs(INSTAKILL_BOOSTS) do SafeRemoveBoost(m.uuid, b) end
      for _, p in ipairs(INSTAKILL_PASSIVES) do SafeRemovePassive(m.uuid, p) end
    end
    self.instaKillActive = false
    print("[OVERLORD] Insta-Kill OFF")
  else
    print("[OVERLORD] Enabling Insta-Kill (staged)...")
    self.instaKillActive = true
    self:StartStagedApply()
  end
end

function Overlord:Unlimited()
  if not self:CheckPrereqs() then return end
  if #self.partyMembers == 0 then self:DetectParty() end
  
  if self.unlimitedActive then
    print("[OVERLORD] Disabling Unlimited...")
    for _, m in ipairs(self.partyMembers) do
      for _, b in ipairs(UNLIMITED_BOOSTS) do SafeRemoveBoost(m.uuid, b) end
    end
    self.unlimitedActive = false
    print("[OVERLORD] Unlimited OFF")
  else
    print("[OVERLORD] Enabling Unlimited (staged)...")
    self.unlimitedActive = true
    self:StartStagedApply()
  end
end

-- ============================================================================
-- ENABLE ALL (staged)
-- ============================================================================
function Overlord:Enable()
  print("")
  print("================================================================")
  print("  BG3 OVERLORD MODE v4 (staggered apply, crash-proof)")
  print("================================================================")
  if not self:CheckPrereqs() then return false end
  local count = self:DetectParty()
  if count == 0 then print("[OVERLORD] No party members!"); return false end
  
  print(string.format("[OVERLORD] %d party members:", count))
  for _, m in ipairs(self.partyMembers) do
    print(string.format("  - %s (HP: %d/%d)%s", m.name, m.hp, m.maxhp, m.isHost and " [HOST]" or ""))
  end
  
  -- Heal first
  pcall(function()
    SetArgToString(0, GetHostCharacter())
    ExecuteCall("RestoreParty")
  end)
  print("[OVERLORD] Party healed!")
  
  -- Set flags
  self.godModeActive = true
  self.instaKillActive = true
  self.unlimitedActive = true
  
  -- Start staggered apply (one character every 2 seconds)
  print(string.format("[OVERLORD] Applying boosts (1 character every 2s, ~%ds total)...", count * 2))
  print("")
  self:StartStagedApply()
  
  return true
end

-- ============================================================================
-- DISABLE ALL
-- ============================================================================
function Overlord:Disable()
  print("[OVERLORD] Deactivating...")
  self:StopApplyTimer()
  self:StopRefreshTimer()
  
  for _, m in ipairs(self.partyMembers) do
    SafeRemoveStatus(m.uuid, "INVULNERABLE")
    for _, b in ipairs(GOD_MODE_BOOSTS) do SafeRemoveBoost(m.uuid, b) end
    for _, b in ipairs(INSTAKILL_BOOSTS) do SafeRemoveBoost(m.uuid, b) end
    for _, p in ipairs(INSTAKILL_PASSIVES) do SafeRemovePassive(m.uuid, p) end
    for _, b in ipairs(UNLIMITED_BOOSTS) do SafeRemoveBoost(m.uuid, b) end
  end
  
  -- Safety sweep on all known companions
  for _, comp in ipairs(COMPANION_DB) do
    SafeRemoveStatus(comp.uuid, "INVULNERABLE")
    for _, b in ipairs(GOD_MODE_BOOSTS) do SafeRemoveBoost(comp.uuid, b) end
    for _, b in ipairs(INSTAKILL_BOOSTS) do SafeRemoveBoost(comp.uuid, b) end
    for _, p in ipairs(INSTAKILL_PASSIVES) do SafeRemovePassive(comp.uuid, p) end
    for _, b in ipairs(UNLIMITED_BOOSTS) do SafeRemoveBoost(comp.uuid, b) end
  end
  
  self.godModeActive = false
  self.instaKillActive = false
  self.unlimitedActive = false
  self.partyMembers = {}
  print("[OVERLORD] Fully disabled.")
end

-- ============================================================================
-- STATUS
-- ============================================================================
function Overlord:Status()
  print("")
  print("=== OVERLORD STATUS ===")
  print(string.format("  God Mode:   %s", self.godModeActive and "ACTIVE" or "OFF"))
  print(string.format("  Insta-Kill: %s", self.instaKillActive and "ACTIVE" or "OFF"))
  print(string.format("  Unlimited:  %s", self.unlimitedActive and "ACTIVE" or "OFF"))
  if #self.partyMembers > 0 then
    for _, m in ipairs(self.partyMembers) do
      local hp, maxhp = 0, 0
      pcall(function()
        SetArgToString(0, m.uuid); ClearArg(1)
        ExecuteCall("GetHitpoints"); hp = GetArgAsInteger(1) or 0
        SetArgToString(0, m.uuid); ClearArg(1)
        ExecuteCall("GetMaxHitpoints"); maxhp = GetArgAsInteger(1) or 0
      end)
      print(string.format("    %s: HP=%d/%d%s", m.name, hp, maxhp, m.isHost and " [HOST]" or ""))
    end
  end
  print("")
end

-- ============================================================================
-- REFRESH TIMER (re-apply INVULNERABLE + resources every 30s)
-- ============================================================================
function Overlord:Refresh()
  if #self.partyMembers == 0 then return end
  for _, m in ipairs(self.partyMembers) do
    if self.godModeActive then
      SafeApplyStatus(m.uuid, "INVULNERABLE", -1)
    end
  end
end

function Overlord:StartRefreshTimer()
  self:StopRefreshTimer()
  local timer = createTimer(getMainForm())
  timer.Interval = 30000
  timer.OnTimer = function() pcall(function() self:Refresh() end) end
  timer.Enabled = true
  self.refreshTimer = timer
end

function Overlord:StopRefreshTimer()
  if self.refreshTimer then
    pcall(function() self.refreshTimer.Enabled = false; self.refreshTimer.Destroy() end)
    self.refreshTimer = nil
  end
end

-- ============================================================================
-- BANNER + AUTO-EXECUTE
-- ============================================================================
print("")
print("  ___  _   _ _____ ____  _     ___  ____  ____  ")
print(" / _ \\| | | | ____|  _ \\| |   / _ \\|  _ \\|  _ \\ ")
print("| | | | | | |  _| | |_) | |  | | | | |_) | | | |")
print("| |_| | |_| | |___|  _ <| |__| |_| |  _ <| |_| |")
print(" \\___/ \\___/|_____|_| \\_|_____\\___/|_| \\_|____/ ")
print("")
print("  v4 — Staggered apply (crash-proof)")
print("")
print("  Overlord:Enable()     Overlord:Disable()")
print("  Overlord:GodMode()    Overlord:InstaKill()")
print("  Overlord:Unlimited()  Overlord:Status()")
print("")

Overlord:Enable()
