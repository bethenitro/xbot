# Enhanced Twitter Bot (Xbot)

A sophisticated Python application for automated Twitter/X community posting with advanced anti-bot detection evasion techniques using Camoufox browser automation.

## Features

- **Stealth Browser Automation**: Uses Camoufox with built-in human-like cursor movement and fingerprint spoofing
- **Human Behavior Simulation**: Realistic typing delays, scrolling patterns, and reading pauses
- **Cookie-Based Authentication**: Secure session management similar to redpost-bot
- **Community Group Management**: Independent posting schedules for different community groups
- **Queue Management**: Automated post queue with completion tracking
- **Error Recovery**: Comprehensive error handling with retry logic and rate limit detection
- **GUI Interface**: User-friendly interface for monitoring and controlling operations
- **Configuration Profiles**: Multiple configuration profiles for different posting strategies

## Requirements

- Python 3.8 or higher
- Camoufox browser automation library
- Required Python packages (see requirements.txt)

## Installation

1. **Clone or download the project**
   ```bash
   cd Xbot
   ```

2. **Create virtual environment (recommended)**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up configuration**
   ```bash
   # Copy sample files
   cp posts.txt.sample posts.txt
   cp communities.txt.sample communities.txt
   
   # Edit configuration files as needed
   ```

## Configuration

### Main Configuration (config.json)

The main configuration file controls all aspects of the bot's behavior:

- **posting_intervals**: Default posting intervals and limits
- **behavior_settings**: Human behavior simulation parameters
- **stealth_settings**: Anti-detection and fingerprint rotation settings
- **browser_settings**: Browser window and automation settings
- **session_settings**: Cookie and session management
- **error_handling**: Retry logic and error recovery settings

### Posts Configuration (posts.txt)

Add your posts in either format:

**Plain text format:**
```
Hello world! This is my first automated post.
Check out this amazing content!
```

**JSON format for advanced options:**
```json
{"content": "Post with image", "images": ["path/to/image.png"], "community_groups": ["tech"]}
{"content": "Scheduled post", "scheduled_for": "2024-12-01T10:00:00"}
```

### Communities Configuration (communities.txt)

Configure your Twitter communities:

**Plain URL format (added to 'default' group):**
```
https://twitter.com/i/communities/1234567890
https://x.com/i/communities/0987654321
```

**JSON format for group management:**
```json
{"name": "tech", "communities": ["https://twitter.com/i/communities/1111"], "posting_interval": 7200}
{"name": "social", "communities": ["https://twitter.com/i/communities/2222"], "posting_interval": 3600}
```

## Usage

### GUI Mode (Default)

```bash
python main.py
```

This launches the graphical interface where you can:
- Monitor posting status and queue information
- Start/stop/pause posting operations
- View real-time logs and statistics
- Handle authentication challenges

### Headless Mode

```bash
python main.py --headless
```

Runs without GUI for server deployments.

### Command Line Options

```bash
python main.py --help
```

Available options:
- `--config`: Custom configuration file path
- `--log-level`: Override log level (DEBUG, INFO, WARNING, ERROR)
- `--log-file`: Custom log file path
- `--headless`: Run without GUI
- `--validate-config`: Validate configuration and exit

## Authentication

The bot uses cookie-based authentication:

1. **First Run**: The bot will open Twitter login page
2. **Manual Login**: Complete login manually in the browser
3. **Cookie Capture**: Bot automatically saves encrypted authentication cookies
4. **Subsequent Runs**: Cookies are restored for seamless authentication

## Stealth Features

### Camoufox Integration
- Built-in human-like cursor movement (C++ implementation)
- Native fingerprint spoofing and anti-leak patches
- Sandboxed JavaScript execution

### Human Behavior Simulation
- Variable typing speeds (50-200ms between keystrokes)
- Random scrolling patterns and reading pauses
- Timing fluctuations (±20% variation)
- Random page visits before posting (2-3 pages)

### Anti-Detection Measures
- Fingerprint rotation between sessions
- Rate limit detection and handling
- Risk assessment and adaptive delays
- Error recovery with exponential backoff

## File Structure

```
Xbot/
├── main.py                 # Main application entry point
├── config.json            # Main configuration file
├── requirements.txt       # Python dependencies
├── posts.txt              # Posts queue (create from sample)
├── communities.txt        # Community groups (create from sample)
├── data/                  # Data directory
│   ├── pictures/          # Image attachments
│   └── posting_history.json
├── logs/                  # Log files
├── sessions/              # Encrypted session data
└── src/                   # Source code
    ├── browser/           # Camoufox browser automation
    ├── behavior/          # Human behavior simulation
    ├── config/            # Configuration management
    ├── core/              # Main application logic
    ├── error/             # Error handling and recovery
    ├── gui/               # Graphical user interface
    ├── models/            # Data models
    ├── queue/             # Post queue and scheduling
    ├── session/           # Session and authentication
    ├── stealth/           # Stealth and anti-detection
    ├── twitter/           # Twitter-specific interactions
    └── utils/             # Utility functions
```

## Troubleshooting

### Common Issues

1. **Browser Launch Fails**
   - Ensure Camoufox is properly installed
   - Check system requirements and dependencies
   - Try running with `--log-level DEBUG` for detailed logs

2. **Authentication Problems**
   - Delete session files in `sessions/` directory
   - Clear browser cookies manually
   - Ensure Twitter account is not restricted

3. **Rate Limiting**
   - Bot automatically handles rate limits
   - Increase posting intervals in configuration
   - Check error logs for specific rate limit messages

4. **Posts Not Processing**
   - Verify posts.txt format is correct
   - Check community URLs are valid
   - Ensure community groups are active

### Log Files

Check log files in the `logs/` directory for detailed information:
- `xbot.log`: Main application logs
- Use `--log-level DEBUG` for verbose logging

### Configuration Validation

```bash
python main.py --validate-config
```

This checks your configuration for errors and displays a summary.

## Security Considerations

- Authentication cookies are encrypted using industry-standard cryptography
- Session data is stored locally and never transmitted
- Browser fingerprints are rotated to maintain privacy
- All network requests use HTTPS

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review log files for error details
3. Validate configuration files
4. Ensure all dependencies are properly installed

## License

This project is provided as-is for educational and automation purposes. Users are responsible for complying with Twitter's Terms of Service and applicable laws.