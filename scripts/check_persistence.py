#!/usr/bin/env python3
"""
Database persistence verification script for Docker deployments
"""
import os
import sys
import logging
from pathlib import Path

def check_persistence():
    """Verify database persistence setup"""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Check environment using centralized config
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from my_proof.config import settings
    
    is_docker = settings.DOCKER_CONTAINER or os.getenv('DOCKER_CONTAINER', False)
    db_path = settings.DB_PATH
    
    logging.info(f"Environment: {'Docker' if is_docker else 'Local'}")
    logging.info(f"Expected DB path: {db_path}")
    
    # Check data directory
    data_dir = os.path.dirname(db_path)
    if not os.path.exists(data_dir):
        logging.error(f"❌ Data directory missing: {data_dir}")
        return False
    
    if not os.access(data_dir, os.W_OK):
        logging.error(f"❌ Data directory not writable: {data_dir}")
        return False
    
    logging.info(f"✅ Data directory OK: {data_dir}")
    
    # Check if database exists
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        logging.info(f"✅ Database exists: {db_path} ({size} bytes)")
    else:
        logging.info(f"ℹ️  Database will be created: {db_path}")
    
    # Test database creation/access
    try:
        from my_proof.utils.db import DataRegistry
        registry = DataRegistry(db_path)
        logging.info("✅ Database connection successful")
        return True
    except Exception as e:
        logging.error(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    success = check_persistence()
    sys.exit(0 if success else 1)
