import json
import os
import logging
from typing import Dict, Any, Tuple

import jsonschema

def validate_schema(input_data: Dict[str, Any]) -> Tuple[str, bool]:
    """
    Validate input data against available schemas (Google profile or Instagram meta export).
    
    Args:
        input_data: The JSON data to validate
        
    Returns:
        tuple[str, bool]: A tuple containing (schema_type, is_valid)
        where schema_type is the matched schema filename
        and is_valid indicates if the schema validation passed
    """
    schemas_to_try = []
    
    # Determine which schema to validate against based on data structure
    # Only support Instagram meta export schema
    schemas_to_try = ['instagram-meta-export.json']
    
    for schema_type in schemas_to_try:
        try:
            # Load the schema
            schema_path = os.path.join(os.path.dirname(__file__), '..', 'schemas', schema_type)
            
            if not os.path.exists(schema_path):
                logging.warning(f"Schema file not found: {schema_path}")
                continue
                
            with open(schema_path, 'r') as f:
                schema = json.load(f)
                
            # Validate against schema
            jsonschema.validate(instance=input_data, schema=schema)
            logging.info(f"Data successfully validated against {schema_type}")
            return schema_type, True
            
        except jsonschema.exceptions.ValidationError as e:
            logging.debug(f"Schema validation failed for {schema_type}: {str(e)}")
            continue
        except Exception as e:
            logging.error(f"Schema validation error for {schema_type}: {str(e)}")
            continue
    
    # If no schema matched
    logging.error("Data did not match any available schema")
    return schemas_to_try[0] if schemas_to_try else 'unknown', False

def _is_instagram_data(input_data: Dict[str, Any]) -> bool:
    """
    Check if the input data appears to be Instagram data based on structure.
    
    Args:
        input_data: The JSON data to check
        
    Returns:
        bool: True if it appears to be Instagram data
    """
    # Check for Instagram-specific fields
    instagram_indicators = [
        'contribution_id',
        'contributor',
        'data.platform',
        'data.profile.username',
        'data.metrics.posts_count',
        'data.activities',
        'metadata.data_type'
    ]
    
    for indicator in instagram_indicators:
        if _has_nested_key(input_data, indicator):
            value = _get_nested_value(input_data, indicator)
            if indicator == 'data.platform' and value == 'instagram':
                return True
            elif indicator == 'metadata.data_type' and 'instagram' in str(value).lower():
                return True
            elif indicator in ['contribution_id', 'data.profile.username', 'data.activities']:
                return True
    
    return False

def _has_nested_key(data: Dict[str, Any], key_path: str) -> bool:
    """Check if nested key exists in data."""
    keys = key_path.split('.')
    current = data
    
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    
    return True

def _get_nested_value(data: Dict[str, Any], key_path: str) -> Any:
    """Get nested value from data."""
    keys = key_path.split('.')
    current = data
    
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    
    return current
