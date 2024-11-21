# GPT-Modified

A modified version of gptme with additional features for performance analysis and optimization.

## New Features

### Profile Command
- `/profile` - Analyze performance metrics of the application
- Shows top functions by cumulative time and call count
- Helps identify performance bottlenecks

### Clean Logs Command
- `/cleanlogs` - Optimize conversation logs to reduce token usage
- Removes duplicate messages
- Combines related system messages
- Preserves important metadata
- Use `/cleanlogs --all` to clean all conversation logs

### Improved Reload
- Enhanced `/reload` command with better state management
- Preserves settings during reload
- Proper cleanup of stateful components
- More robust module reloading

## Installation

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install the package:
```bash
pip install -e .
```

## Requirements

Main dependencies:
- click
- rich
- anthropic
- openai
- python-dotenv

For full list of dependencies, see `requirements.txt`.

## Usage

Start the application:
```bash
gptme
```

### Profile Analysis
To analyze performance:
```bash
# Start gptme with profiling enabled
gptme --profile

# Use the application normally
# Then use /profile to see performance metrics
```

### Log Optimization
```bash
# Clean current conversation
/cleanlogs

# Clean all conversations
/cleanlogs --all
```

## Development

To contribute:
1. Fork the repository
2. Create a virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Install in editable mode: `pip install -e .`
