"""
Clean and optimize conversation logs to reduce token usage.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Generator

from .logmanager import LogManager
from .message import Message, len_tokens
from .util import console

logger = logging.getLogger(__name__)

def clean_log(manager: LogManager) -> Generator[Message, None, None]:
    """Clean a single conversation log to reduce token usage."""
    # Create a backup of the current log
    backup_file = manager.logfile.parent / "conversation.backup.jsonl"
    shutil.copy(manager.logfile, backup_file)

    # Get token count before cleaning
    original_tokens = len_tokens(manager.log.messages)
    console.log(f"Token count before cleaning: {original_tokens}")

    cleaned_entries = []
    seen_entries = set()
    stats = {"user": 0, "assistant": 0, "system": 0, "duplicates": 0}

    # Always keep the first system message (initialization)
    if manager.log.messages and manager.log.messages[0].role == "system":
        cleaned_entries.append(manager.log.messages[0])
        stats["system"] += 1

    def should_keep_system_message(msg: Message) -> bool:
        """Determine if a system message should be kept."""
        if msg.hide or msg.pinned:
            return True
        if "Error:" in msg.content:
            return True
        if "Successfully" in msg.content:
            return False  # Skip success messages
        if "No output" in msg.content:
            return False  # Skip empty output messages
        if "Executed command" in msg.content and len(msg.content) < 50:
            return False  # Skip short command acknowledgments
        return True

    # Process each message
    i = 1  # Skip first message as we handled it
    while i < len(manager.log.messages):
        msg = manager.log.messages[i]
        
        if msg.role in ['user', 'assistant']:
            # Create a tuple of role and content for deduplication
            entry_key = (msg.role, msg.content.strip())
            if entry_key not in seen_entries:
                cleaned_entries.append(msg)
                seen_entries.add(entry_key)
                stats[msg.role] += 1
            else:
                stats["duplicates"] += 1
        
        # Handle system messages
        elif msg.role == 'system':
            if should_keep_system_message(msg):
                if 'Ran command' in msg.content:
                    # Try to combine command and its output
                    command = msg.content.split('Ran command:')[1].strip()
                    command_key = ('system', command)
                    
                    if command_key not in seen_entries:
                        # Look ahead for related messages
                        combined_content = [f"Command: {command}"]
                        j = i + 1
                        while j < len(manager.log.messages):
                            next_msg = manager.log.messages[j]
                            if next_msg.role != 'system':
                                break
                            if 'stdout' in next_msg.content:
                                output = next_msg.content.strip()
                                if len(output) > 500:  # Truncate long outputs
                                    output = output[:500] + "... (truncated)"
                                combined_content.append(f"Output: {output}")
                                j += 1
                            elif 'stderr' in next_msg.content:
                                combined_content.append(f"Error: {next_msg.content.strip()}")
                                j += 1
                            else:
                                break
                        
                        cleaned_msg = Message(
                            "system",
                            " | ".join(combined_content),
                            hide=msg.hide,
                            files=msg.files,
                            quiet=msg.quiet,
                            pinned=msg.pinned
                        )
                        cleaned_entries.append(cleaned_msg)
                        seen_entries.add(command_key)
                        stats["system"] += 1
                        i = j - 1  # Skip the messages we combined
                    else:
                        stats["duplicates"] += 1
                else:
                    cleaned_entries.append(msg)
                    stats["system"] += 1
        
        i += 1

    # Log statistics
    console.log(f"Messages processed:")
    console.log(f"  User messages kept: {stats['user']}")
    console.log(f"  Assistant messages kept: {stats['assistant']}")
    console.log(f"  System messages kept: {stats['system']}")
    console.log(f"  Duplicate messages removed: {stats['duplicates']}")

    # Create a new log with cleaned entries
    manager.edit(cleaned_entries)

    # Get token count after cleaning
    cleaned_tokens = len_tokens(manager.log.messages)
    tokens_saved = original_tokens - cleaned_tokens
    console.log(f"Token count after cleaning: {cleaned_tokens}")
    console.log(f"Tokens saved: {tokens_saved} ({(tokens_saved/original_tokens)*100:.1f}%)")

    yield Message(
        "system",
        f"Cleaned conversation log. Tokens saved: {tokens_saved} ({(tokens_saved/original_tokens)*100:.1f}%)"
    )

def clean_all_logs(logs_dir: Path) -> Generator[Message, None, None]:
    """Clean all conversation logs in the logs directory."""
    total_tokens_saved = 0
    total_original_tokens = 0
    
    # Get all conversation directories
    directories = sorted(logs_dir.iterdir(), key=lambda d: d.name, reverse=True)
    for directory in directories:
        if directory.is_dir() and (directory / "conversation.jsonl").exists():
            console.log(f"\nCleaning {directory.name}...")
            manager = LogManager.load(directory)
            
            # Get token counts before cleaning
            original_tokens = len_tokens(manager.log.messages)
            total_original_tokens += original_tokens
            
            # Clean the log
            for msg in clean_log(manager):
                pass  # Consume the generator
            
            # Calculate tokens saved
            cleaned_tokens = len_tokens(manager.log.messages)
            tokens_saved = original_tokens - cleaned_tokens
            total_tokens_saved += tokens_saved

    if total_original_tokens > 0:
        yield Message(
            "system",
            f"Cleaned all logs. Total tokens saved: {total_tokens_saved} "
            f"({(total_tokens_saved/total_original_tokens)*100:.1f}%)"
        )
    else:
        yield Message("system", "No logs found to clean")
