"""
Command handling for the CLI.
"""

import logging
import re
import sys
from collections.abc import Generator
from pathlib import Path
from time import sleep
from typing import Literal

from . import llm
from .export import export_chat_to_html
from .logmanager import LogManager, prepare_messages
from .message import (
    Message,
    len_tokens,
    msgs_to_toml,
    print_msg,
    toml_to_msgs,
)
from .models import get_model
from .tools import ToolUse, execute_msg, loaded_tools
from .tools.base import ConfirmFunc
from .useredit import edit_text_with_editor

logger = logging.getLogger(__name__)

Actions = Literal[
    "undo",
    "log",
    "tools",
    "edit",
    "rename",
    "fork",
    "summarize",
    "replay",
    "impersonate",
    "tokens",
    "export",
    "help",
    "exit",
    "reload",
    "cleanlogs",
    "profile",
]

action_descriptions: dict[Actions, str] = {
    "undo": "Undo the last action",
    "log": "Show the conversation log",
    "tools": "Show available tools",
    "edit": "Edit the conversation in your editor",
    "rename": "Rename the conversation",
    "fork": "Create a copy of the conversation with a new name",
    "summarize": "Summarize the conversation",
    "replay": "Re-execute codeblocks in the conversation, wont store output in log",
    "impersonate": "Impersonate the assistant",
    "tokens": "Show the number of tokens used",
    "export": "Export conversation as standalone HTML",
    "help": "Show this help message",
    "exit": "Exit the program",
    "reload": "Reload all modules and reinitialize the application",
    "cleanlogs": "Clean and optimize conversation logs to reduce token usage",
    "profile": "Analyze the current profile.stats file",
}
COMMANDS = list(action_descriptions.keys())


def execute_cmd(msg: Message, log: LogManager, confirm: ConfirmFunc) -> bool:
    """Executes any user-command, returns True if command was executed."""
    assert msg.role == "user"

    # if message starts with / treat as command
    # when command has been run,
    if msg.content[:1] in ["/"]:
        for resp in handle_cmd(msg.content, log, confirm):
            log.append(resp)
        return True
    return False


def handle_cmd(
    cmd: str,
    manager: LogManager,
    confirm: ConfirmFunc,
) -> Generator[Message, None, None]:
    """Handles a command."""
    cmd = cmd.lstrip("/")
    logger.debug(f"Executing command: {cmd}")
    name, *args = re.split(r"[\n\s]", cmd)
    full_args = cmd.split(" ", 1)[1] if " " in cmd else ""
    match name:
        case "profile":
            # First undo the /profile command itself
            manager.undo(1, quiet=True)
            
            from pathlib import Path
            profile_path = Path("profile.stats")
            
            if not profile_path.exists():
                yield Message("system", "No profile data found. Run gptme with --profile flag first.")
                return
                
            import pstats
            from io import StringIO
            from contextlib import redirect_stdout

            try:
                # Create a string buffer to capture output
                output = StringIO()
                
                # Redirect stdout to our string buffer
                with redirect_stdout(output):
                    # Create Stats object with string path
                    stats = pstats.Stats(str(profile_path.absolute()))
                    stats.strip_dirs()
                    
                    # Print different views of the profile data
                    print("\n=== Top 20 Functions by Cumulative Time ===")
                    stats.sort_stats('cumulative')
                    stats.print_stats(20)
                    
                    print("\n=== Top 20 Functions by Call Count ===")
                    stats.sort_stats('calls')
                    stats.print_stats(20)
                
                # Get the complete output
                yield Message("system", output.getvalue())
            except Exception as e:
                yield Message("system", f"Error analyzing profile data: {str(e)}\nProfile path: {profile_path.absolute()}")
                
        case "cleanlogs":
            # First undo the /cleanlogs command itself
            manager.undo(1, quiet=True)
            
            from .clean_logs import clean_log, clean_all_logs
            
            # Check if --all flag is present
            if "--all" in args:
                yield Message("system", "Cleaning all conversation logs...")
                yield from clean_all_logs(get_logs_dir())
            else:
                yield Message("system", "Cleaning current conversation log...")
                yield from clean_log(manager)
                
        case "log":
            manager.undo(1, quiet=True)
            manager.log.print(show_hidden="--hidden" in args)
        case "rename":
            manager.undo(1, quiet=True)
            manager.write()
            # rename the conversation
            print("Renaming conversation")
            if args:
                new_name = args[0]
            else:
                print("(enter empty name to auto-generate)")
                new_name = input("New name: ").strip()
            rename(manager, new_name, confirm)
        case "fork":
            # fork the conversation
            new_name = args[0] if args else input("New name: ")
            manager.fork(new_name)
        case "summarize":
            msgs = prepare_messages(manager.log.messages)
            msgs = [m for m in msgs if not m.hide]
            summary = llm.summarize(msgs)
            print(f"Summary: {summary}")
        case "edit":
            # edit previous messages
            # first undo the '/edit' command itself
            manager.undo(1, quiet=True)
            yield from edit(manager)
        case "undo":
            # undo the '/undo' command itself
            manager.undo(1, quiet=True)
            # if int, undo n messages
            n = int(args[0]) if args and args[0].isdigit() else 1
            manager.undo(n)
        case "exit":
            manager.undo(1, quiet=True)
            manager.write()
            sys.exit(0)
        case "replay":
            manager.undo(1, quiet=True)
            manager.write()
            print("Replaying conversation...")
            for msg in manager.log:
                if msg.role == "assistant":
                    for reply_msg in execute_msg(msg, confirm):
                        print_msg(reply_msg, oneline=False)
        case "impersonate":
            content = full_args if full_args else input("[impersonate] Assistant: ")
            msg = Message("assistant", content)
            yield msg
            yield from execute_msg(msg, confirm=lambda _: True)
        case "tokens":
            manager.undo(1, quiet=True)
            n_tokens = len_tokens(manager.log.messages)
            print(f"Tokens used: {n_tokens}")
            model = get_model()
            if model:
                print(f"Model: {model.model}")
                if model.price_input:
                    print(f"Cost (input): ${n_tokens * model.price_input / 1_000_000}")
        case "tools":
            manager.undo(1, quiet=True)
            print("Available tools:")
            for tool in loaded_tools:
                print(
                    f"""
  # {tool.name}
    {tool.desc.rstrip(".")}
    tokens (example): {len_tokens(tool.examples)}"""
                )
        case "export":
            manager.undo(1, quiet=True)
            manager.write()
            # Get output path from args or use default
            output_path = (
                Path(args[0]) if args else Path(f"{manager.logfile.parent.name}.html")
            )
            # Export the chat
            export_chat_to_html(manager.name, manager.log, output_path)
            print(f"Exported conversation to {output_path}")
        case "reload":
            # First undo the /reload command itself
            manager.undo(1, quiet=True)
            yield Message("system", "Reloading modules...")
            
            # Store current settings
            from .models import DEFAULT_MODEL
            current_model = DEFAULT_MODEL
            from .tools import loaded_tools
            current_tools = [tool.name for tool in loaded_tools]
            
            # Cleanup stateful components
            from .tools.shell import cleanup_shell
            cleanup_shell()
            
            # Get the package name
            import gptme
            package_name = gptme.__name__
            
            # Get all loaded modules that are part of our package
            import sys
            modules_to_reload = [
                mod for name, mod in sys.modules.items()
                if name.startswith(package_name + ".")
            ]
            
            # Sort modules to ensure proper reload order
            modules_to_reload.sort(
                key=lambda mod: len(mod.__name__.split("."))
            )
            
            # Reload all modules
            import importlib
            for module in modules_to_reload:
                try:
                    importlib.reload(module)
                except Exception as e:
                    yield Message("system", f"Error reloading {module.__name__}: {e}")
                    return
            
            try:
                # Reload the main package
                import gptme
                importlib.reload(gptme)
                
                # Re-import key components after reload
                from .tools import init_tools
                from .init import init
                from .chat import auto_confirm, AutoConfirm
                from .models import set_default_model
                
                # Create new auto_confirm instance
                global auto_confirm
                auto_confirm = AutoConfirm()
                
                # Reinitialize with preserved settings
                init_tools(current_tools)
                init(current_model.model if current_model else None, True, current_tools)
                
                yield Message("system", "Successfully reloaded all modules")
            except Exception as e:
                yield Message("system", f"Error during reinitialization: {e}")
                # Try to recover by reinitializing with defaults
                try:
                    init_tools(None)
                    init(None, True, None)
                    yield Message("system", "Recovered with default settings")
                except Exception as e2:
                    yield Message("system", f"Failed to recover: {e2}")
        case _:
            # the case for python, shell, and other block_types supported by tools
            tooluse = ToolUse(name, [], full_args)
            if tooluse.is_runnable:
                yield from tooluse.execute(confirm)
            else:
                if manager.log[-1].content.strip() == "/help":
                    # undo the '/help' command itself
                    manager.undo(1, quiet=True)
                    manager.write()
                    help()
                else:
                    print("Unknown command")


def edit(manager: LogManager) -> Generator[Message, None, None]:  # pragma: no cover
    # generate editable toml of all messages
    t = msgs_to_toml(reversed(manager.log))  # type: ignore
    res = None
    while not res:
        t = edit_text_with_editor(t, "toml")
        try:
            res = toml_to_msgs(t)
        except Exception as e:
            print(f"\nFailed to parse TOML: {e}")
            try:
                sleep(1)
            except KeyboardInterrupt:
                yield Message("system", "Interrupted")
                return
    manager.edit(list(reversed(res)))
    print("Applied edited messages, write /log to see the result")


def rename(manager: LogManager, new_name: str, confirm: ConfirmFunc) -> None:
    if new_name in ["", "auto"]:
        msgs = prepare_messages(manager.log.messages)[1:]  # skip system message
        new_name = llm.generate_name(msgs)
        assert " " not in new_name, f"Invalid name: {new_name}"
        print(f"Generated name: {new_name}")
        if not confirm("Confirm?"):
            print("Aborting")
            return
        manager.rename(new_name, keep_date=True)
    else:
        manager.rename(new_name, keep_date=False)
    print(f"Renamed conversation to {manager.logfile.parent}")


def _gen_help(incl_langtags: bool = True) -> Generator[str, None, None]:
    yield "Available commands:"
    max_cmdlen = max(len(cmd) for cmd in COMMANDS)
    for cmd, desc in action_descriptions.items():
        yield f"  /{cmd.ljust(max_cmdlen)}  {desc}"

    if incl_langtags:
        yield ""
        yield "To execute code with supported tools, use the following syntax:"
        yield "  /<langtag> <code>"
        yield ""
        yield "Example:"
        yield "  /sh echo hello"
        yield "  /python print('hello')"
        yield ""
        yield "Supported langtags:"
        for tool in loaded_tools:
            if tool.block_types:
                yield f"  - {tool.block_types[0]}" + (
                    f"  (alias: {', '.join(tool.block_types[1:])})"
                    if len(tool.block_types) > 1
                    else ""
                )


def help():
    for line in _gen_help():
        print(line)
