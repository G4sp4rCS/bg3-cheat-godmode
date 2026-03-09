"""
================================================================================
  BG3 PARTY GOD MODE — Python Standalone (pymem)
  
  100% independent from Cheat Engine. Attaches to bg3_dx11.exe and applies
  invincibility to all party members via code cave injection.
  
  Modes:
    --party-only   (default) Inject code cave that skips damage ONLY for
                   entities in the player entity whitelist
    --all          Patch damage function globally (enemies also invincible)
    --disable      Remove all patches and restore original code
    
  Requirements:
    pip install pymem
    Run as Administrator (required for process memory access)
    
  Author: DarkForge-X
  Target: Baldur's Gate 3 v4.1.1+ (bg3_dx11.exe / bg3.exe)
================================================================================
"""

import sys
import time
import ctypes
import struct
import argparse
import logging
from typing import Optional

try:
    import pymem
    import pymem.process
    import pymem.pattern
except ImportError:
    print("[!] pymem not installed. Run: pip install pymem")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Process names to look for
PROCESS_NAMES = ["bg3_dx11.exe", "bg3.exe"]

# AOB pattern for the damage function entry point
# cmp byte ptr [rcx+000001C8], 00 | jne <skip_damage>
# This is the god mode check in the damage handler
DAMAGE_FUNC_AOB = b"\x80\xB9\xC8\x01\x00\x00\x00\x0F\x85"

# Offset from AOB match to the JNE instruction we want to patch
JNE_OFFSET = 7

# Original bytes at the JNE (conditional jump)
ORIGINAL_BYTES = bytes([0x0F, 0x85])

# Patched bytes: NOP + JMP (unconditional jump, skips damage for everyone)
PATCHED_BYTES_ALL = bytes([0x90, 0xE9])

# Known BG3 companion UUIDs (for reference / future use)
COMPANIONS = {
    "Astarion":    "c7c13742-bacd-460a-8f65-f864fe41f255",
    "Gale":        "ad9af97d-75da-406a-ae13-7071c563f604",
    "Karlach":     "2c76687d-93a2-477b-8b18-8a14b549304c",
    "Laezel":      "58a69333-40bf-8571-d77a-93e42c29260e",
    "Wyll":        "c774d764-4a17-48dc-b470-32ace9ce447d",
    "ShadowHeart": "3ed74f06-3c60-42dc-83f6-f034cb47c679",
    "Minsc":       "0de603c5-42e2-4811-9210-f178b28716a8",
    "Jaheira":     "91b6b200-7d00-4d62-8dc9-99e8339dfa1a",
    "Minthara":    "25721313-0c15-4571-acc5-b83e5e09b30c",
    "Halsin":      "7628bc0e-52b8-42a7-856a-13a6fd413323",
    "DarkUrge":    "3130cff0-5765-4b71-b857-a2b00228087b",
}

# God mode byte offset from entity base
GODMODE_OFFSET = 0x1C8

# Max entities in whitelist
MAX_WHITELIST = 16

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger("BG3GodMode")


# ============================================================================
# CORE CLASS
# ============================================================================

class BG3GodMode:
    """Baldur's Gate 3 God Mode injector using pymem."""
    
    def __init__(self):
        self.pm: Optional[pymem.Pymem] = None
        self.process_name: str = ""
        self.module_base: int = 0
        self.module_size: int = 0
        self.damage_func_addr: int = 0
        self.jne_addr: int = 0
        self.original_bytes_backup: bytes = b""
        self.code_cave_addr: int = 0
        self.whitelist_addr: int = 0
        self.is_patched: bool = False
        self.mode: str = ""
    
    # ========================================================================
    # ATTACH
    # ========================================================================
    
    def attach(self) -> bool:
        """Attach to BG3 process."""
        for name in PROCESS_NAMES:
            try:
                self.pm = pymem.Pymem(name)
                self.process_name = name
                log.info(f"Attached to {name} (PID: {self.pm.process_id})")
                
                # Get module info
                module = pymem.process.module_from_name(
                    self.pm.process_handle, name
                )
                if module:
                    self.module_base = module.lpBaseOfDll
                    self.module_size = module.SizeOfImage
                    log.info(
                        f"Module base: 0x{self.module_base:X}, "
                        f"size: {self.module_size // (1024*1024)} MB"
                    )
                return True
            except pymem.exception.ProcessNotFound:
                continue
            except pymem.exception.CouldNotOpenProcess:
                log.error(f"Found {name} but cannot open it. Run as Administrator!")
                return False
        
        log.error("BG3 process not found! Make sure the game is running.")
        return False
    
    # ========================================================================
    # AOB SCAN
    # ========================================================================
    
    def find_damage_function(self) -> bool:
        """Find the damage function via AOB scan."""
        log.info("Scanning for damage function AOB pattern...")
        
        try:
            # Read the entire module
            module_bytes = self.pm.read_bytes(self.module_base, self.module_size)
        except Exception as e:
            log.error(f"Failed to read module memory: {e}")
            return False
        
        # Search for the AOB pattern
        offset = 0
        found = []
        while True:
            idx = module_bytes.find(DAMAGE_FUNC_AOB, offset)
            if idx == -1:
                break
            found.append(self.module_base + idx)
            offset = idx + 1
        
        if len(found) == 0:
            log.error("AOB pattern not found! Game version may be incompatible.")
            return False
        
        if len(found) > 1:
            log.warning(f"Found {len(found)} matches, using first one.")
            for i, addr in enumerate(found):
                log.warning(f"  Match {i+1}: 0x{addr:X}")
        
        self.damage_func_addr = found[0]
        self.jne_addr = self.damage_func_addr + JNE_OFFSET
        
        log.info(f"Damage function found at: 0x{self.damage_func_addr:X}")
        log.info(f"JNE instruction at: 0x{self.jne_addr:X}")
        
        # Verify the bytes at the JNE location
        current_bytes = self.pm.read_bytes(self.jne_addr, 2)
        if current_bytes == ORIGINAL_BYTES:
            log.info("JNE bytes verified: 0F 85 (original, unpatched)")
        elif current_bytes == PATCHED_BYTES_ALL:
            log.warning("Already patched with global disable! (90 E9)")
            self.is_patched = True
        else:
            log.warning(
                f"Unexpected bytes at JNE: {current_bytes.hex()}. "
                f"Possible incompatible version or already patched."
            )
        
        return True
    
    # ========================================================================
    # MODE 1: GLOBAL DAMAGE DISABLE (simple patch)
    # ========================================================================
    
    def patch_global(self) -> bool:
        """Patch damage function to skip all damage (affects ALL entities)."""
        if self.is_patched:
            log.warning("Already patched!")
            return True
        
        # Backup original bytes
        self.original_bytes_backup = self.pm.read_bytes(self.jne_addr, 2)
        
        # Patch: JNE -> NOP + JMP (unconditional)
        self.pm.write_bytes(self.jne_addr, PATCHED_BYTES_ALL, 2)
        
        # Verify
        verify = self.pm.read_bytes(self.jne_addr, 2)
        if verify == PATCHED_BYTES_ALL:
            self.is_patched = True
            self.mode = "global"
            log.info("GLOBAL DAMAGE DISABLE applied!")
            log.info("ALL entities are now invincible (including enemies)")
            return True
        else:
            log.error("Patch verification failed!")
            return False
    
    # ========================================================================
    # MODE 2: PARTY-ONLY GOD MODE (code cave injection)
    # ========================================================================
    
    def patch_party_only(self) -> bool:
        """
        Inject code cave that skips damage only for whitelisted entities.
        
        The code cave:
        1. Checks if the entity (rcx) is in a whitelist
        2. If yes -> force skip damage (jump to skip address)
        3. If no  -> execute original god mode check
        """
        if self.is_patched:
            log.warning("Already patched!")
            return True
        
        # Calculate the skip address from the JNE relative offset
        # JNE is: 0F 85 XX XX XX XX (6 bytes)
        jne_bytes = self.pm.read_bytes(self.jne_addr, 6)
        rel_offset = struct.unpack("<i", jne_bytes[2:6])[0]
        skip_addr = self.jne_addr + 6 + rel_offset  # address after JNE + relative offset
        continue_addr = self.jne_addr + 6  # address right after JNE (normal flow)
        
        log.info(f"Skip damage address: 0x{skip_addr:X}")
        log.info(f"Continue address: 0x{continue_addr:X}")
        
        # Allocate memory for:
        # 1. Entity whitelist (MAX_WHITELIST * 8 bytes for pointers)
        # 2. Code cave (~128 bytes should be enough)
        total_alloc = (MAX_WHITELIST * 8) + 256
        
        try:
            alloc_addr = self.pm.allocate(total_alloc)
        except Exception as e:
            log.error(f"Failed to allocate memory: {e}")
            return False
        
        self.whitelist_addr = alloc_addr
        self.code_cave_addr = alloc_addr + (MAX_WHITELIST * 8)
        
        log.info(f"Whitelist at: 0x{self.whitelist_addr:X}")
        log.info(f"Code cave at: 0x{self.code_cave_addr:X}")
        
        # Initialize whitelist to zeros
        self.pm.write_bytes(
            self.whitelist_addr, 
            b"\x00" * (MAX_WHITELIST * 8), 
            MAX_WHITELIST * 8
        )
        
        # Build the code cave shellcode
        # 
        # The code cave does:
        #   push rax
        #   push rbx
        #   push rcx (preserve all)
        #   lea rbx, [whitelist_addr]
        #   mov ecx, MAX_WHITELIST
        # .loop:
        #   mov rax, [rbx]
        #   test rax, rax
        #   jz .not_found        ; end of list (null terminator)
        #   cmp rax, r15         ; r15 = rcx at entry (entity ptr, saved earlier)
        #   je .found_player
        #   add rbx, 8
        #   dec ecx
        #   jnz .loop
        # .not_found:
        #   pop rcx
        #   pop rbx
        #   pop rax
        #   ; Execute original code: cmp byte ptr [rcx+1C8], 00
        #   cmp byte ptr [rcx+0x1C8], 0
        #   jne .skip_damage
        #   jmp continue_addr
        # .found_player:
        #   pop rcx
        #   pop rbx
        #   pop rax
        #   jmp skip_addr
        # .skip_damage:
        #   jmp skip_addr
        
        # NOTE: At the injection point, rcx still holds the entity pointer
        # (mov r15, rcx happened at bg3.exe+492BC52, right before our injection)
        # So we can use rcx directly
        
        shellcode = bytearray()
        
        # Save registers
        shellcode += b"\x50"          # push rax
        shellcode += b"\x53"          # push rbx
        shellcode += b"\x51"          # push rcx
        
        # lea rbx, [whitelist_addr] — use mov rbx, imm64
        shellcode += b"\x48\xBB"      # mov rbx, imm64
        shellcode += struct.pack("<Q", self.whitelist_addr)
        
        # mov ecx, MAX_WHITELIST
        shellcode += b"\xB9"           # mov ecx, imm32
        shellcode += struct.pack("<I", MAX_WHITELIST)
        
        # .loop: (offset = current position)
        loop_offset = len(shellcode)
        
        # mov rax, [rbx]
        shellcode += b"\x48\x8B\x03"  # mov rax, [rbx]
        
        # test rax, rax
        shellcode += b"\x48\x85\xC0"  # test rax, rax
        
        # jz .not_found (placeholder, will fix)
        jz_not_found_pos = len(shellcode)
        shellcode += b"\x74\x00"       # jz rel8 (placeholder)
        
        # We need to compare with the original rcx value
        # At entry, the original rcx was saved to r15 (mov r15, rcx at +492BC52)
        # But we also pushed rcx. The original rcx is on the stack.
        # Actually, when we entered the code cave, rcx = entity pointer (unchanged)
        # We pushed rcx, so [rsp] = rcx, [rsp+8] = rbx_saved, [rsp+16] = rax_saved
        # Let's compare rax with [rsp] (saved rcx = entity ptr)
        
        # cmp rax, [rsp]  — compare with saved rcx (entity pointer)
        shellcode += b"\x48\x3B\x04\x24"  # cmp rax, [rsp]
        
        # je .found_player (placeholder)
        je_found_pos = len(shellcode)
        shellcode += b"\x74\x00"       # je rel8 (placeholder)
        
        # add rbx, 8
        shellcode += b"\x48\x83\xC3\x08"  # add rbx, 8
        
        # dec ecx
        shellcode += b"\xFF\xC9"       # dec ecx
        
        # jnz .loop
        jnz_target = loop_offset - (len(shellcode) + 2)
        shellcode += b"\x75"
        shellcode += struct.pack("b", jnz_target)
        
        # .not_found:
        not_found_offset = len(shellcode)
        # Fix jz placeholder
        shellcode[jz_not_found_pos + 1] = not_found_offset - (jz_not_found_pos + 2)
        
        # pop rcx, rbx, rax
        shellcode += b"\x59"           # pop rcx
        shellcode += b"\x5B"           # pop rbx
        shellcode += b"\x58"           # pop rax
        
        # Execute original code: cmp byte ptr [rcx+1C8], 00
        shellcode += b"\x80\xB9\xC8\x01\x00\x00\x00"  # cmp byte [rcx+0x1C8], 0
        
        # jne -> skip_damage (use jmp with rel32)
        # But first, if NOT equal (god mode entity), jump to skip
        jne_to_skip_pos = len(shellcode)
        shellcode += b"\x0F\x85"       # jne rel32 (placeholder)
        shellcode += b"\x00\x00\x00\x00"
        
        # jmp continue_addr (normal flow, entity takes damage)
        jmp_continue_pos = len(shellcode)
        shellcode += b"\xE9"           # jmp rel32
        shellcode += b"\x00\x00\x00\x00"
        
        # .found_player:
        found_offset = len(shellcode)
        # Fix je placeholder
        shellcode[je_found_pos + 1] = found_offset - (je_found_pos + 2)
        
        # pop rcx, rbx, rax
        shellcode += b"\x59"           # pop rcx
        shellcode += b"\x5B"           # pop rbx
        shellcode += b"\x58"           # pop rax
        
        # jmp skip_addr (force skip damage for player)
        jmp_skip_pos = len(shellcode)
        shellcode += b"\xE9"           # jmp rel32
        shellcode += b"\x00\x00\x00\x00"
        
        # .skip_damage (from the jne after original cmp):
        skip_damage_from_jne = len(shellcode)
        # jmp skip_addr
        jmp_skip2_pos = len(shellcode)
        shellcode += b"\xE9"
        shellcode += b"\x00\x00\x00\x00"
        
        # Fix relative addresses
        # jne_to_skip: from jne_to_skip_pos+6 to skip_damage_from_jne
        cave_base = self.code_cave_addr
        
        jne_from = cave_base + jne_to_skip_pos + 6
        jne_to = cave_base + skip_damage_from_jne
        struct.pack_into("<i", shellcode, jne_to_skip_pos + 2, jne_to - jne_from)
        
        # jmp continue_addr
        jmp_from = cave_base + jmp_continue_pos + 5
        struct.pack_into("<i", shellcode, jmp_continue_pos + 1, continue_addr - jmp_from)
        
        # jmp skip_addr (found_player)
        jmp_from2 = cave_base + jmp_skip_pos + 5
        struct.pack_into("<i", shellcode, jmp_skip_pos + 1, skip_addr - jmp_from2)
        
        # jmp skip_addr (from jne path)
        jmp_from3 = cave_base + jmp_skip2_pos + 5
        struct.pack_into("<i", shellcode, jmp_skip2_pos + 1, skip_addr - jmp_from3)
        
        # Write the code cave
        self.pm.write_bytes(self.code_cave_addr, bytes(shellcode), len(shellcode))
        log.info(f"Code cave written: {len(shellcode)} bytes")
        
        # Backup original bytes at injection point
        # We need to replace 13 bytes (7 for CMP + 6 for JNE)
        self.original_bytes_backup = self.pm.read_bytes(self.damage_func_addr, 13)
        
        # Build the jump to code cave
        # JMP rel32 from damage_func_addr to code_cave_addr
        jump_from = self.damage_func_addr + 5  # after the 5-byte JMP
        jump_rel = self.code_cave_addr - jump_from
        
        injection = bytearray()
        injection += b"\xE9"           # JMP rel32
        injection += struct.pack("<i", jump_rel)
        # NOP the remaining bytes (13 - 5 = 8 NOPs)
        injection += b"\x90" * 8
        
        # Write the injection
        self.pm.write_bytes(self.damage_func_addr, bytes(injection), len(injection))
        
        self.is_patched = True
        self.mode = "party-only"
        
        log.info("PARTY-ONLY GOD MODE code cave injected!")
        log.info("Now populating entity whitelist...")
        
        return True
    
    # ========================================================================
    # ENTITY SCANNER: Find player entities by scanning for god mode structures
    # ========================================================================
    
    def scan_player_entities(self) -> list[int]:
        """
        Scan for player entity pointers by looking for entities whose
        structure matches player characteristics.
        
        Strategy: Search for the known HP values we got from the game,
        then backtrack to find the entity root.
        """
        entities = []
        
        # We'll use the damage function's behavior to collect entity pointers.
        # Alternative: scan for characteristic memory patterns near entity objects.
        
        # For now, use a different approach: scan for entities that have
        # the god mode flag area with specific patterns.
        # Player entities in BG3 have identifiable structures.
        
        log.info("Scanning for player entities...")
        log.info("(Entities will be captured as they enter combat or take actions)")
        
        return entities
    
    def add_entity_to_whitelist(self, entity_addr: int, slot: int = -1) -> bool:
        """Add an entity address to the whitelist."""
        if not self.whitelist_addr:
            log.error("Whitelist not initialized!")
            return False
        
        if slot == -1:
            # Find first empty slot
            for i in range(MAX_WHITELIST):
                addr = self.whitelist_addr + (i * 8)
                val = struct.unpack("<Q", self.pm.read_bytes(addr, 8))[0]
                if val == 0:
                    slot = i
                    break
            if slot == -1:
                log.error("Whitelist is full!")
                return False
        
        write_addr = self.whitelist_addr + (slot * 8)
        self.pm.write_bytes(write_addr, struct.pack("<Q", entity_addr), 8)
        log.info(f"Added entity 0x{entity_addr:X} to whitelist slot {slot}")
        return True
    
    def clear_whitelist(self):
        """Clear the entity whitelist."""
        if self.whitelist_addr:
            self.pm.write_bytes(
                self.whitelist_addr,
                b"\x00" * (MAX_WHITELIST * 8),
                MAX_WHITELIST * 8
            )
            log.info("Whitelist cleared")
    
    def show_whitelist(self):
        """Display current whitelist contents."""
        if not self.whitelist_addr:
            log.info("Whitelist not initialized")
            return
        
        log.info("Current entity whitelist:")
        for i in range(MAX_WHITELIST):
            addr = self.whitelist_addr + (i * 8)
            val = struct.unpack("<Q", self.pm.read_bytes(addr, 8))[0]
            if val != 0:
                log.info(f"  Slot {i}: 0x{val:X}")
    
    # ========================================================================
    # ENTITY CAPTURE VIA BREAKPOINT HOOK
    # ========================================================================
    
    def capture_entities_via_hook(self, duration: float = 5.0) -> list[int]:
        """
        Temporarily install a capture hook that records all entity pointers
        passing through the damage function. Requires game activity (combat).
        
        Alternative approach: Read from the entity list directly.
        """
        log.info(f"Entity capture not available in standalone mode.")
        log.info(f"Use --all mode or manually add entities.")
        return []
    
    # ========================================================================
    # UNPATCH / RESTORE
    # ========================================================================
    
    def unpatch(self) -> bool:
        """Remove all patches and restore original code."""
        if not self.is_patched:
            log.info("Nothing to unpatch")
            return True
        
        if self.original_bytes_backup:
            if self.mode == "global":
                self.pm.write_bytes(
                    self.jne_addr, 
                    self.original_bytes_backup, 
                    len(self.original_bytes_backup)
                )
            elif self.mode == "party-only":
                self.pm.write_bytes(
                    self.damage_func_addr, 
                    self.original_bytes_backup, 
                    len(self.original_bytes_backup)
                )
            
            log.info("Original bytes restored")
        
        # Free allocated memory
        if self.code_cave_addr:
            try:
                # pymem.free doesn't exist directly, memory freed on process exit
                pass
            except Exception:
                pass
        
        self.is_patched = False
        self.mode = ""
        log.info("All patches removed!")
        return True
    
    # ========================================================================
    # STATUS
    # ========================================================================
    
    def status(self):
        """Print current status."""
        print("\n" + "=" * 50)
        print("  BG3 GOD MODE STATUS")
        print("=" * 50)
        print(f"  Process:     {self.process_name} (PID: {self.pm.process_id if self.pm else 'N/A'})")
        print(f"  Module base: 0x{self.module_base:X}")
        print(f"  Damage func: 0x{self.damage_func_addr:X}")
        print(f"  Patched:     {self.is_patched}")
        print(f"  Mode:        {self.mode or 'none'}")
        
        if self.mode == "party-only":
            print(f"  Whitelist:   0x{self.whitelist_addr:X}")
            print(f"  Code cave:   0x{self.code_cave_addr:X}")
            self.show_whitelist()
        
        # Check current bytes at patch location
        if self.jne_addr:
            current = self.pm.read_bytes(self.jne_addr, 2)
            state = "ORIGINAL" if current == ORIGINAL_BYTES else "PATCHED"
            print(f"  JNE bytes:   {current.hex()} ({state})")
        
        print("=" * 50 + "\n")
    
    # ========================================================================
    # CLEANUP
    # ========================================================================
    
    def cleanup(self):
        """Clean shutdown."""
        if self.is_patched:
            self.unpatch()
        if self.pm:
            self.pm.close_process()
            log.info("Process handle closed")


# ============================================================================
# INTERACTIVE MODE
# ============================================================================

def interactive_mode(gm: BG3GodMode):
    """Interactive command loop."""
    print("\n" + "=" * 50)
    print("  BG3 GOD MODE — INTERACTIVE MODE")
    print("=" * 50)
    print("  Commands:")
    print("    all      - Enable global damage disable")
    print("    party    - Enable party-only god mode")
    print("    off      - Disable all patches")
    print("    status   - Show current status")
    print("    add <hex> - Add entity to whitelist")
    print("    list     - Show whitelist")
    print("    clear    - Clear whitelist")
    print("    quit     - Exit (removes patches)")
    print("=" * 50)
    
    while True:
        try:
            cmd = input("\n[BG3] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        
        if not cmd:
            continue
        
        parts = cmd.split()
        action = parts[0]
        
        if action in ("quit", "exit", "q"):
            break
        elif action == "all":
            if gm.is_patched:
                gm.unpatch()
            gm.patch_global()
        elif action == "party":
            if gm.is_patched:
                gm.unpatch()
            gm.patch_party_only()
        elif action in ("off", "disable", "restore"):
            gm.unpatch()
        elif action == "status":
            gm.status()
        elif action == "add" and len(parts) > 1:
            try:
                addr = int(parts[1], 16)
                gm.add_entity_to_whitelist(addr)
            except ValueError:
                print("Invalid address. Use hex format: add 1A97B9B94A0")
        elif action == "list":
            gm.show_whitelist()
        elif action == "clear":
            gm.clear_whitelist()
        else:
            print(f"Unknown command: {cmd}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="BG3 Party God Mode — Python Standalone",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bg3_godmode.py --all          # Disable all damage globally
  python bg3_godmode.py --party-only   # Player-only god mode (code cave)
  python bg3_godmode.py --interactive  # Interactive command mode
  python bg3_godmode.py --disable      # Remove all patches
        """
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all", action="store_true",
        help="Disable ALL damage (enemies also invincible)"
    )
    group.add_argument(
        "--party-only", action="store_true", default=True,
        help="Party-only god mode via code cave (default)"
    )
    group.add_argument(
        "--disable", action="store_true",
        help="Remove all patches and restore original code"
    )
    group.add_argument(
        "--interactive", "-i", action="store_true",
        help="Interactive command mode"
    )
    
    parser.add_argument(
        "--keep-alive", "-k", action="store_true",
        help="Keep running (don't exit after patching)"
    )
    
    args = parser.parse_args()
    
    # Banner
    print(r"""
    ____  ____  _____    ____           __  __  __          __   
   / __ )/ ___)|___ /   / ___| ___   ___|  \/  |___   __ _| ___ 
  |  _ | |  _   |_ \  | |  _ / _ \ / __| |\/| / _ \ / _` |/ _ \
  | |_) | |_| | ___) | | |_| | (_) | (__| |  | (_) | (_| |  __/
  |____/ \____|____/   \____|\___/ \___|_|  |_\___/ \__,_|\___|
                                                                
    Python Standalone — No Cheat Engine Required
    """)
    
    gm = BG3GodMode()
    
    try:
        # Attach to process
        if not gm.attach():
            sys.exit(1)
        
        # Find damage function
        if not gm.find_damage_function():
            sys.exit(1)
        
        if args.interactive:
            interactive_mode(gm)
        elif args.disable:
            gm.unpatch()
        elif args.all:
            if gm.patch_global():
                print("\n[+] GLOBAL DAMAGE DISABLE ACTIVE")
                print("[!] Warning: Enemies are also invincible!")
                if args.keep_alive:
                    print("\nPress Ctrl+C to remove patches and exit...")
                    try:
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        pass
        else:
            # Default: party-only
            if gm.patch_party_only():
                print("\n[+] PARTY-ONLY GOD MODE ACTIVE")
                print("[*] Note: Add entity addresses to whitelist for targeted protection")
                print("[*] Use --all for simpler global protection")
                print("[*] Use --interactive for full control")
                if args.keep_alive:
                    print("\nPress Ctrl+C to remove patches and exit...")
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
        gm.cleanup()
        print("\n[*] BG3 God Mode shut down cleanly.")


if __name__ == "__main__":
    main()
