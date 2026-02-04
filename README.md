# Xbot

A sophisticated Python application for automated Twitter/X community posting with advanced anti-bot detection evasion techniques using ZenDriver browser automation.

## Features

- **ZenDriver Browser Automation**: Uses ZenDriver (Chrome DevTools Protocol) for maximum stealth - no WebDriver detection
- **Multi-Account Support**: Cycle through multiple Twitter accounts with independent session management
- **Community Group Management**: Independent posting schedules for different community groups with randomized intervals
- **Human Behavior Simulation**: Realistic typing delays, scrolling patterns, and reading pauses
- **Cookie-Based Authentication**: Secure session management with encrypted cookie storage
- **Queue Management**: Automated post queue with completion tracking and status persistence
- **Error Recovery**: Comprehensive error handling with retry logic and rate limit detection
- **Web-Based GUI**: Real-time monitoring dashboard with start/stop/pause controls
- **Stealth Engine**: Fingerprint rotation, anti-detection measures, and adaptive delays
- **Proxy Support**: Optional proxy rotation for additional anonymity

## Requirements

- Python 3.8 or higher
- ZenDriver (Chrome DevTools Protocol automation)
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

- **posting_intervals**: Default posting intervals and randomness percentage
- **behavior_settings**: Human behavior simulation parameters (typing delays, scroll pauses, etc.)
- **stealth_settings**: Anti-detection settings (fingerprint consistency, cookie refresh)
- **browser_settings**: Browser window and automation settings
- **session_settings**: Cookie and session management
- **error_handling**: Retry logic and error recovery settings
- **automation**: CSS selectors and XPath expressions for Twitter UI elements
- **proxy_settings**: Proxy configuration and defaults

### Architecture Overview

#### Core Components

**Post Manager** (`src/core/post_manager.py`)
- Orchestrates the entire posting workflow
- Manages multi-account cycling (every account posts to every community)
- Coordinates between all subsystems
- Handles browser lifecycle and session management

**Posting Scheduler** (`src/posting/posting_scheduler.py`)
- Manages independent schedules for each community group
- Implements randomized posting intervals (±25% by default)
- Tracks last posted time and calculates next post times
- Supports group activation/deactivation

**Queue Manager** (`src/posting/queue_manager.py`)
- Manages post queue and completion tracking
- Persists queue state to `data/posts.json`
- Tracks post status (pending, completed, failed)
- Supports filtering by community group

**Account Manager** (`src/account/account_manager.py`)
- Manages multiple Twitter accounts
- Handles account cycling for multi-account posting
- Stores encrypted session cookies
- Tracks account metadata and fingerprints

**Browser Factory** (`src/browser/browser_factory.py`)
- Creates ZenDriver instances
- Manages browser configuration
- Handles browser lifecycle

**Stealth Engine** (`src/stealth/stealth_engine.py`)
- Implements anti-detection measures
- Manages fingerprint rotation
- Applies stealth delays between operations
- Handles rate limit detection

**Error Handler** (`src/error/error_handler.py`)
- Implements retry logic with exponential backoff
- Tracks error statistics and patterns
- Manages rate limit recovery
- Provides error context and recovery suggestions

#### Data Models

**Post** (`src/models/post.py`)
- Represents a single post with content and metadata
- Tracks post status and completion time
- Supports image attachments

**Account** (`src/models/session.py`)
- Represents a Twitter account
- Stores credentials, cookies, and fingerprint data
- Tracks last login and activity

**CommunityGroup** (`src/models/community_group.py`)
- Represents a group of communities
- Manages posting interval and schedule
- Tracks last posted time

**Proxy** (`src/models/proxy.py`)
- Represents proxy configuration
- Stores proxy URL and authentication details

#### Posting Workflow

1. **Initialization**: Load configuration, accounts, communities, and posts
2. **Scheduling**: Calculate next due post across all community groups
3. **Account Selection**: Cycle through active accounts
4. **Browser Launch**: Create new ZenDriver instance with stealth settings
5. **Authentication**: Restore cookies or handle login challenge
6. **Posting**: Execute post to selected community
7. **Cleanup**: Close browser and update schedules
8. **Repeat**: Wait for next scheduled post

## Configuration

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

This launches the web-based GUI interface (http://127.0.0.1:5000) where you can:
- Monitor posting status and queue information in real-time
- View community group schedules and next post times
- Start/stop/pause posting operations
- Track account cycling progress
- View error logs and statistics
- Monitor stealth engine status

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

The bot uses cookie-based authentication with multi-account support:

1. **First Run**: The bot will open Twitter login page for each account
2. **Manual Login**: Complete login manually in the browser
3. **Cookie Capture**: Bot automatically saves encrypted authentication cookies per account
4. **Subsequent Runs**: Cookies are restored for seamless authentication
5. **Session Validation**: Bot validates sessions before posting and handles re-authentication if needed

## Multi-Account Posting Strategy

Xbot implements a comprehensive multi-account posting system where:

- **Every account posts to every community**: Account 1 → Community 1, 2, 3; Account 2 → Community 1, 2, 3; etc.
- **Independent account cycling**: Accounts cycle through sequentially with progress tracking
- **Encrypted session storage**: Each account's cookies are encrypted and stored separately
- **Fingerprint management**: Each account maintains its own browser fingerprint
- **Proxy rotation**: Optional proxy assignment per account for additional anonymity

### Account Management

Accounts are stored in `data/accounts.json` with the following structure:
- Username and password (encrypted)
- Session cookies (encrypted)
- Browser fingerprint data
- Proxy assignment
- Last login timestamp
- Active/inactive status

### Community Group Management

Communities are organized into groups in `data/communities.json`:
- Each group has independent posting intervals
- Randomized intervals prevent detection patterns
- Groups can be activated/deactivated independently
- Supports multiple communities per group

## Stealth Features

### ZenDriver Integration
- Chrome DevTools Protocol-based automation (no WebDriver detection)
- Blazing fast performance with minimal overhead
- Undetectable by anti-bot systems that look for WebDriver
- Native browser automation without synthetic indicators

### Human Behavior Simulation
- Variable typing speeds (50-200ms between keystrokes)
- Random scrolling patterns and reading pauses
- Timing fluctuations (±20% variation)
- Randomized posting intervals (configurable ±25% by default)

### Anti-Detection Measures
- Fingerprint rotation between sessions
- Rate limit detection and adaptive handling
- Exponential backoff on failures
- Stealth delays between operations
- Proxy rotation support for additional anonymity

## File Structure

```
Xbot/
├── main.py                      # Main application entry point
├── config.json                  # Main configuration file
├── requirements.txt             # Python dependencies
├── posts.txt                    # Posts queue (create from sample)
├── communities.txt              # Community groups (create from sample)
├── data/                        # Data directory
│   ├── accounts.json            # Account credentials and metadata
│   ├── posts.json               # Post queue and history
│   ├── communities.json         # Community group definitions
│   ├── proxies.json             # Proxy configurations
│   ├── captions.json            # Post captions library
│   ├── image_hashes.json        # Image deduplication hashes
│   ├── image_groups.json        # Image grouping metadata
│   └── images/                  # Image attachments directory
├── logs/                        # Log files
├── sessions/                    # Browser profiles and session data
│   ├── zendriver_profiles/      # ZenDriver browser profiles
│   └── proxy_auth_extension/    # Proxy authentication extension
└── src/                         # Source code
    ├── account/                 # Account management and cycling
    ├── behavior/                # Human behavior simulation
    ├── browser/                 # ZenDriver browser automation
    ├── config/                  # Configuration management
    ├── core/                    # Post manager and orchestration
    ├── error/                   # Error handling and recovery
    ├── gui/                     # Web-based GUI interface
    ├── models/                  # Data models (Post, Account, etc.)
    ├── posting/                 # Queue and scheduler management
    ├── proxy/                   # Proxy management and rotation
    ├── session/                 # Session and authentication
    ├── stealth/                 # Stealth engine and anti-detection
    ├── twitter/                 # Twitter/X interface
    └── utils/                   # Utility functions and helpers
```

## Troubleshooting

### Common Issues

1. **Browser Launch Fails**
   - Ensure ZenDriver is properly installed: `pip install zendriver`
   - Check system requirements and dependencies
   - Try running with `--log-level DEBUG` for detailed logs

2. **Authentication Problems**
   - Delete session files in `sessions/` directory
   - Clear account cookies in `data/accounts.json`
   - Ensure Twitter account is not restricted or locked
   - Check if 2FA is enabled (may require manual intervention)

3. **Rate Limiting**
   - Bot automatically handles rate limits with exponential backoff
   - Increase posting intervals in configuration
   - Check error logs for specific rate limit messages
   - Consider using proxy rotation for additional anonymity

4. **Posts Not Processing**
   - Verify posts.txt format is correct
   - Check community URLs are valid and accessible
   - Ensure community groups are active
   - Verify accounts are active and authenticated

5. **Multi-Account Issues**
   - Ensure all accounts are properly authenticated
   - Check that accounts have access to communities
   - Verify proxy settings if using proxies
   - Check account status in `data/accounts.json`

### Log Files

Check log files in the `logs/` directory for detailed information:
- `xbot.log`: Main application logs
- Use `--log-level DEBUG` for verbose logging
- Logs include component-specific information (browser, posting, stealth, etc.)

### Configuration Validation

```bash
python main.py --validate-config
```

This checks your configuration for errors and displays a summary including:
- Configuration file validity
- Required fields presence
- Value ranges and constraints
- Component availability

## Security Considerations

- Authentication cookies are encrypted using industry-standard cryptography
- Session data is stored locally and never transmitted
- Browser fingerprints are rotated to maintain privacy
- All network requests use HTTPS
- Account credentials are encrypted in storage
- Proxy credentials are handled securely
- No telemetry or external data collection

## Performance Characteristics

- **ZenDriver**: Blazing fast Chrome DevTools Protocol automation
- **Memory Usage**: Minimal - new browser instance per post (like quick post)
- **CPU Usage**: Low - efficient event loop management
- **Network**: Optimized with connection pooling
- **Scalability**: Supports unlimited accounts and communities (limited by system resources)

## Advanced Features

### Randomized Posting Intervals
- Configurable randomness percentage (default ±25%)
- Prevents detection of automated patterns
- Independent randomization per community group
- Adaptive delays based on error history

### Fingerprint Rotation
- Unique fingerprint per account
- Rotates between sessions
- Includes user agent, screen resolution, timezone, etc.
- Prevents fingerprint-based detection

### Rate Limit Handling
- Automatic detection of rate limit responses
- Exponential backoff strategy
- Adaptive delay adjustment
- Error statistics tracking

### Proxy Support
- Per-account proxy assignment
- Proxy rotation support
- Proxy authentication handling
- Fallback to direct connection if needed

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review log files for error details
3. Validate configuration files
4. Ensure all dependencies are properly installed

## License

This project is provided as-is for educational and automation purposes. Users are responsible for complying with Twitter's Terms of Service and applicable laws.