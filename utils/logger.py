"""
Beautiful logging system with console output and file logging
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
try:
    from colorama import init, Fore, Back, Style
    COLORAMA_AVAILABLE = True
    init(autoreset=True)
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback colors for terminals that support ANSI
    class Fore:
        BLACK = '\033[30m'
        RED = '\033[31m'
        GREEN = '\033[32m'
        YELLOW = '\033[33m'
        BLUE = '\033[34m'
        MAGENTA = '\033[35m'
        CYAN = '\033[36m'
        WHITE = '\033[37m'
        RESET = '\033[0m'
    
    class Style:
        BRIGHT = '\033[1m'
        DIM = '\033[2m'
        RESET_ALL = '\033[0m'


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels (console only)"""
    
    COLORS = {
        'DEBUG': Fore.CYAN + Style.DIM,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW + Style.BRIGHT,  # 黄色加粗
        'ERROR': Fore.RED + Style.BRIGHT,  # 红色加粗
        'CRITICAL': Fore.RED + Back.WHITE + Style.BRIGHT,
    }
    
    RESET = Fore.RESET + Style.RESET_ALL
    
    def format(self, record):
        # Save original levelname
        original_levelname = record.levelname
        
        # Add color to levelname and message for console output
        if COLORAMA_AVAILABLE or sys.stdout.isatty():
            level_color = self.COLORS.get(record.levelname, '')
            # Color the levelname
            colored_levelname = f"{level_color}{record.levelname:8s}{self.RESET}"
            record.levelname = colored_levelname
            
            # Format the message
            result = super().format(record)
            
            # For WARNING and ERROR, also color the message content
            if original_levelname == 'WARNING':
                # Yellow for warnings - color the message part
                # Format: timestamp | levelname | name | message
                parts = result.split(' | ', 3)
                if len(parts) == 4:
                    result = f"{parts[0]} | {parts[1]} | {parts[2]} | {Fore.YELLOW}{parts[3]}{self.RESET}"
            elif original_levelname in ['ERROR', 'CRITICAL']:
                # Red for errors - color the message part
                parts = result.split(' | ', 3)
                if len(parts) == 4:
                    result = f"{parts[0]} | {parts[1]} | {parts[2]} | {Fore.RED}{parts[3]}{self.RESET}"
        else:
            record.levelname = f"{record.levelname:8s}"
            result = super().format(record)
        
        # Restore original levelname to avoid affecting file handlers
        record.levelname = original_levelname
        
        return result


class BeautifulLogger:
    """Beautiful logger with console and file output"""
    
    def __init__(self, name: str = __name__, log_dir: str = "logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler
        log_file = self.log_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        self.log_file = log_file
    
    def get_logger(self):
        return self.logger
    
    def info(self, message: str):
        self.logger.info(message)
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def critical(self, message: str):
        self.logger.critical(message)
    
    def success(self, message: str):
        """Custom success message"""
        if COLORAMA_AVAILABLE or sys.stdout.isatty():
            self.logger.info(f"{Fore.GREEN}✓ {message}{Fore.RESET}")
        else:
            self.logger.info(f"✓ {message}")
    
    def separator(self, char: str = "=", length: int = 60):
        """Print a separator line"""
        separator_line = char * length
        self.logger.info(separator_line)


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Setup beautiful logging system
    
    Args:
        log_dir: Directory to save log files
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Logger instance
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(
        fmt='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    log_file = log_path / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Log the log file location
    root_logger.info(f"Log file: {log_file}")
    
    return root_logger

