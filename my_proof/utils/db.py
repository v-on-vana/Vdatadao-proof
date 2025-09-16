import logging
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Index, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

Base = declarative_base()

class EmailRegistry(Base):
    __tablename__ = 'email_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email_hash = Column(String(64), unique=True, nullable=False, index=True)
    wallet_address = Column(String(42), nullable=False, index=True)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_email_wallet', 'email_hash', 'wallet_address'),
    )

class DataHashRegistry(Base):
    __tablename__ = 'data_hash_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    data_hash = Column(String(64), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False, index=True) 
    wallet_address = Column(String(42), nullable=False, index=True)
    email_hash = Column(String(64), nullable=False, index=True)
    contribution_id = Column(String(100), nullable=True)
    platform = Column(String(20), nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_hash_wallet_email', 'data_hash', 'wallet_address', 'email_hash'),
        Index('idx_fingerprint_wallet', 'fingerprint', 'wallet_address'),
        Index('idx_platform_registered', 'platform', 'registered_at'),
    )

class UsernameRegistry(Base):
    __tablename__ = 'username_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username_hash = Column(String(64), nullable=False, index=True)
    wallet_address = Column(String(42), nullable=False, index=True)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_username_wallet', 'username_hash', 'wallet_address'),
    )

class TimestampRegistry(Base):
    __tablename__ = 'timestamp_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False, index=True)
    wallet_address = Column(String(42), nullable=False, index=True)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_timestamp_wallet', 'timestamp', 'wallet_address'),
    )

class WalletRegistry(Base):
    __tablename__ = 'wallet_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42), unique=True, nullable=False, index=True)
    first_email_hash = Column(String(64), nullable=False)
    first_data_hash = Column(String(64), nullable=False)
    platform = Column(String(20), nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_wallet_platform', 'wallet_address', 'platform'),
    )

class DataRegistry:
    """SQLAlchemy-based data registry for email-wallet binding."""
    
    def __init__(self, db_path: str = None):
        """
        Initialize the data registry with SQLAlchemy.
        
        Args:
            db_path: Path to the SQLite database file (ignored if using PostgreSQL)
        """
        import os
        from my_proof.config import settings
        
        # Check database type and initialize accordingly
        if settings.DB_TYPE == "postgresql":
            self._init_postgresql()
        else:
            self._init_sqlite(db_path)
    
    def _init_sqlite(self, db_path: str = None):
        """Initialize SQLite database connection."""
        import os
        from my_proof.config import settings
        
        # Enhanced path resolution using centralized config
        if db_path is None:
            # Use centralized settings with environment override capability
            db_path = settings.DB_PATH
            is_docker = settings.DOCKER_CONTAINER
            
            logging.info(f"Environment: {'Docker' if is_docker else 'Local'}")
            logging.info(f"Config DB_PATH: {db_path}")
            
            # Auto-detect Docker if not explicitly set
            if not is_docker and os.getenv('DOCKER_CONTAINER'):
                is_docker = True
                logging.info("Docker environment auto-detected via env variable")
        
        # Resolve relative paths based on environment
        if not os.path.isabs(db_path):
            if settings.DOCKER_CONTAINER or os.getenv('DOCKER_CONTAINER'):
                # Docker environment - use /app prefix
                db_path = f"/app/{db_path}" if not db_path.startswith('/app/') else db_path
                logging.info(f"Docker: Resolved to absolute path: {db_path}")
            else:
                # Local environment - use project root
                app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.join(app_root, db_path)
                logging.info(f"Local: Resolved to absolute path: {db_path}")
        
        # Ensure database directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logging.info(f"Created database directory: {db_dir}")
        
        # Store final path and check if database exists
        self.db_path = db_path
        db_exists = os.path.exists(db_path)
        db_size = os.path.getsize(db_path) if db_exists else 0
        logging.info(f"Database path resolved to: {db_path}")
        logging.info(f"Database exists: {db_exists} (size: {db_size} bytes)")
        
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=False,
            pool_pre_ping=True,
            connect_args={'check_same_thread': False}
        )
        
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Enhanced database initialization logging
        logging.info(f"SQLite data registry initialized: {db_path}")
        
        # Verify persistence by checking table existence and record counts
        self._verify_database_persistence()
    
    def _init_postgresql(self):
        """Initialize PostgreSQL database connection."""
        from my_proof.config import settings
        
        # Build database URL
        if settings.DATABASE_URL:
            database_url = settings.DATABASE_URL
        else:
            database_url = (
                f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
                f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )
        
        logging.info(f"PostgreSQL connection URL: {database_url.replace(settings.POSTGRES_PASSWORD, '***')}")
        
        # Create engine with PostgreSQL-specific settings
        self.engine = create_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logging.info("PostgreSQL data registry initialized successfully")
        
        # Verify persistence by checking table existence and record counts
        self._verify_database_persistence()
    
    def _verify_database_persistence(self):
        """Verify database persistence and log existing records for debugging"""
        try:
            with self.get_session() as session:
                # Count existing records in all tables
                email_count = session.query(EmailRegistry).count()
                data_count = session.query(DataHashRegistry).count()
                wallet_count = session.query(WalletRegistry).count()
                username_count = session.query(UsernameRegistry).count()
                timestamp_count = session.query(TimestampRegistry).count()
                
                logging.info(f"Database persistence verification:")
                logging.info(f"  - EmailRegistry: {email_count} records")
                logging.info(f"  - DataHashRegistry: {data_count} records") 
                logging.info(f"  - WalletRegistry: {wallet_count} records")
                logging.info(f"  - UsernameRegistry: {username_count} records")
                logging.info(f"  - TimestampRegistry: {timestamp_count} records")
                logging.info(f"  - Database file size: {self._get_db_file_size()} bytes")
                
                if email_count > 0 or data_count > 0 or wallet_count > 0:
                    logging.info("✅ PERSISTENCE: Existing records found - database is persistent")
                else:
                    logging.info("ℹ️  PERSISTENCE: Clean database - no existing records")
                    
        except Exception as e:
            logging.error(f"Database persistence verification failed: {str(e)}")
    
    def _get_db_file_size(self) -> int:
        """Get database file size for persistence debugging"""
        try:
            import os
            if os.path.exists(self.db_path):
                return os.path.getsize(self.db_path)
            return 0
        except Exception:
            return -1
    
    @contextmanager
    def get_session(self) -> Session:
        """Context manager for database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Database session error: {str(e)}")
            raise
        finally:
            session.close()
    
    def register_email_hash(self, email_hash: str, wallet_address: str) -> bool:
        """
        Register an email hash to a wallet address.
        
        Args:
            email_hash: SHA256 hash of the email
            wallet_address: Wallet address of the contributor
            
        Returns:
            bool: True if registration successful, False if email already registered to different wallet
        """
        try:
            with self.get_session() as session:
                existing = session.query(EmailRegistry).filter_by(email_hash=email_hash).first()
                
                if existing:
                    if existing.wallet_address.lower() == wallet_address.lower():
                        logging.info(f"Email hash {email_hash[:16]}... already registered to same wallet")
                        return True
                    else:
                        logging.warning(f"Email hash {email_hash[:16]}... already registered to different wallet {existing.wallet_address[:10]}...")
                        return False
                
                new_entry = EmailRegistry(
                    email_hash=email_hash,
                    wallet_address=wallet_address
                )
                
                session.add(new_entry)
                session.commit()
                
                logging.info(f"Email hash {email_hash[:16]}... registered for wallet {wallet_address[:10]}...")
                return True
                
        except IntegrityError:
            logging.warning(f"Email hash {email_hash[:16]}... already exists (race condition)")
            return self._check_existing_registration(email_hash, wallet_address)
        except Exception as e:
            logging.error(f"Error registering email hash: {str(e)}")
            return False
    
    def is_email_hash_registered(self, email_hash: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an email hash is already registered.
        
        Args:
            email_hash: SHA256 hash of the email to check
            
        Returns:
            Tuple: (is_registered: bool, registered_wallet: str or None)
        """
        try:
            with self.get_session() as session:
                result = session.query(EmailRegistry).filter_by(email_hash=email_hash).first()
                
                if result:
                    logging.info(f"Email hash {email_hash[:16]}... found registered to {result.wallet_address[:10]}...")
                    return True, result.wallet_address
                
                return False, None
                
        except Exception as e:
            logging.error(f"Error checking email hash registration: {str(e)}")
            return False, None
    
    def get_wallet_emails(self, wallet_address: str) -> list:
        """
        Get all email hashes registered to a wallet address.
        
        Args:
            wallet_address: Wallet address to check
            
        Returns:
            list: List of email hashes registered to the wallet
        """
        try:
            with self.get_session() as session:
                results = session.query(EmailRegistry).filter_by(wallet_address=wallet_address).all()
                return [r.email_hash for r in results]
                
        except Exception as e:
            logging.error(f"Error getting wallet emails: {str(e)}")
            return []
    
    def _check_existing_registration(self, email_hash: str, wallet_address: str) -> bool:
        """Check if existing registration matches the wallet address."""
        is_registered, registered_wallet = self.is_email_hash_registered(email_hash)
        if is_registered and registered_wallet:
            return registered_wallet.lower() == wallet_address.lower()
        return False
    
    def register_data_hash(self, data_hash: str, fingerprint: str, wallet_address: str, 
                          email_hash: str, contribution_id: str = None, platform: str = "instagram") -> bool:
        """
        Register a data hash with its fingerprint to the database.
        
        Args:
            data_hash: SHA256 hash of the data
            fingerprint: Core data fingerprint 
            wallet_address: Wallet address of the contributor
            email_hash: Hash of the contributor's email
            contribution_id: Optional contribution ID
            platform: Data platform (instagram, google, etc.)
            
        Returns:
            bool: True if registration successful
        """
        try:
            with self.get_session() as session:
                new_entry = DataHashRegistry(
                    data_hash=data_hash,
                    fingerprint=fingerprint,
                    wallet_address=wallet_address,
                    email_hash=email_hash,
                    contribution_id=contribution_id,
                    platform=platform
                )
                
                session.add(new_entry)
                session.commit()
                
                logging.info(f"Data hash {data_hash[:16]}... registered for wallet {wallet_address[:10]}...")
                return True
                
        except Exception as e:
            logging.error(f"Error registering data hash: {str(e)}")
            return False
    
    def register_wallet(self, wallet_address: str, email_hash: str, data_hash: str, platform: str = "instagram") -> bool:
        """
        Register a wallet for the first time.
        
        Args:
            wallet_address: Wallet address to register
            email_hash: Hash of the email used
            data_hash: Hash of the data submitted
            platform: Platform name
            
        Returns:
            bool: True if registration successful
        """
        try:
            with self.get_session() as session:
                existing = session.query(WalletRegistry).filter_by(wallet_address=wallet_address).first()
                
                if existing:
                    logging.warning(f"Wallet {wallet_address[:10]}... already registered")
                    return False
                
                new_entry = WalletRegistry(
                    wallet_address=wallet_address,
                    first_email_hash=email_hash,
                    first_data_hash=data_hash,
                    platform=platform
                )
                
                session.add(new_entry)
                session.commit()
                
                logging.info(f"Wallet {wallet_address[:10]}... registered successfully")
                return True
                
        except Exception as e:
            logging.error(f"Error registering wallet: {str(e)}")
            return False

    def is_wallet_used(self, wallet_address: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a wallet has been used before.
        
        Args:
            wallet_address: Wallet address to check
            
        Returns:
            Tuple: (is_used: bool, first_email_hash: str or None)
        """
        try:
            with self.get_session() as session:
                result = session.query(WalletRegistry).filter_by(wallet_address=wallet_address).first()
                
                if result:
                    logging.info(f"Wallet {wallet_address[:10]}... found in registry")
                    return True, result.first_email_hash
                
                return False, None
                
        except Exception as e:
            logging.error(f"Error checking wallet usage: {str(e)}")
            return False, None

    def is_data_hash_used(self, data_hash: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a data hash has been used before.
        
        Args:
            data_hash: Data hash to check
            
        Returns:
            Tuple: (is_used: bool, wallet_address: str or None)
        """
        try:
            with self.get_session() as session:
                result = session.query(DataHashRegistry).filter_by(data_hash=data_hash).first()
                if result:
                    logging.info(f"Data hash {data_hash[:16]}... found used by wallet {result.wallet_address[:10]}...")
                    return True, result.wallet_address
                
                result = session.query(WalletRegistry).filter_by(first_data_hash=data_hash).first()
                if result:
                    logging.info(f"Data hash {data_hash[:16]}... found as first submission by wallet {result.wallet_address[:10]}...")
                    return True, result.wallet_address
                
                return False, None
                
        except Exception as e:
            logging.error(f"Error checking data hash usage: {str(e)}")
            return False, None

    def check_data_duplicate(self, data_hash: str, fingerprint: str, wallet_address: str, 
                           email_hash: str) -> Tuple[bool, str]:
        """
        Ultra-strict duplicate checking: ONLY allow completely new combinations.
        
        Rules:
        - If wallet was used before = DENY
        - If email was used before = DENY  
        - If data hash was used before = DENY
        - If fingerprint was used before = DENY
        - ONLY allow: New wallet + New email + New data
        
        Args:
            data_hash: SHA256 hash of the data
            fingerprint: Core data fingerprint
            wallet_address: Wallet address of the contributor
            email_hash: Hash of the contributor's email
            
        Returns:
            Tuple: (is_duplicate: bool, reason: str)
        """
        try:
            with self.get_session() as session:
                logging.info(f"🔍 DUPLICATE CHECK for wallet {wallet_address[:10]}...")
                
                # Check 1: Wallet already used?
                wallet_used, first_email = self.is_wallet_used(wallet_address)
                if wallet_used:
                    logging.warning(f"❌ WALLET_ALREADY_USED: {wallet_address[:10]}... (first email: {first_email[:16] if first_email else 'unknown'}...)")
                    return True, "WALLET_ALREADY_USED"
                logging.info(f"✅ Wallet {wallet_address[:10]}... is new")
                
                # Check 2: Email already used?
                email_used, registered_to_wallet = self.is_email_hash_registered(email_hash)
                if email_used:
                    logging.warning(f"❌ EMAIL_ALREADY_USED: {email_hash[:16]}... registered to {registered_to_wallet[:10] if registered_to_wallet else 'unknown'}...")
                    return True, "EMAIL_ALREADY_USED"
                logging.info(f"✅ Email hash {email_hash[:16]}... is new")
                
                # Check 3: Data hash already used?
                data_used, used_by_wallet = self.is_data_hash_used(data_hash)
                if data_used:
                    logging.warning(f"❌ DATA_ALREADY_USED: {data_hash[:16]}... used by {used_by_wallet[:10] if used_by_wallet else 'unknown'}...")
                    return True, f"DATA_ALREADY_USED_BY_WALLET_{used_by_wallet[:10] if used_by_wallet else 'UNKNOWN'}"
                logging.info(f"✅ Data hash {data_hash[:16]}... is new")
                
                # Check 4: Fingerprint already used?
                fingerprint_exists = session.query(DataHashRegistry).filter_by(fingerprint=fingerprint).first()
                if fingerprint_exists:
                    logging.warning(f"❌ SIMILAR_DATA_ALREADY_USED: fingerprint {fingerprint[:16]}... used by {fingerprint_exists.wallet_address[:10]}...")
                    return True, f"SIMILAR_DATA_ALREADY_USED_BY_WALLET_{fingerprint_exists.wallet_address[:10]}"
                logging.info(f"✅ Fingerprint {fingerprint[:16]}... is new")
                
                # If we reach here, everything is new
                logging.info(f"🎉 ALL_NEW_ALLOWED: All checks passed for {wallet_address[:10]}...")
                return False, "ALL_NEW_ALLOWED"
                
        except Exception as e:
            logging.error(f"Error checking data duplicate: {str(e)}")
            return False, f"ERROR: {str(e)}"
    
    def is_data_hash_registered(self, data_hash: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a data hash is already registered.
        
        Args:
            data_hash: SHA256 hash of the data to check
            
        Returns:
            Tuple: (is_registered: bool, registered_wallet: str or None, registered_email: str or None)
        """
        try:
            with self.get_session() as session:
                result = session.query(DataHashRegistry).filter_by(data_hash=data_hash).first()
                
                if result:
                    logging.info(f"Data hash {data_hash[:16]}... found registered to {result.wallet_address[:10]}...")
                    return True, result.wallet_address, result.email_hash
                
                return False, None, None
                
        except Exception as e:
            logging.error(f"Error checking data hash registration: {str(e)}")
            return False, None, None

    def get_registration_stats(self) -> dict:
        """Get registration statistics."""
        try:
            with self.get_session() as session:
                email_registrations = session.query(EmailRegistry).count()
                email_unique_wallets = session.query(EmailRegistry.wallet_address).distinct().count()
                
                data_registrations = session.query(DataHashRegistry).count()
                data_unique_wallets = session.query(DataHashRegistry.wallet_address).distinct().count()
                unique_platforms = session.query(DataHashRegistry.platform).distinct().count()
                
                return {
                    'email_registrations': email_registrations,
                    'email_unique_wallets': email_unique_wallets,
                    'data_registrations': data_registrations,
                    'data_unique_wallets': data_unique_wallets,
                    'unique_platforms': unique_platforms
                }
                
        except Exception as e:
            logging.error(f"Error getting registration stats: {str(e)}")
            return {'email_registrations': 0, 'email_unique_wallets': 0, 'data_registrations': 0, 'data_unique_wallets': 0, 'unique_platforms': 0}

    def check_username_duplicate(self, username_hash: str, wallet_address: str) -> Tuple[bool, str]:
        """
        Username duplicate check.
        
        Prevents the same username from being sent with different wallets.
        """
        try:
            with self.get_session() as session:
                result = session.query(UsernameRegistry).filter_by(username_hash=username_hash).first()
                if result and result.wallet_address != wallet_address:
                    return True, f"USERNAME_ALREADY_USED_BY_WALLET_{result.wallet_address}"
                return False, "NO_DUPLICATE"
        except Exception as e:
            logging.error(f"Error checking username duplicate: {str(e)}")
            return False, "ERROR_IN_USERNAME_CHECK"

    def check_timestamp_duplicate(self, timestamp: int, wallet_address: str) -> Tuple[bool, str]:
        """
        Account creation timestamp duplicate check.
        
        Prevents the same Instagram account from being sent with different wallets.
        """
        try:
            with self.get_session() as session:
                result = session.query(TimestampRegistry).filter_by(timestamp=timestamp).first()
                if result and result.wallet_address != wallet_address:
                    logging.warning(f"Found timestamp {timestamp} already used by wallet {result.wallet_address}")
                    return True, f"SAME_INSTAGRAM_ACCOUNT_ALREADY_USED_BY_WALLET_{result.wallet_address}"
                logging.info(f"No timestamp {timestamp} found in existing records")
                return False, "NO_DUPLICATE"
        except Exception as e:
            logging.error(f"Error checking timestamp duplicate: {str(e)}")
            return False, "ERROR_IN_TIMESTAMP_CHECK"

    def register_username_hash(self, username_hash: str, wallet_address: str) -> bool:
        """Register username hash"""
        try:
            with self.get_session() as session:
                username_reg = UsernameRegistry(
                    username_hash=username_hash,
                    wallet_address=wallet_address
                )
                session.add(username_reg)
                return True
        except Exception as e:
            logging.error(f"Error registering username hash: {str(e)}")
            return False

    def register_timestamp(self, timestamp: int, wallet_address: str) -> bool:
        """Register timestamp"""
        try:
            with self.get_session() as session:
                timestamp_reg = TimestampRegistry(
                    timestamp=timestamp,
                    wallet_address=wallet_address
                )
                session.add(timestamp_reg)
                return True
        except Exception as e:
            logging.error(f"Error registering timestamp: {str(e)}")
            return False

def hash_email(email: str) -> str:
    """Hash an email address using SHA256."""
    normalized_email = email.lower().strip()
    return hashlib.sha256(normalized_email.encode('utf-8')).hexdigest()

def hash_username(username: str) -> str:
    """Hash a username using SHA256."""
    normalized_username = username.lower().strip()
    return hashlib.sha256(normalized_username.encode('utf-8')).hexdigest()

def hash_wallet(wallet_address: str) -> str:
    """Hash a wallet address using SHA256."""
    normalized_wallet = wallet_address.lower().strip()
    return hashlib.sha256(normalized_wallet.encode('utf-8')).hexdigest()
