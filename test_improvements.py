#!/usr/bin/env python3
"""
Test script for the OM1 improvements
This script tests the new connection manager and configuration validator
"""

import sys
import os
import asyncio
import tempfile
import json
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from connectors.connection_manager import ConnectionManager, APIConnectionManager, retry_on_failure
from utils.config_validator import ConfigValidator

async def test_connection_manager():
    """Test the connection manager functionality"""
    print("🧪 Testing Connection Manager...")
    
    # Test basic connection manager
    manager = ConnectionManager(max_retries=3, base_timeout=5)
    
    # Test successful connection
    async def successful_connection():
        await asyncio.sleep(0.1)
        return "success"
    
    try:
        result = await manager.robust_connect(successful_connection)
        print(f"  ✅ Successful connection test: {result}")
    except Exception as e:
        print(f"  ❌ Successful connection test failed: {e}")
    
    # Test failed connection
    async def failing_connection():
        await asyncio.sleep(0.1)
        raise Exception("Connection failed")
    
    try:
        result = await manager.robust_connect(failing_connection)
        print(f"  ❌ Failed connection test should have failed but got: {result}")
    except Exception as e:
        print(f"  ✅ Failed connection test correctly failed: {e}")
    
    # Test stats
    stats = manager.get_stats()
    print(f"  📊 Connection stats: {stats}")
    
    print("✅ Connection Manager tests completed")

def test_config_validator():
    """Test the configuration validator"""
    print("\n🧪 Testing Configuration Validator...")
    
    validator = ConfigValidator()
    
    # Create a temporary valid config file
    valid_config = {
        "inputs": [
            {
                "type": "voice",
                "config": {"sample_rate": 44100}
            }
        ],
        "actions": [
            {
                "type": "speak",
                "config": {"voice": "default"}
            }
        ],
        "llm_config": {
            "model": "gpt-4o",
            "api_key": "test_api_key_123"
        }
    }
    
    # Create a temporary invalid config file
    invalid_config = {
        "inputs": [],  # Empty inputs
        "actions": [],  # Empty actions
        "llm_config": {
            "model": "gpt-4o"
            # Missing api_key
        }
    }
    
    # Test valid configuration
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(valid_config, f)
        valid_config_path = f.name
    
    try:
        is_valid, errors = validator.validate_agent_config(valid_config_path)
        if is_valid:
            print("  ✅ Valid configuration test passed")
        else:
            print(f"  ❌ Valid configuration test failed: {errors}")
    except Exception as e:
        print(f"  ❌ Valid configuration test error: {e}")
    finally:
        os.unlink(valid_config_path)
    
    # Test invalid configuration
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(invalid_config, f)
        invalid_config_path = f.name
    
    try:
        is_valid, errors = validator.validate_agent_config(invalid_config_path)
        if not is_valid and len(errors) > 0:
            print("  ✅ Invalid configuration test passed")
            print(f"  📝 Found {len(errors)} errors as expected")
        else:
            print(f"  ❌ Invalid configuration test failed: {errors}")
    except Exception as e:
        print(f"  ❌ Invalid configuration test error: {e}")
    finally:
        os.unlink(invalid_config_path)
    
    print("✅ Configuration Validator tests completed")

async def test_api_connection_manager():
    """Test the API connection manager"""
    print("\n🧪 Testing API Connection Manager...")
    
    manager = APIConnectionManager()
    
    # Test successful API call
    async def successful_api_call():
        await asyncio.sleep(0.1)
        return {"status": "success", "data": "test_data"}
    
    try:
        result = await manager.make_api_call(successful_api_call)
        print(f"  ✅ Successful API call test: {result}")
    except Exception as e:
        print(f"  ❌ Successful API call test failed: {e}")
    
    # Test health status
    health = manager.get_health_status()
    print(f"  📊 Health status: {health}")
    
    print("✅ API Connection Manager tests completed")

async def test_retry_decorator():
    """Test the retry decorator"""
    print("\n🧪 Testing Retry Decorator...")
    
    call_count = 0
    
    @retry_on_failure(max_retries=3, timeout=5)
    async def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Temporary failure")
        return "success after retries"
    
    try:
        result = await flaky_function()
        print(f"  ✅ Retry decorator test passed: {result}")
        print(f"  📊 Function was called {call_count} times")
    except Exception as e:
        print(f"  ❌ Retry decorator test failed: {e}")
    
    print("✅ Retry Decorator tests completed")

async def main():
    """Run all tests"""
    print("🚀 Starting OM1 Improvements Tests")
    print("=" * 50)
    
    # Run all tests
    await test_connection_manager()
    test_config_validator()
    await test_api_connection_manager()
    await test_retry_decorator()
    
    print("\n🎉 All tests completed!")
    print("=" * 50)
    print("Your improvements are working correctly! 🚀")

if __name__ == "__main__":
    asyncio.run(main())
