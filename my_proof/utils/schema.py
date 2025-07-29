import json
import os
import logging
from typing import Dict, Any, Tuple

import jsonschema

def validate_schema(input_data: Dict[str, Any]) -> Tuple[str, bool]:
    """
    Validate input data against available schemas (Google or Instagram).
    
    Args:
        input_data: The JSON data to validate
        
    Returns:
        tuple[str, bool]: A tuple containing (schema_type, is_valid)
        where schema_type is the detected schema and is_valid indicates if validation passed
    """
    # Available schemas in order of priority
    schemas = [
        'instagram-data.json',
        'google-profile.json'
    ]
    
    for schema_type in schemas:
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
    
    # If no schema matches
    logging.error("Input data does not match any available schema")
    return "unknown", False

def detect_data_type(input_data: Dict[str, Any]) -> str:
    """
    Detect the type of data based on its structure.
    
    Args:
        input_data: The JSON data to analyze
        
    Returns:
        str: The detected data type ('instagram', 'google', 'unknown')
    """
    # Instagram data detection - check for Instagram-specific fields
    if (
        'username' in input_data and 
        'profile' in input_data and
        isinstance(input_data.get('profile'), dict) and
        ('followerCount' in input_data.get('profile', {}) or 
         'followingCount' in input_data.get('profile', {}))
    ):
        return 'instagram'
    
    # Check for posts array which is Instagram-specific
    if 'posts' in input_data and isinstance(input_data.get('posts'), list):
        return 'instagram'
    
    # Check for stories or reels which are Instagram-specific
    if 'stories' in input_data or 'reels' in input_data:
        return 'instagram'
    
    # Google data detection - check for Google-specific fields
    if (
        'email' in input_data and 
        'profile' in input_data and
        isinstance(input_data.get('profile'), dict) and
        'name' in input_data.get('profile', {}) and
        'storage' in input_data
    ):
        return 'google'
    
    return 'unknown'

def get_schema_requirements(schema_type: str) -> Dict[str, Any]:
    """
    Get requirements and constraints for a specific schema type.
    
    Args:
        schema_type: The schema type ('instagram-data.json', 'google-profile.json')
        
    Returns:
        dict: Schema requirements and validation rules
    """
    if schema_type == 'instagram-data.json':
        return {
            'required_fields': ['userId', 'username', 'exportTimestamp', 'profile', 'metadata'],
            'min_engagement_posts': 1,
            'max_username_length': 30,
            'max_bio_length': 150,
            'valid_media_types': ['image', 'video', 'carousel'],
            'min_follower_quality_threshold': 10
        }
    elif schema_type == 'google-profile.json':
        return {
            'required_fields': ['userId', 'email', 'timestamp', 'profile', 'metadata'],
            'email_verification_required': True,
            'profile_name_required': True
        }
    else:
        return {}
