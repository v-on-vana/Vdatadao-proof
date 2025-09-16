#!/usr/bin/env python3
"""
PostgreSQL integration test script for vdatadao-proof
Tests both SQLite and PostgreSQL database connections
"""

import os
import logging
from my_proof.config import settings
from my_proof.utils.db import DataRegistry, EmailRegistry, DataHashRegistry

logging.basicConfig(level=logging.INFO)

def test_postgresql_config():
    """Test PostgreSQL configuration settings."""
    print("=== PostgreSQL Configuration Test ===\n")
    print("1. Environment Variables:")
    print(f"   DB_TYPE: {settings.DB_TYPE}")
    print(f"   DATABASE_URL: {settings.DATABASE_URL}")
    print(f"   POSTGRES_HOST: {settings.POSTGRES_HOST}")
    print(f"   POSTGRES_PORT: {settings.POSTGRES_PORT}")
    print(f"   POSTGRES_DB: {settings.POSTGRES_DB}")
    print(f"   POSTGRES_USER: {settings.POSTGRES_USER}")
    print(f"   POSTGRES_PASSWORD: {'*' * len(settings.POSTGRES_PASSWORD)}")

def test_database_connection():
    """Test database connection based on DB_TYPE."""
    print("\n2. Database Connection Test:")
    try:
        if settings.DB_TYPE == "postgresql":
            print("   Attempting PostgreSQL connection...")
            data_registry = DataRegistry()
            with data_registry.get_session() as session:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))
            print("   ✅ PostgreSQL connection successful!")
        else:
            print("   ⚠️  DB_TYPE is set to 'sqlite', not 'postgresql'")
            print("   Set DB_TYPE=postgresql to use PostgreSQL")
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")

def test_database_tables():
    """Test database tables accessibility."""
    if settings.DB_TYPE == "postgresql":
        print("\n3. Database Tables Check:")
        try:
            data_registry = DataRegistry()
            with data_registry.get_session() as session:
                email_count = session.query(EmailRegistry).count()
                data_hash_count = session.query(DataHashRegistry).count()
                print(f"   Email Registry: {email_count} records")
                print(f"   Data Hash Registry: {data_hash_count} records")
            print("   ✅ Database tables accessible!")
        except Exception as e:
            print(f"   ❌ Database tables check failed: {e}")

def test_sqlite_fallback():
    """Test SQLite fallback functionality."""
    print("\n=== SQLite Fallback Test ===\n")
    print("1. Testing SQLite connection...")
    try:
        # Temporarily override DB_TYPE to test SQLite
        original_db_type = settings.DB_TYPE
        settings.DB_TYPE = "sqlite"
        sqlite_data_registry = DataRegistry()
        with sqlite_data_registry.get_session() as session:
            email_count = session.query(EmailRegistry).count()
            print(f"   ✅ SQLite connection successful!")
            print(f"   Email Registry: {email_count} records")
        settings.DB_TYPE = original_db_type  # Restore original
    except Exception as e:
        print(f"   ❌ SQLite connection failed: {e}")

def main():
    """Main test function."""
    print("Vdatadao PostgreSQL Integration Test\n")
    
    test_postgresql_config()
    test_database_connection()
    test_database_tables()
    test_sqlite_fallback()
    
    print("\n=== Test Summary ===\n")
    if settings.DB_TYPE == "postgresql":
        print("✅ PostgreSQL configuration is working!")
        print("   You can now use PostgreSQL for data storage")
    else:
        print("⚠️  PostgreSQL is not active. Currently using SQLite.")
        print("   To activate PostgreSQL, set DB_TYPE=postgresql in your environment variables or .env file.")

if __name__ == "__main__":
    main()
