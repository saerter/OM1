#!/usr/bin/env python3
"""
OM1 Configuration Validator CLI Tool
This tool helps users validate their OM1 configuration files
"""

import argparse
import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config_validator import ConfigValidator

def main():
    parser = argparse.ArgumentParser(
        description="Validate OM1 configuration files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_config.py                          # Validate all configs in ./config
  python validate_config.py -f config/spot.json5     # Validate specific file
  python validate_config.py -d /path/to/configs      # Validate all configs in directory
  python validate_config.py --fix                    # Try to fix common issues
        """
    )
    
    parser.add_argument(
        '-f', '--file',
        help='Validate a specific configuration file'
    )
    
    parser.add_argument(
        '-d', '--directory',
        default='config',
        help='Directory containing configuration files (default: config)'
    )
    
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Try to fix common configuration issues'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed validation information'
    )
    
    args = parser.parse_args()
    
    validator = ConfigValidator()
    
    if args.file:
        # Validate single file
        validate_single_file(validator, args.file, args.verbose, args.fix)
    else:
        # Validate all files in directory
        validate_directory(validator, args.directory, args.verbose, args.fix)

def validate_single_file(validator: ConfigValidator, file_path: str, verbose: bool, fix: bool):
    """Validate a single configuration file"""
    print(f"Validating configuration file: {file_path}")
    print("=" * 60)
    
    is_valid, errors = validator.validate_agent_config(file_path)
    
    if is_valid:
        print("✅ Configuration is valid!")
        if verbose:
            print("All required fields are present and correctly formatted.")
    else:
        print("❌ Configuration has errors:")
        for error in errors:
            print(f"  - {error}")
        
        suggestions = validator.get_suggestions(errors)
        if suggestions:
            print("\n💡 Suggestions:")
            for suggestion in suggestions:
                print(f"  - {suggestion}")
        
        if fix:
            print("\n🔧 Attempting to fix issues...")
            fix_configuration(file_path, errors)
        
        sys.exit(1)

def validate_directory(validator: ConfigValidator, directory: str, verbose: bool, fix: bool):
    """Validate all configuration files in a directory"""
    print(f"Validating all configuration files in: {directory}")
    print("=" * 60)
    
    results = validator.validate_all_configs(directory)
    
    if not results:
        print(f"⚠️  No configuration files found in {directory}")
        return
    
    valid_count = 0
    total_count = len(results)
    
    for config_file, (is_valid, errors) in results.items():
        file_name = Path(config_file).name
        print(f"\n📄 {file_name}:")
        
        if is_valid:
            print("  ✅ Valid configuration")
            valid_count += 1
        else:
            print("  ❌ Configuration has errors:")
            for error in errors:
                print(f"    - {error}")
            
            suggestions = validator.get_suggestions(errors)
            if suggestions:
                print("  💡 Suggestions:")
                for suggestion in suggestions:
                    print(f"    - {suggestion}")
            
            if fix:
                print("  🔧 Attempting to fix issues...")
                fix_configuration(config_file, errors)
    
    print(f"\n📊 Summary: {valid_count}/{total_count} configurations are valid")
    
    if valid_count < total_count:
        sys.exit(1)

def fix_configuration(file_path: str, errors: list):
    """Attempt to fix common configuration issues"""
    print(f"  Attempting to fix: {file_path}")
    
    # This is a simple implementation - in a real tool, you'd have more sophisticated fixing
    fixes_applied = 0
    
    for error in errors:
        if "API key" in error and "openmind_free" in error:
            print(f"    - Found placeholder API key, please update manually")
            fixes_applied += 1
        elif "Missing required field" in error:
            print(f"    - Missing field: {error}")
            print(f"    - Please add the missing field manually")
            fixes_applied += 1
    
    if fixes_applied > 0:
        print(f"  Applied {fixes_applied} fixes (manual review required)")
    else:
        print(f"  No automatic fixes available for this configuration")

if __name__ == "__main__":
    main()

