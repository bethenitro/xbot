#!/usr/bin/env python3
"""
Enhanced Twitter Bot (Xbot) - Main Entry Point

A sophisticated Python application for automated Twitter/X community posting
with advanced anti-bot detection evasion techniques.
"""

import sys
import os
import argparse
import time
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from utils.logging import setup_logging
from config.manager import ConfigurationManager


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Enhanced Twitter Bot (Xbot) - Automated Twitter/X community posting"
    )
    
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level from configuration"
    )
    
    parser.add_argument(
        "--log-file",
        help="Path to log file (default: logs/xbot.log)"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )
    
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration and exit"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Enhanced Twitter Bot (Xbot) v1.0.0"
    )
    
    return parser.parse_args()


def validate_environment():
    """Validate that the environment is properly set up."""
    errors = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        errors.append("Python 3.8 or higher is required")
    
    # Check required directories
    required_dirs = ["src", "logs", "data", "sessions"]
    for dir_name in required_dirs:
        if not Path(dir_name).exists():
            Path(dir_name).mkdir(parents=True, exist_ok=True)
    
    # Check for required files
    if not Path("config.json").exists():
        print("Warning: config.json not found, will create default configuration")
    
    if errors:
        print("Environment validation failed:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    return True


def main():
    """Main application entry point."""
    try:
        # Parse command line arguments
        args = parse_arguments()
        
        # Validate environment
        if not validate_environment():
            sys.exit(1)
        
        # Load configuration
        config_manager = ConfigurationManager(args.config)
        config = config_manager.load_config()
        
        # Override configuration with command line arguments
        if args.log_level:
            config.error_handling.log_level = args.log_level
        if args.headless:
            config.browser_settings.headless = True
        
        # Set up logging
        log_file = args.log_file or "logs/xbot.log"
        setup_logging(
            log_level=config.error_handling.log_level,
            log_file=log_file
        )
        
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("Enhanced Twitter Bot (Xbot) starting up...")
        logger.info(f"Configuration loaded from: {args.config}")
        logger.info(f"Log level: {config.error_handling.log_level}")
        
        # Validate configuration if requested
        if args.validate_config:
            try:
                config_manager.validate_config(config)
                print("Configuration validation passed!")
                print(config_manager.get_config_summary())
                sys.exit(0)
            except ValueError as e:
                print(f"Configuration validation failed: {e}")
                sys.exit(1)
        
        # Import main application components
        from src.core.post_manager import PostManager
        from src.gui.web_server import create_web_gui
        from src.browser.browser_factory import browser_factory
        
        # ZenDriver is the only browser available
        logger.info("Using ZenDriver browser")
        
        # Initialize post manager
        post_manager = PostManager(config_manager)
        
        # Initialize web GUI if not in headless mode
        if not config.browser_settings.headless:
            logger.info("Starting web-based GUI interface...")
            
            # Create web GUI server
            # Use to_dict() to ensure all nested dataclasses (like AutomationSettings) are converted to dicts
            gui = create_web_gui(config.to_dict())
            
            # Set up callbacks between GUI and post manager
            gui.set_callbacks(
                start_callback=post_manager.start_posting,
                stop_callback=post_manager.stop_posting,
                pause_callback=post_manager.pause_posting
            )
            
            post_manager.set_callbacks(
                status_callback=lambda status: logger.info(f"Bot status: {status}"),
                error_callback=lambda msg: logger.error(f"Bot error: {msg}")
            )
            
            # Start web server
            try:
                import webbrowser
                import threading
                
                # Open browser after a short delay
                def open_browser():
                    time.sleep(1.5)
                    webbrowser.open('http://127.0.0.1:5000')
                
                threading.Thread(target=open_browser, daemon=True).start()
                
                # Start the web server (this will block)
                gui.run(host='127.0.0.1', port=5000, debug=False)
                
            except KeyboardInterrupt:
                logger.info("Web GUI interrupted by user")
            finally:
                # Cleanup
                if post_manager.is_running:
                    post_manager.stop_posting()
                gui.close()
        else:
            # Headless mode - run without GUI
            logger.info("Running in headless mode...")
            
            try:
                # Start posting operations
                success = post_manager.start_posting()
                if not success:
                    logger.error("Failed to start posting operations")
                    sys.exit(1)
                
                # Keep running until interrupted
                while post_manager.is_running:
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("Headless mode interrupted by user")
            finally:
                # Cleanup
                if post_manager.is_running:
                    post_manager.stop_posting()
        
        logger.info("Application shutdown completed")
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        if 'logger' in locals():
            logger.exception("Fatal error occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()