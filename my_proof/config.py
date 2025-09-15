from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


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

    # Database Configuration
    DB_PATH: str = Field(
        default="data/registry.db",
        description="Path to the SQLite database file for duplicate detection",
    )

    DOCKER_CONTAINER: bool = Field(
        default=False,
        description="Whether running inside Docker container",
    )

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
