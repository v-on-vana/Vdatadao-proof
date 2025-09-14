from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Global settings configuration using environment variables"""

    DLP_ID: int = Field(default=143, description="Data Liquidity Pool ID")

    DLP_CONTRACT_ADDRESS: str = Field(
        default="0xaA45d51168BB94CC7b7402bb051159276b6279b2",
        description="Ethereum address of the DLP contract",
        pattern="^0x[a-fA-F0-9]{40}$",
    )

    FILE_ID: Optional[int] = Field(
        default=0, description="File ID in the Vana data registry"
    )

    OWNER_ADDRESS: Optional[str] = Field(
        default=None,
        description="Ethereum address of the data owner",
        pattern="^0x[a-fA-F0-9]{40}$",
    )

    RPC_URL: str = Field(
        default="https://rpc.moksha.vana.org",
        description="Ethereum RPC endpoint URL",
        pattern="^https?://.*$",
    )

    INPUT_DIR: str = Field(
        default="/input", description="Directory containing input files to process"
    )

    OUTPUT_DIR: str = Field(
        default="/output", description="Directory where output files will be written"
    )

    GOOGLE_TOKEN: Optional[str] = Field(
        default=None,
        description="Google OAuth2 access token for user authentication",
        min_length=20,
    )

    # Database configuration
    DATABASE_PATH: str = Field(
        default="/app/data/registry.db",
        description="Path to SQLite database file"
    )

    # Logging configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level"
    )

    class Config:
        env_file = ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Ensure directories exist
        os.makedirs(self.INPUT_DIR, exist_ok=True)
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(self.DATABASE_PATH), exist_ok=True)
        
        # Log configuration
        print(f"Configuration loaded:")
        print(f"  INPUT_DIR: {self.INPUT_DIR}")
        print(f"  OUTPUT_DIR: {self.OUTPUT_DIR}")
        print(f"  DATABASE_PATH: {self.DATABASE_PATH}")
        print(f"  DLP_ID: {self.DLP_ID}")


settings = Settings()
