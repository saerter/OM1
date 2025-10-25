"""
Configuration Validator for OM1
This helps users catch configuration errors early and provides helpful suggestions
"""

import json
import os
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigValidationError(Exception):
    """Custom exception for configuration validation errors"""
    pass

class ConfigValidator:
    """
    Validates OM1 configuration files and provides helpful error messages
    """
    
    def __init__(self):
        self.required_fields = {
            'inputs': ['type', 'config'],
            'actions': ['type', 'config'],
            'llm_config': ['model', 'api_key']
        }
        
        self.valid_input_types = [
            'voice', 'camera', 'keyboard', 'file', 'webcam', 'microphone'
        ]
        
        self.valid_action_types = [
            'speak', 'move', 'display', 'file_write', 'api_call'
        ]
    
    def validate_agent_config(self, config_path: str) -> Tuple[bool, List[str]]:
        """
        Validate an agent configuration file
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Check if file exists
            if not os.path.exists(config_path):
                errors.append(f"Configuration file not found: {config_path}")
                return False, errors
            
            # Load configuration
            config = self._load_config(config_path)
            
            # Validate required fields
            errors.extend(self._validate_required_fields(config))
            
            # Validate field types
            errors.extend(self._validate_field_types(config))
            
            # Validate inputs
            if 'inputs' in config:
                errors.extend(self._validate_inputs(config['inputs']))
            
            # Validate actions
            if 'actions' in config:
                errors.extend(self._validate_actions(config['actions']))
            
            # Validate LLM config
            if 'llm_config' in config:
                errors.extend(self._validate_llm_config(config['llm_config']))
            
            # Check for common issues
            errors.extend(self._check_common_issues(config))
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Error reading configuration file: {str(e)}")
            return False, errors
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from file"""
        with open(config_path, 'r') as f:
            if config_path.endswith('.json'):
                return json.load(f)
            elif config_path.endswith('.json5'):
                # For JSON5 files, we'll use basic JSON parsing for now
                # In a real implementation, you'd use a JSON5 parser
                return json.load(f)
            else:
                raise ValueError(f"Unsupported configuration file format: {config_path}")
    
    def _validate_required_fields(self, config: Dict[str, Any]) -> List[str]:
        """Validate that all required fields are present"""
        errors = []
        
        for field in ['inputs', 'actions', 'llm_config']:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        return errors
    
    def _validate_field_types(self, config: Dict[str, Any]) -> List[str]:
        """Validate that fields have the correct types"""
        errors = []
        
        if 'inputs' in config and not isinstance(config['inputs'], list):
            errors.append("'inputs' must be a list")
        
        if 'actions' in config and not isinstance(config['actions'], list):
            errors.append("'actions' must be a list")
        
        if 'llm_config' in config and not isinstance(config['llm_config'], dict):
            errors.append("'llm_config' must be a dictionary")
        
        return errors
    
    def _validate_inputs(self, inputs: List[Dict[str, Any]]) -> List[str]:
        """Validate input configurations"""
        errors = []
        
        for i, input_config in enumerate(inputs):
            if 'type' not in input_config:
                errors.append(f"Input {i}: Missing 'type' field")
            elif input_config['type'] not in self.valid_input_types:
                errors.append(f"Input {i}: Invalid type '{input_config['type']}'. Valid types: {self.valid_input_types}")
            
            if 'config' not in input_config:
                errors.append(f"Input {i}: Missing 'config' field")
        
        return errors
    
    def _validate_actions(self, actions: List[Dict[str, Any]]) -> List[str]:
        """Validate action configurations"""
        errors = []
        
        for i, action_config in enumerate(actions):
            if 'type' not in action_config:
                errors.append(f"Action {i}: Missing 'type' field")
            elif action_config['type'] not in self.valid_action_types:
                errors.append(f"Action {i}: Invalid type '{action_config['type']}'. Valid types: {self.valid_action_types}")
            
            if 'config' not in action_config:
                errors.append(f"Action {i}: Missing 'config' field")
        
        return errors
    
    def _validate_llm_config(self, llm_config: Dict[str, Any]) -> List[str]:
        """Validate LLM configuration"""
        errors = []
        
        if 'model' not in llm_config:
            errors.append("LLM config: Missing 'model' field")
        
        if 'api_key' not in llm_config:
            errors.append("LLM config: Missing 'api_key' field")
        elif llm_config['api_key'] in ['', 'your_api_key_here', 'openmind_free']:
            errors.append("LLM config: Please set a valid API key")
        
        return errors
    
    def _check_common_issues(self, config: Dict[str, Any]) -> List[str]:
        """Check for common configuration issues"""
        errors = []
        
        # Check for empty inputs/actions
        if 'inputs' in config and len(config['inputs']) == 0:
            errors.append("No inputs configured - the agent won't receive any data")
        
        if 'actions' in config and len(config['actions']) == 0:
            errors.append("No actions configured - the agent won't be able to do anything")
        
        # Check for API key in environment
        if 'llm_config' in config and 'api_key' in config['llm_config']:
            api_key = config['llm_config']['api_key']
            if api_key.startswith('${') and api_key.endswith('}'):
                env_var = api_key[2:-1]
                if not os.getenv(env_var):
                    errors.append(f"Environment variable '{env_var}' is not set")
        
        return errors
    
    def validate_all_configs(self, config_dir: str = "config") -> Dict[str, Tuple[bool, List[str]]]:
        """
        Validate all configuration files in a directory
        
        Args:
            config_dir: Directory containing configuration files
            
        Returns:
            Dictionary mapping file paths to validation results
        """
        results = {}
        config_path = Path(config_dir)
        
        if not config_path.exists():
            logger.warning(f"Configuration directory not found: {config_dir}")
            return results
        
        for config_file in config_path.glob("*.json*"):
            is_valid, errors = self.validate_agent_config(str(config_file))
            results[str(config_file)] = (is_valid, errors)
        
        return results
    
    def get_suggestions(self, errors: List[str]) -> List[str]:
        """
        Get helpful suggestions for fixing configuration errors
        
        Args:
            errors: List of error messages
            
        Returns:
            List of suggestions
        """
        suggestions = []
        
        for error in errors:
            if "API key" in error:
                suggestions.append("Get your API key from https://portal.openmind.org/")
            elif "inputs" in error.lower():
                suggestions.append("Add at least one input source (voice, camera, etc.)")
            elif "actions" in error.lower():
                suggestions.append("Add at least one action (speak, move, etc.)")
            elif "environment variable" in error:
                suggestions.append("Set the environment variable in your shell profile (.bashrc, .zshrc)")
        
        return suggestions

def main():
    """Main function for testing the validator"""
    validator = ConfigValidator()
    
    # Validate all configs in the config directory
    results = validator.validate_all_configs()
    
    print("Configuration Validation Results:")
    print("=" * 50)
    
    for config_file, (is_valid, errors) in results.items():
        print(f"\n{config_file}:")
        if is_valid:
            print("  ✅ Valid configuration")
        else:
            print("  ❌ Configuration has errors:")
            for error in errors:
                print(f"    - {error}")
            
            suggestions = validator.get_suggestions(errors)
            if suggestions:
                print("  💡 Suggestions:")
                for suggestion in suggestions:
                    print(f"    - {suggestion}")

if __name__ == "__main__":
    main()

