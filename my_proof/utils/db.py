import logging
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Index
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

class DataRegistry:
    """SQLAlchemy-based data registry for email-wallet binding."""
    
    def __init__(self, db_path: str = "data/registry.db"):
        """
        Initialize the data registry with SQLAlchemy.
        
        Args:
            db_path: Path to the SQLite database file
        """
        import os
        
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logging.info(f"Created database directory: {db_dir}")
        
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=False,
            pool_pre_ping=True,
            connect_args={'check_same_thread': False}
        )
        
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logging.info(f"Data registry initialized: {db_path}")
    
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
    
    def get_registration_stats(self) -> dict:
        """Get registration statistics."""
        try:
            with self.get_session() as session:
                total_registrations = session.query(EmailRegistry).count()
                unique_wallets = session.query(EmailRegistry.wallet_address).distinct().count()
                
                return {
                    'total_registrations': total_registrations,
                    'unique_wallets': unique_wallets
                }
                
        except Exception as e:
            logging.error(f"Error getting registration stats: {str(e)}")
            return {'total_registrations': 0, 'unique_wallets': 0}

def hash_email(email: str) -> str:
    """Hash an email address using SHA256."""
    normalized_email = email.lower().strip()
    return hashlib.sha256(normalized_email.encode('utf-8')).hexdigest()
