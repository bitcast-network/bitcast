"""
Patch for replacing bittensor logging with standard Python logging.

IMPORTANT: This module must be imported before any other modules that use bittensor.
Example usage:
  
  # At the very top of your entry point script:
  import bt_logging_patch
  
  # Then continue with your normal imports
  import other_modules
"""

import sys
import types
import logging
import importlib.util

# Configure logging to show all logs
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

print("🔧 Patching bittensor.logging with standard logging")

# Create a mock logging class that forwards to standard logging
class MockLogging:
    def __init__(self):
        self.logger = logging.getLogger("bittensor")
        self.logger.setLevel(logging.DEBUG)
    
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)
    
    def success(self, msg, *args, **kwargs):
        # Map success to info with a prefix
        self.logger.info(f"SUCCESS: {msg}", *args, **kwargs)
    
    def trace(self, msg, *args, **kwargs):
        # Map trace to debug with a prefix
        self.logger.debug(f"TRACE: {msg}", *args, **kwargs)
    
    # Mock configuration methods to do nothing
    def set_config(self, *args, **kwargs):
        pass
    
    def add_args(self, *args, **kwargs):
        pass

# Try to import the real bittensor module
try:
    # Check if bittensor is already in sys.modules
    if "bittensor" in sys.modules:
        # Get the existing module
        bittensor = sys.modules["bittensor"]
        # Replace only its logging attribute
        bittensor.logging = MockLogging()
        print("✅ Replaced logging in existing bittensor module")
    else:
        # Try to import the real module
        import bittensor
        # Save the original module
        real_bittensor = bittensor
        # Replace only its logging attribute
        real_bittensor.logging = MockLogging()
        # Update sys.modules to use our modified module
        sys.modules["bittensor"] = real_bittensor
        print("✅ Imported real bittensor module and replaced its logging")
    
    # Also patch bt for imports like "import bt"
    if "bt" not in sys.modules:
        sys.modules["bt"] = sys.modules["bittensor"]
        print("✅ Added 'bt' as an alias to the patched bittensor module")
    
except ImportError:
    print("⚠️ Could not import bittensor - creating minimal mock")
    # Create a minimal mock module with just logging
    mock_bittensor = types.ModuleType("bittensor")
    mock_bittensor.logging = MockLogging()
    
    # Add the mock module to sys.modules
    sys.modules["bittensor"] = mock_bittensor
    sys.modules["bt"] = mock_bittensor
    print("✅ Created minimal mock for bittensor (logging only)")

print("✅ Patching complete - bt.logging and bittensor.logging now use standard logging") 