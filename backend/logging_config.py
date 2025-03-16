import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(app):

    log_dir = os.path.join(os.path.dirname(app.root_path), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Main application log file
    app_log_file = os.path.join(log_dir, 'app.log')

    # Configure file handler
    file_handler = RotatingFileHandler(
        app_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    file_handler.setLevel(logging.INFO)

    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    console_handler.setLevel(logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Set up specific loggers
    loggers = {
        'app': logging.getLogger('app'),
        'prices': logging.getLogger('prices'),
        'scheduler': logging.getLogger('scheduler'),
        'api': logging.getLogger('api')
    }

    # Make sure all loggers have the same handlers
    for name, logger in loggers.items():
        logger.handlers = []  # Remove any existing handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Prevent double logging

    # Update Flask app logger
    app.logger.handlers = []
    for handler in [file_handler, console_handler]:
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    app.logger.info(f"Logging configured. Log file: {app_log_file}")

    return loggers